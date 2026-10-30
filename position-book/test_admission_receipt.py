"""Same-ledger receipt binding, replay, rollback and refusal tests."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import admission_receipt as m
import pre_sign_admission as admission
from admission_receipt_checks import receipt, failed, unknown, other_vault, run
from locked_admission_checks import fixture, home_fixture, NOW
from contract import digest

HERE = Path(__file__).resolve().parent


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.e, self.p, self.signed = fixture(); self.now = NOW+200
        self.wallet = self.p['scope']['accounts']['wallet']; self.pool = self.p['scope']['accounts']['pool']
        self.home = home_fixture(self.root/'source', self.wallet)
        snapshot = deepcopy(self.e['costInputs']['reservations'])
        snapshot.update(readStartedAtMs=self.now, observedAtMs=self.now)
        with patch.object(admission, 'BASELINE', self.e['costInputs']['baseline']), patch.object(m.handoff.bridge.view, 'read_locked', return_value=snapshot):
            m.handoff.dispatch(self.home, self.wallet, self.pool, self.e, self.p,
                signer_adapter=lambda _: self.signed['signedTransactionBase64'], clock=lambda: self.now)
        self.b = admission.Admission(m.handoff.storage(self.home), clock=lambda: self.now)
        self.g = m.ReceiptGate(self.b)
        self.package = receipt(self.e, self.b.private_accounting_handoff()); self.now = NOW+1100
    def tearDown(self):
        self.b.close(); self.tmp.cleanup()
    def reopen(self):
        self.b.close(); self.b = admission.Admission(m.handoff.storage(self.home), clock=lambda: self.now)
        self.g = m.ReceiptGate(self.b)

    def test_portable_checks_without_network_or_signer(self):
        with patch('socket.socket', side_effect=AssertionError('network')), patch('core.signer', side_effect=AssertionError('signer')):
            r = run()
        self.assertEqual(r['casesPassed'], 14)
        self.assertFalse(r['reservationReleased']); self.assertFalse(r['submissionProvenanceVerified'])

    def test_status_has_no_schema_writes_and_no_second_book(self):
        before = self.b.j.path.read_bytes()
        self.assertEqual(self.g.status()['state'], 'awaiting-receipt')
        self.assertEqual(self.b.j.path.read_bytes(), before)
        self.g.observe(self.package)
        self.assertEqual(len(list(self.b.j.path.parent.glob('*.sqlite'))), 1)
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM intents').fetchone()[0], 0)
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)

    def test_success_reopens_replays_and_does_not_mutate_admission(self):
        before = self.b.status(); r = self.g.observe(self.package)
        self.reopen(); self.assertEqual(r, self.g.status()); self.assertEqual(before, self.b.status())
        self.assertEqual(r['observedAcquiredAtomic'], self.e['costInputs']['price']['quote']['outAmount'])
        self.assertEqual(r['reservedFeeLamports'], '26000')
        self.assertFalse(r['executionApproved']); self.assertFalse(r['reservationReleased'])

    def test_failure_is_fee_only_never_a_fill(self):
        r = self.g.observe(failed(self.package)); self.reopen()
        self.assertEqual(self.g.status(), r); self.assertEqual(r['observedAcquiredAtomic'], '0')
        self.assertEqual(r['observedEntryFeeLamports'], str(self.package['bundle']['rpcEvidence']['transaction']['result']['meta']['fee']))
        self.assertEqual(self.g.observe(failed(self.package)), r)
        self.assertEqual(r['receiptEventCount'], 1)

    def test_missing_receipt_and_missing_transfers_remain_unknown(self):
        for p in (unknown(self.package), deepcopy(self.package)):
            if p['bundle']['rpcEvidence']['transaction']['result']:
                p['bundle']['rpcEvidence']['transaction']['result']['meta']['innerInstructions'] = None
            r = self.g.observe(p)
            self.assertEqual(r['state'], 'receipt-unknown'); self.assertIsNone(r['observedEntryFeeLamports'])
        self.assertEqual(self.g.observe(self.package)['state'], 'entry-effects-observed')

    def test_conflicting_receipt_is_sticky_and_keeps_original_raw(self):
        r = self.g.observe(self.package)
        original = self.b.db.execute('SELECT value FROM admission_receipt_raw').fetchone()[0]
        r = self.g.observe(failed(self.package)); self.assertEqual(r['state'], 'quarantined')
        self.reopen(); self.assertEqual(self.g.observe(self.package), r)
        self.assertEqual(self.b.db.execute('SELECT value FROM admission_receipt_raw').fetchone()[0], original)
        self.assertIsNone(r['observedAcquiredAtomic']); self.assertFalse(r['observedEffectsUsable'])

    def test_changed_wire_or_intent_quarantines_before_audit(self):
        self.package['signedTransactionBase64'] = self.signed['otherSignedTransactionBase64']
        with patch.object(m, 'audit', side_effect=AssertionError('unbound audit')):
            self.assertEqual(self.g.observe(self.package)['state'], 'quarantined')
        self.assertEqual(self.b.status()['reservation']['reservedPrincipalAtomic'], '100')

    def test_generic_compatible_counterparty_is_not_the_admitted_vault(self):
        self.package = other_vault(self.package, self.p['scope'])
        self.assertEqual(m.audit(self.package)['state'], 'signed-token-accounting-consistent')
        self.assertEqual(self.g.observe(self.package)['state'], 'quarantined')

    def test_future_old_or_bool_capture_rejected_without_write(self):
        before = self.b.j.path.read_bytes()
        for at in (True, NOW+199, self.now+1):
            p = deepcopy(self.package); p['bundle']['capturedAtMs'] = at
            with self.assertRaises(ValueError): self.g.observe(p)
            self.assertEqual(self.b.j.path.read_bytes(), before)

    def test_receipts_allowed_after_original_deadline_and_stop(self):
        self.now += 100000; self.b.stop()
        self.assertEqual(self.g.observe(self.package)['state'], 'entry-effects-observed')
        self.assertEqual(self.b.status()['state'], 'stopped')

    def test_regressed_event_clock_refuses(self):
        self.g.observe(self.package); self.now -= 1
        with self.assertRaisesRegex(ValueError, 'receipt-clock-regressed'): self.g.status()

    def test_oversize_evidence_and_event_cap_preserve_existing_state(self):
        before = self.b.j.path.read_bytes(); p = deepcopy(self.package)
        p['padding'] = 'x'*(m.MAX_RECEIPT_BYTES+1)
        with self.assertRaisesRegex(ValueError, 'receipt-size-cap'): self.g.observe(p)
        self.assertEqual(self.b.j.path.read_bytes(), before)
        r = self.g.observe(unknown(self.package))
        with patch.object(m, 'MAX_EVENTS', 1):
            with self.assertRaisesRegex(ValueError, 'receipt-event-cap'): self.g.observe(self.package)
        self.assertEqual(self.g.status(), r)
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM admission_receipt_raw').fetchone()[0], 0)

    def test_write_failure_rolls_back_raw_and_event_together(self):
        before = self.g.observe(unknown(self.package))
        self.b.db.execute("CREATE TRIGGER refuse_receipt BEFORE INSERT ON admission_receipt_events BEGIN SELECT RAISE(ABORT,'injected failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.g.observe(self.package)
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM admission_receipt_raw').fetchone()[0], 0)
        self.assertEqual(self.g.status(), before)
        self.b.db.execute('DROP TRIGGER refuse_receipt')
        self.assertEqual(self.g.observe(self.package)['state'], 'entry-effects-observed')

    def test_changed_raw_replay_and_broken_event_hash_fail_closed(self):
        self.g.observe(self.package)
        raw = self.b.db.execute('SELECT value FROM admission_receipt_raw').fetchone()[0]
        p = json.loads(raw); p['bundle']['rpcEvidence']['transaction']['result']['meta']['postBalances'][0] -= 1
        self.b.db.execute('UPDATE admission_receipt_raw SET value=?', (m.encoded(p),))
        with self.assertRaisesRegex(ValueError, 'receipt-raw-identity'): self.g.status()
        self.b.db.execute('UPDATE admission_receipt_raw SET value=?', (raw,))
        self.b.db.execute("UPDATE admission_receipt_events SET hash='broken'")
        with self.assertRaisesRegex(ValueError, 'receipt-event-integrity'): self.g.status()

    def test_valid_but_different_terminal_replay_is_rejected(self):
        self.g.observe(self.package)
        self.b.db.execute('UPDATE admission_receipt_raw SET value=?', (m.encoded(failed(self.package)),))
        with self.assertRaisesRegex(ValueError, 'receipt-raw-identity'): self.g.status()

    def test_replay_recomputes_effects_even_with_matching_raw_hash(self):
        self.g.observe(self.package)
        value = self.b.db.execute('SELECT * FROM admission_receipt_events').fetchone()
        changed = json.loads(value['value'])
        changed['terminalSummary']['native']['feeLamports'] = '1'
        changed['terminalIdentity'] = digest(changed['terminalSummary'])
        h = digest(dict(seq=1, atMs=value['at_ms'], value=changed, previousHash=''))
        self.b.db.execute('UPDATE admission_receipt_events SET value=?,hash=?', (m.encoded(changed), h))
        with self.assertRaisesRegex(ValueError, 'receipt-raw-replay-conflict'): self.g.status()

    def test_oversized_stored_raw_refused_before_json_decode(self):
        self.g.observe(self.package)
        self.b.db.execute('UPDATE admission_receipt_raw SET value=?', ('x'*(m.MAX_RECEIPT_BYTES+1),))
        with self.assertRaisesRegex(ValueError, 'receipt-raw-required'): self.g.status()

    def test_lock_scope_and_readonly_source_preserved(self):
        before = {p.name: p.read_bytes() for p in self.home.iterdir()}
        original = m.evaluate
        def locked(*args):
            with self.assertRaises(BlockingIOError):
                with m.handoff.bridge.view.cycles.c.source_lock(self.home, self.wallet): pass
            return original(*args)
        with patch.object(m, 'evaluate', side_effect=locked):
            r = m.observe(self.home, self.wallet, self.pool, self.package, clock=lambda: self.now)
        self.assertEqual(r['state'], 'entry-effects-observed')
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.home.iterdir()})
        with self.assertRaisesRegex(ValueError, 'receipt-source-scope'):
            m.observe(self.home, self.wallet, self.wallet, clock=lambda: self.now)

    def test_quarantined_admission_cannot_be_hidden_by_old_receipt(self):
        self.g.observe(self.package)
        self.b.record_signed(self.signed['otherSignedTransactionBase64'])
        with self.assertRaisesRegex(ValueError, 'handoff-not-ready'): self.g.status()

    def test_process_death_after_commit_recovers_without_reapplication(self):
        code = '''import os,sys
from pathlib import Path
from locked_admission_checks import fixture,NOW
from admission_receipt_checks import receipt
from pre_sign_admission import Admission
from admission_receipt import ReceiptGate
e,p,s=fixture()
b=Admission(Path(sys.argv[1]),clock=lambda:NOW+1100)
ReceiptGate(b).observe(receipt(e,b.private_accounting_handoff()))
os._exit(73)
'''
        r = subprocess.run([sys.executable, '-E', '-s', '-c', code, str(self.b.j.path)], cwd=HERE)
        self.assertEqual(r.returncode, 73); self.reopen()
        status = self.g.status(); self.assertEqual(status['state'], 'entry-effects-observed')
        self.assertEqual(self.g.observe(self.package), status); self.assertEqual(status['receiptEventCount'], 1)

    def test_public_reports_exclude_raw_payload_and_keys(self):
        self.package['bundle']['rpcEvidence']['transaction']['result']['meta']['logMessages'] = ['PRIVATE-RAW-MARKER']
        text = json.dumps(self.g.observe(self.package))
        for secret in ('PRIVATE-RAW-MARKER', self.signed['signedTransactionBase64'], 'rpcEvidence', 'receiptIntentTemplate'):
            self.assertNotIn(secret, text)

    def test_cli_only_synthetic_private_exclusive_output(self):
        out = self.root/'check.json.gz'; cmd = [sys.executable, '-E', '-s', str(HERE/'admission_receipt_cli.py'), '--output', str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(gzip.decompress(out.read_bytes()))['casesPassed'], 14)
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)
        before = out.read_bytes(); self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        self.assertEqual(before, out.read_bytes())
        for flag in ('--directory', '--receipt', '--wallet', '--execute', '--allow-devnet-submit'):
            self.assertNotEqual(subprocess.run(cmd+[flag], capture_output=True).returncode, 0)


if __name__ == '__main__': unittest.main()
