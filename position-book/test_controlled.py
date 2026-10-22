"""Actual signed synthetic journals exercise the historical import boundary."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

import controlled as c
import test_reverse_swap as reverse


class ControlledAccountingCase(unittest.TestCase):
    setUpClass = classmethod(reverse.ReverseCase.setUpClass.__func__)
    tearDownClass = classmethod(reverse.ReverseCase.tearDownClass.__func__)
    setUp = reverse.ReverseCase.setUp
    tearDown = reverse.ReverseCase.tearDown
    run_exit = reverse.ReverseCase.run_exit

    def sync(self):
        return c.sync(self.home, self.wallet, self.pool)

    def files(self):
        return {str(p.relative_to(self.home)): p.read_bytes() for p in self.home.rglob('*')
                if p.is_file() and not p.name.startswith(c.NAME)}

    def test_open_position_excludes_background_and_never_opens_key_or_network(self):
        before = self.files()
        # Deleting the disposable key proves the reader cannot derive/open it.
        keys = [p for p in self.home.rglob('*') if p.is_file() and p.suffix == '.pk8']
        self.assertTrue(keys)
        for key in keys:
            key.unlink()
        before = self.files()
        with patch('core.signer', side_effect=AssertionError('signer called')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('network called')):
            r = self.sync()
        p = r['position']
        self.assertEqual(r['state'], 'open')
        self.assertEqual(p['backgroundAcquiredAtomic'], '500000000')
        self.assertEqual(p['lastReconciledResidualAtomic'], '998')
        self.assertEqual(p['confirmedFeeLamports'], '5000')
        self.assertFalse(p['currentWalletBalancesKnown'])
        self.assertFalse(r['pretradeBudgetEnforced'])
        self.assertEqual(before, self.files())

    def test_closed_round_trip_import_and_restart_do_not_duplicate_fees(self):
        r, _ = self.run_exit()
        self.assertEqual(r['state'], 'finalized-success')
        before = self.files()
        first = self.sync(); second = self.sync()
        self.assertEqual(first['state'], 'closed')
        self.assertEqual(first['position']['confirmedFeeLamports'], '10000')
        self.assertEqual(first['position']['netOriginalTokenAtomic'], '-4')
        self.assertEqual(first['position']['lastReconciledResidualAtomic'], '0')
        self.assertEqual(second['eventCount'], 1)
        self.assertFalse(second['ledgerChanged'])
        self.assertEqual(first['position'], second['position'])
        self.assertEqual(before, self.files())

    def test_open_then_close_appends_exactly_one_update(self):
        self.assertEqual(self.sync()['eventCount'], 1)
        self.run_exit()
        r = self.sync()
        self.assertEqual(r['eventCount'], 2)
        self.assertEqual(r['state'], 'closed')

    def test_failed_exit_retains_acquisition_and_charges_actual_fee(self):
        self.run_exit(failure=True)
        r = self.sync()
        self.assertEqual(r['state'], 'open')
        self.assertEqual(r['position']['confirmedFeeLamports'], '10000')
        self.assertEqual(r['position']['lastReconciledResidualAtomic'], '998')
        self.assertEqual(r['position']['returnedOriginalAtomic'], '0')

    def test_pending_exit_preserves_last_known_exposure_until_receipt(self):
        _, transport = self.run_exit(pending=True)
        r = self.sync()
        self.assertEqual(r['state'], 'exit-unresolved')
        self.assertEqual(r['position']['lastReconciledResidualAtomic'], '998')
        self.assertEqual(r['position']['confirmedFeeLamports'], '5000')
        self.assertFalse(r['position']['exitOutcomeResolved'])
        transport.pending = False
        reverse.submit.recover(self.home, self.wallet, reverse=True, opener=transport, sleeper=lambda _: None)
        r = self.sync()
        self.assertEqual(r['state'], 'closed')
        self.assertEqual(r['eventCount'], 2)

    def test_changed_receipt_summary_without_raw_proof_creates_no_ledger(self):
        path = self.home / c.submit.CHILD / 'observation-000.json'
        v = json.loads(path.read_text()); v['receipt']['outputAtomic'] = '999'
        path.write_text(json.dumps(v))
        with self.assertRaises(ValueError): self.sync()
        self.assertFalse((self.home / c.NAME).exists())

    def test_lost_source_after_import_quarantines_persistently(self):
        self.sync()
        path = self.home / c.submit.CHILD / 'receipt-evidence.json'
        old = path.read_bytes(); path.unlink()
        first = self.sync()
        self.assertEqual(first['state'], 'quarantined')
        self.assertFalse(first['position']['accountingUsable'])
        path.write_bytes(old); path.chmod(0o600)
        second = self.sync()
        self.assertEqual(second['state'], 'quarantined')
        self.assertEqual(second['eventCount'], first['eventCount'])

    def test_removed_finalized_reverse_cannot_reopen_closed_position(self):
        import shutil
        self.run_exit(); self.sync()
        shutil.rmtree(self.home / c.submit.REVERSE_CHILD)
        r = self.sync()
        self.assertEqual(r['state'], 'quarantined')
        self.assertEqual(r['position']['confirmedFeeLamports'], '10000')

    def test_wrong_explicit_identity_does_not_poison_existing_ledger(self):
        self.sync()
        before = (self.home / c.NAME).read_bytes()
        for wallet, pool in ((reverse.fake_key('other-wallet'), self.pool),
                             (self.wallet, reverse.fake_key('other-pool'))):
            with self.assertRaises(ValueError): c.sync(self.home, wallet, pool)
        self.assertEqual(before, (self.home / c.NAME).read_bytes())

    def test_source_execution_lock_prevents_import(self):
        with c.source_lock(self.home, self.wallet):
            with self.assertRaises(BlockingIOError): self.sync()
        self.assertFalse((self.home / c.NAME).exists())

    def test_unsafe_ledger_symlink_and_permissions_are_rejected(self):
        self.sync(); path = self.home / c.NAME
        path.chmod(0o644)
        with self.assertRaises(ValueError): self.sync()
        path.chmod(0o600); saved = self.home / 'saved-accounting'
        path.rename(saved); path.symlink_to(saved)
        with self.assertRaises(OSError): self.sync()

    def test_mutated_ledger_snapshot_is_rejected(self):
        self.sync()
        with sqlite3.connect(self.home / c.NAME) as db:
            db.execute("UPDATE controlled_events SET snapshot=replace(snapshot, '998', '999')")
        with self.assertRaises(ValueError): self.sync()

    def test_generic_journal_cannot_silently_become_controlled_ledger(self):
        journal = c.Journal(self.home / c.NAME); journal.close()
        with self.assertRaises(ValueError): self.sync()

    def test_clock_regression_rolls_back_update(self):
        value = c.read_evidence(self.home, self.wallet, self.pool)
        ledger = c.Ledger(self.home, create=True, clock=lambda: 100)
        try:
            ledger.apply(value)
            self.run_exit()
            value = c.read_evidence(self.home, self.wallet, self.pool)
            ledger.j.clock = lambda: 99
            with self.assertRaises(ValueError): ledger.apply(value)
            self.assertEqual(ledger.read()[0]['state'], 'open')
            self.assertEqual(ledger.read()[1], 1)
        finally: ledger.close()

    def test_cap_failure_retains_previous_complete_snapshot(self):
        self.sync(); self.run_exit()
        with patch.object(c, 'MAX_EVENTS', 1):
            with self.assertRaises(ValueError): self.sync()
        ledger = c.Ledger(self.home, create=False)
        try:
            self.assertEqual(ledger.read()[1], 1)
            self.assertEqual(ledger.read()[0]['state'], 'open')
        finally: ledger.close()

    def test_transaction_abort_keeps_prior_snapshot(self):
        self.sync(); self.run_exit()
        ledger = c.Ledger(self.home, create=False)
        try:
            # Failure after SQL insert, before commit, must roll back the entire event.
            with patch.object(ledger, 'result', side_effect=RuntimeError('synthetic crash')):
                with self.assertRaises(RuntimeError):
                    ledger.apply(c.read_evidence(self.home, self.wallet, self.pool))
            self.assertEqual(ledger.read()[1], 1)
            self.assertEqual(ledger.read()[0]['state'], 'open')
        finally: ledger.close()

    def test_public_report_excludes_signed_bytes(self):
        self.run_exit()
        text = json.dumps(self.sync())
        for child in (c.submit.CHILD, c.submit.REVERSE_CHILD):
            wire = json.loads((self.home / child / 'signed.json').read_text())['wire']
            self.assertNotIn(wire, text)


if __name__ == '__main__':
    unittest.main()
