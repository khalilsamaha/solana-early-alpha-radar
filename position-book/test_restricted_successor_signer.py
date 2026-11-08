"""Saved successor ACK recovery and snapshot semantics; disposable signatures."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import restricted_successor_signer as backend
import successor_signing_handoff as handoff
import test_successor_signing_handoff as source
from core import write_new
from test_signed_exit_timing import files
import admission_recovery as recovery


class SuccessorBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):source.SuccessorSigningTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):source.SuccessorSigningTests.tearDownClass.__func__(cls)
    setUp=source.SuccessorSigningTests.setUp
    def tearDown(self):
        for name in (backend.ATTEMPT,backend.ACK):
            (self.c.path.parent/name).unlink(missing_ok=True)
        source.SuccessorSigningTests.tearDown(self)
    dispatch=source.SuccessorSigningTests.dispatch
    lost=source.SuccessorSigningTests.lost
    status=source.SuccessorSigningTests.status
    rows=source.SuccessorSigningTests.rows
    boundary=source.SuccessorSigningTests.boundary

    def markers(self,wire=None):
        b=self.c.book()
        try:
            r=handoff.successor.row(b);state=handoff.read(b,r,self.c.now)
            row=b.db.execute('SELECT hash,at_ms FROM admission_successor_signing WHERE seq=1').fetchone()
            req=state['request'];wire=wire or self.c.sign_successor(req)
            checked=handoff.original.signed_check(wire,req)
            attempt=dict(format='successor-signer-attempt-1',requestSha256=state['requestSha256'],
                signingHeadSha256=row['hash'],successorSha256=self.candidate,retirementSha256=r['retirementSha256'],atMs=row['at_ms'])
            ack=dict(format='successor-signer-ack-1',requestSha256=state['requestSha256'],
                signedTransactionBase64=wire,wireSha256=checked['wireSha256'])
            write_new(self.c.path.parent/backend.ATTEMPT,attempt);write_new(self.c.path.parent/backend.ACK,ack)
            return attempt,ack
        finally:b.close()

    def recover(self):return backend._recover(self.c.home,self.c.wallet,self.c.pool,self.candidate,clock=lambda:self.c.now)

    def projection(self):
        with handoff.read_only_journals():
            b=self.c.book()
            try:return recovery.retirement_projection(b,self.c.home,self.c.wallet,self.c.pool,lambda:self.c.now)
            finally:b.close()

    def test_opt_in_required_before_key_or_journal_access(self):
        with patch.object(handoff,'_dispatch',side_effect=AssertionError('access')):
            with self.assertRaisesRegex(ValueError,'explicit-successor-private-key-opt-in-required'):
                backend._dispatch('/missing','wallet','pool','hash')

    def test_saved_ack_recovers_after_stop_and_expiry_without_key_or_old_marker_changes(self):
        self.boundary();self.markers();before=self.rows();old={p:b for p,b in files(self.c).items() if 'exit-signer' in p}
        self.c.now+=30000;(self.c.home/'STOP').touch(mode=0o600)
        self.assertFalse((self.c.home/'signer.pk8').exists())
        with patch.object(backend,'_invoke',side_effect=AssertionError('key access')):
            result=self.recover();self.assertEqual(result['state'],'successor-signed-recorded')
            self.assertFalse(result['backendInvokedThisRun']);self.assertFalse(result['privateKeyAccessPossibleThisRun'])
            self.assertTrue(result['evidenceExpired']);self.assertTrue(result['stopRequested'])
            self.assertFalse(result['validForSubmission']);self.assertEqual(result['transactionsSent'],0)
            after=self.rows();self.assertEqual({k:v for k,v in before.items() if k!=handoff.TABLE},
                {k:v for k,v in after.items() if k!=handoff.TABLE})
            saved=files(self.c);self.assertEqual(self.recover()['headSha256'],result['headSha256']);self.assertEqual(saved,files(self.c))
            r=backend._dispatch(self.c.home,self.c.wallet,self.c.pool,self.candidate,
                allow_private_key_signing=True,clock=lambda:self.c.now)
            self.assertFalse(r['backendInvokedThisRun'])
        for p,raw in old.items():self.assertEqual(Path(p).read_bytes(),raw)

    def test_marker_substitution_clock_and_old_generation_rejected(self):
        self.boundary();attempt,ack=self.markers();path=self.c.path.parent/backend.ATTEMPT
        for field,value in [('format','exit-signer-attempt-1'),('requestSha256','0'*64),('signingHeadSha256','0'*64),
                            ('successorSha256','0'*64),('retirementSha256','0'*64),('atMs',self.c.now-1),('atMs',self.c.now+10000)]:
            with self.subTest(field=field,value=value):
                changed=deepcopy(attempt);changed[field]=value;path.write_text(json.dumps(changed));saved=files(self.c)
                with self.assertRaises(ValueError):self.recover()
                self.assertEqual(saved,files(self.c))
        path.write_text(json.dumps(attempt));self.assertEqual(self.recover()['state'],'successor-signed-recorded')

    def test_missing_ack_cannot_sign_again_or_adopt_old_ack(self):
        self.boundary();self.markers();(self.c.path.parent/backend.ACK).unlink()
        saved=files(self.c)
        with patch.object(backend,'_invoke',side_effect=AssertionError('sign again')):
            with self.assertRaises(FileNotFoundError):self.recover()
            result=backend._dispatch(self.c.home,self.c.wallet,self.c.pool,self.candidate,allow_private_key_signing=True,clock=lambda:self.c.now)
            self.assertFalse(result['backendInvokedThisRun']);self.assertEqual(result['state'],'successor-signing-unknown')
        self.assertEqual(saved,files(self.c))

    def test_corrupt_ack_refuses_without_mutating_evidence(self):
        self.boundary();attempt,ack=self.markers();path=self.c.path.parent/backend.ACK
        for field,value in [('format','exit-signer-ack-1'),('requestSha256','0'*64),('wireSha256','0'*64),
                            ('signedTransactionBase64',self.c.exit_wire)]:
            with self.subTest(field=field):
                changed=deepcopy(ack);changed[field]=value;path.write_text(json.dumps(changed));saved=files(self.c)
                with self.assertRaises(ValueError):self.recover()
                self.assertEqual(saved,files(self.c))

    def test_adapter_reads_committed_boundary_and_replays_ack_before_recording(self):
        b=self.c.book()
        try:request=handoff.request_for(handoff.successor.row(b))
        finally:b.close()
        wire=self.c.sign_successor(request);calls=[];original_run=subprocess.run
        def child(cmd,**kwargs):
            if not any(str(arg).endswith('/successor_signer.mjs') for arg in cmd):
                return original_run(cmd,**kwargs)
            calls.append((cmd,kwargs))
            self.assertEqual(kwargs['timeout'],5)
            self.assertEqual(set(kwargs['env']),{'PATH'})
            self.assertEqual(json.loads(kwargs['input']),dict(directory=str(self.c.home),requestSha256=handoff.digest(request)))
            self.markers(wire)
            return subprocess.CompletedProcess(cmd,0,'{"state":"successor-signed-recorded"}','')
        with patch.object(backend.subprocess,'run',side_effect=child):
            r=backend._dispatch(self.c.home,self.c.wallet,self.c.pool,self.candidate,
                allow_private_key_signing=True,clock=lambda:self.c.now)
            self.assertTrue(r['backendInvokedThisRun']);self.assertEqual(r['state'],'successor-signed-recorded')
            self.assertEqual(len(calls),1)
            r=backend._dispatch(self.c.home,self.c.wallet,self.c.pool,self.candidate,
                allow_private_key_signing=True,clock=lambda:self.c.now)
            self.assertFalse(r['backendInvokedThisRun']);self.assertEqual(len(calls),1)

    def test_snapshot_inventory_and_semantic_projection_preserve_markers(self):
        self.boundary();self.markers();saved=files(self.c)
        inv=recovery.admission_inventory(self.c.path.parent)
        self.assertIn(backend.ATTEMPT,inv['files']);self.assertIn(backend.ACK,inv['files'])
        p=self.projection();self.assertTrue(p['successorBackendAttemptPresent']);self.assertTrue(p['successorBackendAcknowledgmentPresent'])
        self.assertEqual(p['successorSigningState'],'successor-signing-unknown');self.assertEqual(saved,files(self.c))
        path=self.c.path.parent/backend.ATTEMPT;v=json.loads(path.read_text());v['successorSha256']='0'*64;path.write_text(json.dumps(v))
        # Updating checksums is not enough: actual source/ACK binding still fails.
        recovery.admission_inventory(self.c.path.parent)
        with self.assertRaisesRegex(ValueError,'successor-signer-attempt-binding'):self.projection()

    def test_orphan_ack_and_symlink_marker_refused(self):
        self.boundary();self.markers();path=self.c.path.parent/backend.ATTEMPT;path.unlink()
        with self.assertRaisesRegex(ValueError,'orphan-successor-signer-ack'):recovery.admission_inventory(self.c.path.parent)
        with self.assertRaises(FileNotFoundError):self.recover()
        path.symlink_to(self.c.path.parent/'exit-signer-attempt.json')
        with self.assertRaises((ValueError,OSError)):self.recover()

    def test_ack_commit_loss_preserves_files_for_keyless_retry(self):
        self.boundary();self.markers();before=files(self.c);append=handoff.append
        def fail(*args):append(*args);raise OSError('synthetic ACK commit loss')
        with patch.object(handoff,'append',side_effect=fail):
            with self.assertRaises(OSError):self.recover()
        self.assertEqual(before,files(self.c));self.assertEqual(self.recover()['state'],'successor-signed-recorded')


if __name__=='__main__':unittest.main()
