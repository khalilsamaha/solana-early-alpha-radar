"""Attempt-only exact signature reuse; state and execution guards remain live."""
import base64
from contextlib import contextmanager
import json
import unittest
from unittest.mock import patch

import fresh_entry as m
from fresh_entry_checks import case
from signature_replay_checks import fixture
import test_fresh_entry as full

wire = m.signing.timing.wire


class ScopeTests(unittest.TestCase):
    def test_shared_phase_counts_are_deltas_and_default_nesting_stays_isolated(self):
        encoded = fixture()
        with wire.signature_verification_scope() as owner:
            wire.verify_wire(encoded)
            with wire.signature_verification_scope(reuse_current=True) as first:
                wire.verify_wire(encoded)
                self.assertEqual(first()['verifierProcesses'], 0)
                self.assertEqual(first()['memoHits'], 1)
                self.assertTrue(first()['sharedWithParent'])
            with wire.signature_verification_scope() as isolated:
                wire.verify_wire(encoded)
                self.assertEqual(isolated()['verifierProcesses'], 1)
            with wire.signature_verification_scope(reuse_current=True) as second:
                wire.verify_wire(encoded)
                self.assertEqual(second()['verificationCalls'], 1)
            self.assertEqual(owner()['verificationCalls'], 3)
            self.assertEqual(owner()['verifierProcesses'], 1)
        self.assertEqual(owner()['memoEntries'], 0)
        self.assertEqual(first()['memoEntries'], 0)
        self.assertIsNone(wire._SIGNATURE_SCOPE.get())

    def test_shared_scope_requires_owner_and_boolean_mode(self):
        for mode in (True, 1, None, 'yes'):
            with self.assertRaises(ValueError):
                with wire.signature_verification_scope(reuse_current=mode): pass
        self.assertIsNone(wire._SIGNATURE_SCOPE.get())

    def test_mutated_bytes_reverified_failures_not_cached_and_capacity_retained(self):
        encoded = fixture()
        with patch.object(wire, 'MAX_SIGNATURE_MEMO', 1), wire.signature_verification_scope() as owner:
            wire.verify_wire(encoded)
            with wire.signature_verification_scope(reuse_current=True) as phase:
                for offset in (1, len(base64.b64decode(encoded))-1):
                    raw = bytearray(base64.b64decode(encoded)); raw[offset] ^= 1
                    for _ in range(2):
                        with self.assertRaises(ValueError): wire.verify_wire(base64.b64encode(raw).decode())
                for _ in range(2): wire.verify_wire(fixture('create'))
                self.assertEqual(phase()['verifierProcesses'], 6)
                self.assertEqual(phase()['capacityBypasses'], 2)
                self.assertEqual(phase()['memoEntries'], 1)
            wire.verify_wire(encoded)
            self.assertEqual(owner()['memoHits'], 1)

    def test_owner_exception_clears_cache_and_next_attempt_cannot_inherit_outer_cache(self):
        encoded = fixture(); captured = []
        @m._attempt_verification
        def fail():
            with wire.signature_verification_scope(reuse_current=True) as phase:
                wire.verify_wire(encoded); captured.append(phase)
                self.assertEqual(phase()['verifierProcesses'], 1)
                raise RuntimeError('test interruption')
        with wire.signature_verification_scope() as outer:
            wire.verify_wire(encoded)
            for _ in range(2):
                with self.assertRaises(RuntimeError): fail()
                self.assertEqual(captured[-1]()['memoEntries'], 0)
            self.assertEqual(outer()['verificationCalls'], 1)
        self.assertIsNone(wire._SIGNATURE_SCOPE.get())

    def test_phase_exception_keeps_owner_then_owner_exit_clears(self):
        with wire.signature_verification_scope() as owner:
            with self.assertRaises(RuntimeError):
                with wire.signature_verification_scope(reuse_current=True):
                    wire.verify_wire(fixture()); raise RuntimeError('phase interrupted')
            wire.verify_wire(fixture())
            self.assertEqual(owner()['memoHits'], 1)
        self.assertEqual(owner()['memoEntries'], 0)


