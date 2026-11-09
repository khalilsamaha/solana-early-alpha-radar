import base64
import concurrent.futures
from contextlib import closing
import copy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from journal import Journal
from selfcheck import fixture, run, unknown
from wire import Cursor, parse, verify_wire

NOW = 1792240010000
ROOT = Path(__file__).resolve().parent


class WireTests(unittest.TestCase):
    def test_all_public_signed_fixtures(self):
        for name in ('existing', 'create', 'close', 'failed', 'v0', 'multisigner'):
            with self.subTest(name=name):
                p, _ = fixture(name)
                result = verify_wire(p['signedTransactionBase64'])
                self.assertTrue(result['signatureVerified'])
                self.assertEqual(result['canonicalMessageSha256'], p['intent']['messageSha256'])
                self.assertEqual(result['signatures'][0], p['intent']['signature'])

    def test_tampering_signature_or_signed_payload_fails(self):
        raw = base64.b64decode(fixture()[0]['signedTransactionBase64'])
        for at in (1, 20, len(raw) - 1, 80):
            with self.subTest(at=at):
                altered = bytearray(raw); altered[at] ^= 1
                with self.assertRaises(ValueError): verify_wire(base64.b64encode(altered).decode())

    def test_every_required_signer_verified(self):
        raw = bytearray(base64.b64decode(fixture('multisigner')[0]['signedTransactionBase64']))
        raw[65] ^= 1
        with self.assertRaisesRegex(ValueError, 'ed25519'): verify_wire(base64.b64encode(raw).decode())

    def test_zero_signature_not_accepted(self):
        raw = bytearray(base64.b64decode(fixture()[0]['signedTransactionBase64'])); raw[1:65] = bytes(64)
        with self.assertRaisesRegex(ValueError, 'ed25519'): verify_wire(base64.b64encode(raw).decode())

    def test_truncation_trailing_cap_and_base64(self):
        raw = base64.b64decode(fixture()[0]['signedTransactionBase64'])
        for s in ('!', '', base64.b64encode(raw + b'\0').decode(), base64.b64encode(raw[:-1]).decode(),
                  'A' * 1648, fixture()[0]['signedTransactionBase64'] + '\n'):
            with self.subTest(size=len(s)), self.assertRaises(ValueError): verify_wire(s)

    def test_compact_u16_canonical_and_bounds(self):
        for raw in (b'\x80\x00', b'\x81\x00', b'\x80\x80\x00', b'\xff\xff\x04', b'\x80'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): Cursor(raw).count(65535)
        self.assertEqual(Cursor(b'\xff\xff\x03').count(65535), 65535)
        with self.assertRaises(ValueError): Cursor(b'\x80\x01').count(127)

    def test_unsupported_version_and_alt_fail_closed(self):
        raw = bytearray(base64.b64decode(fixture('v0')[0]['signedTransactionBase64']))
        raw[65] = 129
        with self.assertRaisesRegex(ValueError, 'version'): parse(base64.b64encode(raw).decode())
        raw[65] = 128
        raw[-1:] = bytes([1]) + bytes([12]) * 32 + bytes([1, 0, 0])
        with self.assertRaisesRegex(ValueError, 'lookup'): parse(base64.b64encode(raw).decode())

    def test_count_header_and_duplicate_keys(self):
        original = base64.b64decode(fixture()[0]['signedTransactionBase64'])
        for kind in ('count', 'readonly', 'keys'):
            raw = bytearray(original)
            if kind == 'count': raw[65] = 2
            elif kind == 'readonly': raw[66] = 1
            else: raw[101:133] = raw[69:101]
            with self.subTest(kind=kind), self.assertRaises(Exception): parse(base64.b64encode(raw).decode())

    def test_node_environment_is_stripped_and_timeout_bounded(self):
        with patch('wire.subprocess.run') as call:
            call.return_value.returncode = 0; call.return_value.stdout = '{"valid":true}'
            with patch.dict(os.environ, {'NODE_OPTIONS': '--require malicious'}):
                verify_wire(fixture()[0]['signedTransactionBase64'])
            self.assertEqual(call.call_args.kwargs['timeout'], 5)
            self.assertNotIn('NODE_OPTIONS', call.call_args.kwargs['env'])
            self.assertNotIn('shell', call.call_args.kwargs)


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'journal.sqlite'
        self.j = Journal(self.path, lambda: NOW)
        self.p, self.b = fixture()

    def tearDown(self):
        self.j.close(); self.tmp.cleanup()

    def prepare(self):
        self.j.register(self.p)
        self.j.mark_submission_boundary('existing')

    def reopen(self):
        self.j.close(); self.j = Journal(self.path, lambda: NOW)

    def test_private_persistent_registration_without_raw_wire(self):
        first = self.j.register(self.p); self.reopen()
        self.assertEqual(first, self.j.result('existing'))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(self.p['signedTransactionBase64'].encode(), self.path.read_bytes())

    def test_registration_retry_preserves_state_and_event_count(self):
        self.prepare()
        a = self.j.result('existing')
        self.assertEqual(a, self.j.register(self.p))

    def test_same_id_cannot_replace_signed_transaction(self):
        self.j.register(self.p)
        other, _ = fixture('create', 'existing')
        with self.assertRaisesRegex(ValueError, 'conflict'): self.j.register(other)
        self.assertEqual(self.j.result('existing')['eventCount'], 1)

    def test_signature_cannot_register_under_new_id_or_network(self):
        self.j.register(self.p)
        other = copy.deepcopy(self.p); other['logicalIntentId'] = 'another'
        for network in ('devnet', 'mainnet-beta'):
            other['intent']['network'] = network
            with self.subTest(network=network), self.assertRaisesRegex(ValueError, 'duplicate'):
                self.j.register(other)

    def test_signed_bytes_must_match_declared_intent(self):
        for field in ('wallet', 'signature', 'messageSha256'):
            p = copy.deepcopy(self.p)
            replacement = fixture('create')[0]['intent'][field]
            p['intent'][field] = replacement
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'binding'): self.j.register(p)

    def test_boundary_is_one_time_and_survives_reopen(self):
        self.prepare(); self.reopen()
        self.assertEqual(self.j.result('existing')['state'], 'submission-unknown')
        with self.assertRaisesRegex(ValueError, 'already'): self.j.mark_submission_boundary('existing')

    def test_receipt_cannot_precede_boundary(self):
        self.j.register(self.p)
        with self.assertRaisesRegex(ValueError, 'not-recorded'): self.j.observe('existing', self.b)

    def test_unknown_survives_restart_and_later_reconciles(self):
        self.prepare(); self.j.observe('existing', unknown(self.b)); self.reopen()
        self.assertEqual(self.j.result('existing')['state'], 'submission-unknown')
        self.assertEqual(self.j.observe('existing', self.b)['state'], 'reconciled')

    def test_unknown_after_final_does_not_erase_final_receipt(self):
        self.prepare(); self.j.observe('existing', self.b)
        self.assertEqual(self.j.observe('existing', unknown(self.b))['state'], 'reconciled')
        self.assertEqual(self.j.observe('existing', self.b)['state'], 'reconciled')

    def test_exact_receipt_retry_is_idempotent(self):
        self.prepare(); a = self.j.observe('existing', self.b)
        self.assertEqual(a, self.j.observe('existing', self.b))

    def test_debit_mismatch_quarantine_is_sticky(self):
        self.prepare()
        b = copy.deepcopy(self.b); b['rpcEvidence']['transaction']['result']['meta']['postBalances'][0] -= 1
        self.assertEqual(self.j.observe('existing', b)['state'], 'quarantined')
        self.reopen()
        self.assertEqual(self.j.observe('existing', self.b)['state'], 'quarantined')

    def test_changed_final_evidence_quarantined(self):
        self.prepare(); self.j.observe('existing', self.b)
        b = copy.deepcopy(self.b)
        b['rpcEvidence']['transaction']['result']['meta']['postTokenBalances'][1]['uiTokenAmount']['amount'] = '201'
        self.assertEqual(self.j.observe('existing', b)['state'], 'quarantined')

    def test_new_capture_time_and_context_do_not_conflict(self):
        self.prepare(); self.j.observe('existing', self.b)
        b = copy.deepcopy(self.b); b['capturedAtMs'] += 100
        b['rpcEvidence']['signatureStatus']['result']['context']['slot'] += 100
        self.assertEqual(self.j.observe('existing', b)['state'], 'reconciled')

    def test_status_cannot_create_missing_database(self):
        missing = Path(self.tmp.name) / 'absent.sqlite'
        with self.assertRaisesRegex(ValueError, 'not-found'): Journal(missing, create=False)
        self.assertFalse(missing.exists())

    def test_extra_signature_vector_change_rejected(self):
        p, b = fixture('multisigner')
        self.j.register(p); self.j.mark_submission_boundary('multisigner')
        b['rpcEvidence']['transaction']['result']['transaction']['signatures'][1] = p['intent']['signature']
        self.assertEqual(self.j.observe('multisigner', b)['state'], 'quarantined')

    def test_receipt_intent_replacement_leaves_original_unchanged(self):
        self.prepare(); before = self.j.result('existing')
        b = copy.deepcopy(self.b); b['intent']['minimumOutputAtomic'] = '1'
        with self.assertRaisesRegex(ValueError, 'conflict'): self.j.observe('existing', b)
        self.assertEqual(self.j.result('existing'), before)

    def test_all_flags_remain_nonexecuting(self):
        self.prepare()
        for result in (self.j.result('existing'), self.j.observe('existing', self.b)):
            for key in ('executionApproved', 'resubmitAllowed', 'productionLedgerUpdated'): self.assertIs(result[key], False)
            self.assertEqual(result['networkRequests'], 0)

    def test_clock_rollback_and_future_intent_fail(self):
        with patch.object(self.j, 'clock', return_value=1):
            with self.assertRaisesRegex(ValueError, 'future'): self.j.register(self.p)
        self.j.register(self.p)
        with patch.object(self.j, 'clock', return_value=NOW - 1):
            with self.assertRaisesRegex(ValueError, 'regressed'): self.j.mark_submission_boundary('existing')

    def test_event_cap_rolls_back_state_update(self):
        self.j.register(self.p)
        with patch('journal.MAX_EVENTS', 1):
            with self.assertRaisesRegex(ValueError, 'cap'): self.j.mark_submission_boundary('existing')
        self.assertEqual(self.j.result('existing')['state'], 'prepared')

    def test_concurrent_registration_is_single_and_boundary_only_once(self):
        def register(_):
            j = Journal(self.path, lambda: NOW)
            try: return j.register(self.p)
            finally: j.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(register, range(2)))
        self.assertEqual(results[0], results[1]); self.assertEqual(results[0]['eventCount'], 1)
        def boundary(_):
            j = Journal(self.path, lambda: NOW)
            try:
                try: return j.mark_submission_boundary('existing')['state']
                except ValueError: return 'rejected'
            finally: j.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(boundary, range(2)))
        self.assertEqual(sorted(results), ['rejected', 'submission-unknown'])

    def test_process_death_after_boundary_preserves_unknown(self):
        self.j.register(self.p)
        code = 'from journal import Journal; import os,sys; j=Journal(sys.argv[1],lambda:1792240010000); j.mark_submission_boundary("existing"); os._exit(9)'
        p = subprocess.run([sys.executable, '-c', code, str(self.path)], cwd=ROOT, capture_output=True)
        self.assertEqual(p.returncode, 9)
        self.reopen(); self.assertEqual(self.j.result('existing')['state'], 'submission-unknown')

    def test_process_death_before_commit_rolls_back(self):
        self.j.register(self.p)
        code = 'import sqlite3,os,sys; d=sqlite3.connect(sys.argv[1]); d.execute("BEGIN IMMEDIATE"); d.execute("UPDATE intents SET state=\'submission-unknown\'"); os._exit(9)'
        p = subprocess.run([sys.executable, '-c', code, str(self.path)], capture_output=True)
        self.assertEqual(p.returncode, 9)
        self.reopen(); self.assertEqual(self.j.result('existing')['state'], 'prepared')

    def test_insecure_directory_symlink_hardlink_and_foreign_database_refused(self):
        link = Path(self.tmp.name) / 'link.sqlite'; link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, 'unsafe'): Journal(link)
        link.unlink(); os.link(self.path, link)
        with self.assertRaisesRegex(ValueError, 'unsafe'): Journal(link)
        link.unlink()
        foreign = Path(self.tmp.name) / 'foreign.sqlite'
        with closing(sqlite3.connect(foreign)) as db, db: db.execute('CREATE TABLE other(x)')
        foreign.chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'unrecognized'): Journal(foreign)
        Path(self.tmp.name).chmod(0o755)
        try:
            with self.assertRaisesRegex(ValueError, '0700'): Journal(self.path)
        finally: Path(self.tmp.name).chmod(0o700)

    def test_selfcheck_and_cli_are_private_offline_and_exclusive(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            result = run()
        self.assertEqual(result['casesPassed'], 11)
        self.assertTrue(result['temporaryJournalRemoved'])
        output = Path(self.tmp.name) / 'report.json.gz'
        command = [sys.executable, str(ROOT / 'intent_journal_cli.py'), '--output', str(output)]
        p = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        before = output.read_bytes(); self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        p = subprocess.run(command, text=True, capture_output=True)
        self.assertNotEqual(p.returncode, 0); self.assertEqual(before, output.read_bytes())


if __name__ == '__main__': unittest.main()
