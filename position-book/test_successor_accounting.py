"""Durable successor accounting with disposable source, keys and RPC evidence."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch
import unittest

import successor_accounting as m
import test_successor_receipt_review as fixture
import admission_lifecycle as lifecycle
import admission_recovery as recovery
import controlled_acceptance
from test_signed_exit_timing import files


class AccountingTests(fixture.ReceiptReviewTests):
    def collect_effects(self, *, failure=False):
        self.submit(); package, _ = self.package()
        self.recover(fixture.ReceiptReplies(self, fixture.failed(package) if failure else package))

    def apply_accounting(self):
        return m._apply(self.c.home, self.c.wallet, self.c.pool, self.candidate,
                        allow_accounting=True, clock=lambda: self.c.now)

    def accounting_status(self):
        return m.status(self.c.home, self.c.wallet, self.c.pool, self.candidate, clock=lambda: self.c.now)

    def assert_held(self, result):
        for key in ('reservationsReleased', 'scopedClosureRecorded', 'fundsAvailableForNewEntry',
                    'nextCycleAuthorized', 'executionApproved', 'currentWalletBalanceEstablished',
                    'retiredAttemptEffectsReconciled', 'networkRequests', 'privateKeyAccessed',
                    'signaturesCreated', 'transactionsSent'):
            self.assertFalse(result[key], key)

    def test_commit_duplicate_lifecycle_and_recovery_conserve_known_fees_and_exposure(self):
        self.collect_effects(); before = self.rows(); original_files = files(self.c)
        result = self.apply_accounting(); self.assertTrue(result['appliedThisRun']); self.assert_held(result)
        self.assertEqual(result['state'], 'successor-accounted-flat-held')
        after = self.rows(); self.assertEqual(set(after)-set(before), {m.TABLE})
        self.assertEqual(before, {k: after[k] for k in before})
        for name, raw in original_files.items():
            if name != str(self.c.path): self.assertEqual(Path(name).read_bytes(), raw)
        saved = files(self.c); again = self.apply_accounting()
        self.assertFalse(again['appliedThisRun']); self.assertEqual(again['recordSha256'], result['recordSha256'])
        self.assertEqual(files(self.c), saved)
        view = lifecycle.inspect(self.c.home, self.c.wallet, self.c.pool, clock=lambda: self.c.now)
        self.assertTrue(view['coherent'], view); self.assertEqual(view['phase'], result['state'])
        amounts = view['scopedAccounting']
        self.assertEqual(amounts['ownedAcquiredHeldAtomic'], '0')
        self.assertEqual(amounts['protectedAcquiredInventoryAtomic'], '902')
        self.assertEqual(amounts['sourceProceedsHeldAtomic'], '96')
        self.assertEqual(amounts['feePaidLamports'], '10002')
        self.assertEqual(amounts['feeHeldLamports'], '15998')
        self.assertEqual(amounts['retiredFeeExposureHeldLamports'], '10000')
        self.assertFalse(amounts['scopedClosureRecorded'])
        projected = controlled_acceptance.projection(view)
        self.assertEqual(projected['scopedAccounting']['retiredFeeExposureHeldLamports'], '10000')
        self.assertEqual(projected['recordIdentity']['exitSuccessorAccountingSha256'], result['recordSha256'])
        book = self.c.book()
        try:
            recovered = recovery.retirement_projection(book, self.c.home, self.c.wallet, self.c.pool, lambda: self.c.now)
        finally: book.close()
        self.assertEqual(recovered['successorAccountingSha256'], result['recordSha256'])
        self.assertEqual(recovered['scopedAccounting'], amounts)
        self.assertEqual(files(self.c), saved)

    def test_failed_receipt_after_stop_preserves_owned_inventory(self):
        self.collect_effects(failure=True); self.c.now += 30000; (self.c.home/'STOP').touch(mode=0o600)
        result = self.apply_accounting(); self.assert_held(result)
        self.assertEqual(result['state'], 'successor-accounted-failed-held')
        self.assertEqual(result['effects']['ownedAcquiredResidualAtomic'], '98')
        self.assertEqual(result['effects']['sourceProceedsObservedAtomic'], '0')
        self.assertEqual(result['effects']['retiredFeeExposureHeldLamports'], '10000')
        self.assertEqual(self.accounting_status()['recordSha256'], result['recordSha256'])

    def test_explicit_optin_and_complete_evidence_required_before_write(self):
        with patch.object(m.submission.transport, '_open', side_effect=AssertionError('source access')):
            with self.assertRaisesRegex(ValueError, 'explicit-successor-accounting-required'):
                m._apply('/missing', 'wallet', 'pool', 'hash')
        before = files(self.c); result = self.apply_accounting()
        self.assertFalse(result['accountingRecorded']); self.assertFalse(result['appliedThisRun'])
        self.assertEqual(files(self.c), before)
        self.submit(); self.recover(); before = files(self.c)
        self.assertFalse(self.apply_accounting()['accountingRecorded'])
        self.assertEqual(files(self.c), before)

    def test_rehashed_record_and_future_clock_are_rejected(self):
        self.collect_effects(); self.apply_accounting(); saved = self.c.path.read_bytes()
        for field in ('fee', 'clock', 'capture'):
            with self.subTest(field=field):
                self.c.path.write_bytes(saved); book = self.c.book()
                try:
                    row = m.saved(book, self.c.now)
                    if field == 'fee': row['effects']['retiredFeeExposureHeldLamports'] = '0'
                    elif field == 'clock': row['recordedAtMs'] = self.c.now + 1
                    else: row['captureSha256'] = '0'*64
                    book.db.execute('UPDATE admission_successor_accounting SET value=?,hash=?', (m.encoded(row), m.digest(row)))
                finally: book.close()
                before = files(self.c)
                with self.assertRaises(ValueError): self.accounting_status()
                with self.assertRaises(ValueError): self.apply_accounting()
                self.assertEqual(files(self.c), before)
                self.assertFalse(lifecycle.inspect(self.c.home, self.c.wallet, self.c.pool,
                    clock=lambda: self.c.now)['coherent'])

    def test_storage_failure_rolls_back_and_lost_completion_is_idempotent(self):
        self.collect_effects(); before = files(self.c); original_check = m.check
        def fail_after_insert(condition, reason):
            if reason == 'successor-accounting-ledger-cap': raise OSError('synthetic storage failure')
            return original_check(condition, reason)
        with patch.object(m, 'check', side_effect=fail_after_insert):
            with self.assertRaises(OSError): self.apply_accounting()
        self.assertEqual(files(self.c), before)
        book = self.c.book()
        try: journal_type = type(book.j); transaction = journal_type.transaction
        finally: book.close()
        @contextmanager
        def lost(journal):
            with transaction(journal): yield
            raise OSError('synthetic lost completion after commit')
        with patch.object(journal_type, 'transaction', lost):
            with self.assertRaises(OSError): self.apply_accounting()
        result = self.accounting_status(); self.assertTrue(result['accountingUsable'], result)
        before = files(self.c); again = self.apply_accounting()
        self.assertFalse(again['appliedThisRun']); self.assertEqual(again['recordSha256'], result['recordSha256'])
        self.assertEqual(files(self.c), before)

    def test_writer_exclusion_and_orphan_accounting_fail_closed(self):
        self.collect_effects(); original = m.receipts.review; collisions = []
        def inspect(*args, **kwargs):
            db = sqlite3.connect(self.c.path, timeout=0)
            try:
                with self.assertRaises(sqlite3.OperationalError): db.execute('BEGIN IMMEDIATE')
            finally: db.close()
            collisions.append(True); return original(*args, **kwargs)
        with patch.object(m.receipts, 'review', side_effect=inspect): self.apply_accounting()
        self.assertEqual(collisions, [True])
        book = self.c.book()
        try: book.db.execute('DROP TABLE admission_exit_successor')
        finally: book.close()
        before = files(self.c)
        self.assertFalse(lifecycle.inspect(self.c.home, self.c.wallet, self.c.pool, clock=lambda: self.c.now)['coherent'])
        with self.assertRaises(ValueError): self.accounting_status()
        self.assertEqual(files(self.c), before)

    def test_later_receipt_conflict_cannot_replace_durable_accounting(self):
        self.collect_effects(); first = self.apply_accounting()
        self.c.now += 1; book = self.c.book()
        try:
            _, _, _, _, state = m.submission.load(self.c.home, book, self.c.wallet,
                self.c.pool, self.candidate, lambda: self.c.now)
            duplicate = deepcopy(state['captures'][0]); duplicate['startedAtMs'] = self.c.now
            m.submission.append(book, duplicate, state, self.c.now)
        finally: book.close()
        before = files(self.c); again = self.apply_accounting()
        self.assertEqual(again['recordSha256'], first['recordSha256'])
        self.assertFalse(again['appliedThisRun']); self.assertEqual(files(self.c), before)
        def change(seq, value):
            if value['kind'] == 'capture':
                value['rpcEvidence']['transaction']['result']['meta']['fee'] = 10001
        self.rewrite(change); before = files(self.c)
        result = self.accounting_status()
        self.assertTrue(result['accountingRecorded']); self.assertFalse(result['accountingUsable'])
        self.assertEqual(result['state'], 'quarantined'); self.assert_held(result)
        self.assertFalse(self.apply_accounting()['appliedThisRun'])
        self.assertEqual(files(self.c), before)


if __name__ == '__main__': unittest.main()