class AttemptGuardTests(unittest.TestCase):
    def test_failed_attempt_and_recovery_do_not_reuse_entry_cache(self):
        with case() as c:
            r = c.run(rpc=c.opener(lost=True))
            self.assertEqual(r['sendRequestsThisRun'], 1)
            self.assertEqual(r['submissionSignatureVerification']['verifierProcesses'], 0)
            self.assertGreater(r['attemptSignatureVerification']['memoHits'], 0)
            self.assertIsNone(wire._SIGNATURE_SCOPE.get())
            recovered = c.recover()
            self.assertGreater(recovered['signatureVerification']['verifierProcesses'], 0)
            self.assertEqual(recovered['sendRequestsThisRun'], 0)
            again = c.run()
            self.assertEqual(again['networkRequests'], 0)
            self.assertIsNone(wire._SIGNATURE_SCOPE.get())

    def test_warmed_source_identity_change_still_blocks_before_rpc(self):
        def change(c, n, result):
            if n == 3: result['ledgerHeadSha256'] = 'd'*64
        with case(read_hook=change) as c:
            r = c.run()
            self.assertEqual(r['diagnosticCode'], 'fresh-entry-source-changed')
            self.assertEqual(r['senderRequests'], 0)
            self.assertFalse(c.transport()['applicationSendBoundaryRecorded'])

    def test_warmed_stop_and_original_expiry_block_send_after_commit(self):
        for kind in ('stop', 'expiry'):
            with self.subTest(kind=kind), case() as c:
                original = m.submission.Submission.mark
                def change(book, proof):
                    value = original(book, proof)
                    if kind == 'stop': (c.home/'STOP').touch(mode=0o600)
                    else: c.now = c.deadline
                    return value
                with patch.object(m.submission.Submission, 'mark', change): r = c.run()
                self.assertEqual(r['sendRequestsThisRun'], 0)
                self.assertEqual(c.transport()['state'], 'submission-unknown')
                self.assertEqual(c.run()['networkRequests'], 0)
                self.assertIsNone(wire._SIGNATURE_SCOPE.get())


class FullSourceTests(unittest.TestCase):
    setUpClass = full.FullSourceEntryTests.__dict__['setUpClass']
    tearDownClass = full.FullSourceEntryTests.__dict__['tearDownClass']
    setUp = full.FullSourceEntryTests.setUp
    tearDown = full.FullSourceEntryTests.tearDown
    files = full.FullSourceEntryTests.files
    pipeline = full.FullSourceEntryTests.pipeline
    integrate = full.FullSourceEntryTests.integrate

    def test_real_pipeline_reduces_processes_without_removing_reads_or_requests(self):
        original_scope = wire.signature_verification_scope
        @contextmanager
        def isolated(*, reuse_current=False):
            with original_scope() as metrics: yield metrics
        read = m.signing.view.read_locked
        with patch.object(wire, 'signature_verification_scope', isolated), \
             patch.object(m.signing.view, 'read_locked', wraps=read) as reads:
            old, _ = self.integrate(lost=True); old_reads = reads.call_count
        other = type(self)(); other.setUp()
        try:
            with patch.object(m.signing.view, 'read_locked', wraps=read) as reads:
                new, _ = other.integrate(lost=True); new_reads = reads.call_count
        finally: other.tearDown()
        for key in ('state', 'networkRequests', 'requestMethods', 'sendRequestsThisRun',
                    'signerInvocationAttempts', 'signerAcknowledgmentValidated',
                    'originalDeadlineCheckedBeforeSend', 'completedWithinOriginalDeadline'):
            self.assertEqual(old[key], new[key], key)
        self.assertEqual(old_reads, new_reads); self.assertGreaterEqual(new_reads, 3)
        a = sum(old[k]['verifierProcesses'] for k in ('signingSignatureVerification', 'submissionSignatureVerification'))
        b = new['attemptSignatureVerification']
        self.assertLess(b['verifierProcesses'], a)
        self.assertEqual(new['submissionSignatureVerification']['verifierProcesses'], 0)
        for key in ('verificationCalls', 'verifierProcesses', 'memoHits', 'capacityBypasses'):
            self.assertEqual(b[key], sum(new[k][key] for k in ('signingSignatureVerification', 'submissionSignatureVerification')))
        self.assertIsNone(wire._SIGNATURE_SCOPE.get())
        print(json.dumps(dict(beforeVerifierProcesses=a, afterVerifierProcesses=b['verifierProcesses'],
            unchangedSourceReads=new_reads, requestAttempts=new['networkRequests'])), flush=True)

    def test_tampered_historical_receipt_after_signing_is_reread_and_refused(self):
        from test_cycle_execution import s, binding
        submit = m.submission.submit
        def tamper(*args, **kw):
            self.assertIsNotNone(wire._SIGNATURE_SCOPE.get())
            (self.home/binding.CYCLE/s.REVERSE_CHILD/'receipt-evidence.json').write_text('{}')
            return submit(*args, **kw)
        # integrate's final preservation assertion must account for our deliberate mutation.
        files = self.files
        def exclude_receipt():
            return {k:v for k,v in files().items() if not str(k).endswith('receipt-evidence.json')}
        with patch.object(self, 'files', exclude_receipt), patch.object(m.submission, 'submit', tamper):
            r, transports = self.integrate()
        self.assertEqual(r['state'], 'fresh-entry-inspection-required')
        self.assertEqual(r['senderRequests'], 0); self.assertEqual(transports, [])
        self.assertIsNone(wire._SIGNATURE_SCOPE.get())


if __name__ == '__main__': unittest.main()
