"""Submission lifecycle integration, crash recovery and bounded transport tests."""
from copy import deepcopy
import gzip
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import admission_submission as m
from admission_submission_checks import case, FakeOpener, run, NOW
from admission_receipt_checks import failed
from contract import digest
from pre_sign_admission import encoded

HERE=Path(__file__).resolve().parent


class SubmissionTests(unittest.TestCase):
    def test_portable_suite(self):
        r=run();self.assertEqual(r['casesPassed'],18)
        self.assertEqual(r['networkRequests'],0);self.assertEqual(r['transactionsSent'],0)

    def test_no_implicit_optin_or_new_storage(self):
        with patch.object(m.handoff.bridge.view.cycles.c,'source_lock',side_effect=AssertionError('source')):
            for flag in (False,1,'true',None):
                with self.assertRaisesRegex(ValueError,'explicit-devnet-submit-required'):
                    m.submit('/absent','wallet','pool',allow_devnet_submit=flag)

    def test_deadline_consumed_by_rpc_never_crosses_boundary(self):
        with case() as c:
            def expire(method):
                if method=='getFeeForMessage':c.now+=30000
            rpc=FakeOpener(c,callback=expire)
            with self.assertRaisesRegex(ValueError,'submission-not-fresh'):c.submit(rpc)
            self.assertFalse(c.status()['applicationSendBoundaryRecorded'])
            self.assertNotIn('sendTransaction',[q['method'] for q in rpc.requests])

    def test_stop_after_durable_boundary_is_unknown_and_no_retry(self):
        with case() as c:
            mark=m.Submission.mark
            def stopped(book,proof):
                r=mark(book,proof);(c.home/'STOP').touch(mode=0o600);return r
            with patch.object(m.Submission,'mark',stopped):
                with self.assertRaisesRegex(ValueError,'submission-boundary-now-unknown'):c.submit(FakeOpener(c))
            r=c.status();self.assertEqual(r['state'],'submission-unknown')
            rpc=FakeOpener(c);self.assertEqual(c.submit(rpc)['sendRequestsThisRun'],0);self.assertFalse(rpc.requests)

    def test_exception_after_boundary_never_rebroadcasts(self):
        with case() as c:
            def crash(method):
                if method=='sendTransaction':raise RuntimeError('synthetic crash before response')
            with self.assertRaises(RuntimeError):c.submit(FakeOpener(c,callback=crash))
            self.assertEqual(c.status()['state'],'submission-unknown')
            self.assertEqual(c.submit(FakeOpener(c))['sendRequestsThisRun'],0)
            self.assertEqual(c.recover(FakeOpener(c))['state'],'entry-effects-observed')

    def test_real_process_exit_after_boundary_reopens_unknown(self):
        with case() as c:
            code='''import json,os,sys
from pathlib import Path
from pre_sign_admission import Admission
from admission_submission import Submission,GENESIS
from locked_admission_checks import NOW
b=Admission(Path(sys.argv[1]),clock=lambda:NOW+1100)
proof={'genesisBefore':{'state':'received','result':GENESIS['devnet']},'genesisAfter':{'state':'received','result':GENESIS['devnet']},'blockhash':{'state':'received','result':{'context':{'slot':100},'value':True}},'fee':{'state':'received','result':{'context':{'slot':100},'value':5001}}}
Submission(b).mark(proof)
os._exit(73)
'''
            r=subprocess.run([sys.executable,'-E','-s','-c',code,str(c.path)],cwd=HERE,capture_output=True)
            self.assertEqual(r.returncode,73,r.stderr)
            self.assertEqual(c.status()['state'],'submission-unknown')
            self.assertEqual(c.submit(FakeOpener(c))['networkRequestsThisRun'],0)

    def test_competing_sender_cannot_acquire_source_lock(self):
        with case() as c:
            def compete(method):
                if method=='sendTransaction':
                    with self.assertRaises(BlockingIOError):c.submit(FakeOpener(c))
            r=c.submit(FakeOpener(c,callback=compete));self.assertEqual(r['sendRequestsThisRun'],1)

    def test_ack_failure_preserves_boundary_and_never_retries(self):
        with case() as c:
            with patch.object(m.Submission,'acknowledge',side_effect=sqlite3.OperationalError('disk')):
                with self.assertRaises(sqlite3.OperationalError):c.submit(FakeOpener(c))
            self.assertEqual(c.status()['state'],'submission-unknown')
            self.assertEqual(c.submit(FakeOpener(c))['networkRequestsThisRun'],0)

    def test_boundary_commit_failure_never_calls_send(self):
        with case() as c:
            rpc=FakeOpener(c)
            with patch.object(m.Submission,'mark',side_effect=sqlite3.OperationalError('disk')):
                with self.assertRaises(sqlite3.OperationalError):c.submit(rpc)
            self.assertFalse(c.status()['applicationSendBoundaryRecorded'])
            self.assertNotIn('sendTransaction',[q['method'] for q in rpc.requests])

    def test_source_and_admission_reservations_unchanged(self):
        with case() as c:
            before={p.name:p.read_bytes() for p in c.home.iterdir()}
            b=c.book()
            try:admission=b.status()
            finally:b.close()
            c.submit(FakeOpener(c));c.recover(FakeOpener(c))
            self.assertEqual(before,{p.name:p.read_bytes() for p in c.home.iterdir()})
            b=c.book()
            try:self.assertEqual(admission,b.status())
            finally:b.close()
            self.assertEqual(len(list(c.path.parent.glob('*.sqlite'))),1)

    def test_preexisting_imported_receipt_blocks_submission(self):
        with case() as c:
            m.receipts.observe(c.home,c.wallet,c.pool,c.package,clock=lambda:c.now)
            rpc=FakeOpener(c)
            with self.assertRaisesRegex(ValueError,'submission-existing-receipt'):c.submit(rpc)
            self.assertFalse(rpc.requests)
            self.assertFalse(c.status()['genesisBoundReceiptCollected'])

    def test_removed_signer_ack_blocks_send_but_not_recovery(self):
        with case() as c:
            c.submit(FakeOpener(c));(c.path.parent/'signer-ack.json').unlink()
            self.assertEqual(c.recover(FakeOpener(c))['state'],'entry-effects-observed')
        with case() as c:
            (c.path.parent/'signer-ack.json').unlink();rpc=FakeOpener(c)
            with self.assertRaises(OSError):c.submit(rpc)
            self.assertFalse(rpc.requests)

    def test_capture_cap_prevents_more_requests_without_resolving_uncertainty(self):
        with case() as c:
            c.submit(FakeOpener(c));p=deepcopy(c.package);p['bundle']['rpcEvidence']['transaction']['result']=None
            with patch.object(m,'MAX_CAPTURES',2):
                for _ in range(2):c.recover(FakeOpener(c,package=p))
                rpc=FakeOpener(c)
                with self.assertRaisesRegex(ValueError,'collection-cap'):c.recover(rpc)
                self.assertFalse(rpc.requests)
            self.assertFalse(c.status()['genesisBoundReceiptCollected'])

    def test_recovery_does_not_reapply_earlier_unknown_captures(self):
        with case() as c:
            c.submit(FakeOpener(c));p=deepcopy(c.package);p['bundle']['rpcEvidence']['transaction']['result']=None
            for _ in range(m.MAX_CAPTURES):
                c.now+=100
                c.recover(FakeOpener(c,package=p))
            b=c.book()
            try:
                self.assertEqual(m.receipts.ReceiptGate(b).status()['receiptEventCount'],m.MAX_CAPTURES)
                before=b.j.path.read_bytes();m.Submission(b).replay()
                self.assertEqual(before,b.j.path.read_bytes())
            finally:b.close()

    def test_tampered_capture_and_boundary_refuse_before_network(self):
        with case() as c:
            c.submit(FakeOpener(c));c.recover(FakeOpener(c))
            b=c.book()
            try:b.db.execute("UPDATE admission_rpc_captures SET hash='bad'")
            finally:b.close()
            rpc=FakeOpener(c)
            with self.assertRaisesRegex(ValueError,'collection-binding'):c.recover(rpc)
            self.assertFalse(rpc.requests)
        with case() as c:
            c.submit(FakeOpener(c));b=c.book()
            try:
                v=json.loads(b.db.execute('SELECT value FROM admission_submission').fetchone()[0]);v['wireSha256']='0'*64
                b.db.execute('UPDATE admission_submission SET value=?',(encoded(v),))
            finally:b.close()
            with self.assertRaisesRegex(ValueError,'submission-boundary-binding'):c.status()

    def test_future_capture_and_oversized_raw_fail_closed(self):
        with case() as c:
            c.submit(FakeOpener(c));c.recover(FakeOpener(c));b=c.book()
            try:
                v=json.loads(b.db.execute('SELECT value FROM admission_rpc_captures').fetchone()[0]);v['finishedAtMs']=c.now+1
                b.db.execute('UPDATE admission_rpc_captures SET value=?,hash=?',(encoded(v),digest(v)))
            finally:b.close()
            with self.assertRaisesRegex(ValueError,'collection-finish-clock'):c.status()
        with case() as c:
            c.submit(FakeOpener(c));c.recover(FakeOpener(c));b=c.book()
            try:b.db.execute('UPDATE admission_rpc_captures SET value=?',('x'*(m.MAX_CAPTURE_BYTES+1),))
            finally:b.close()
            with self.assertRaisesRegex(ValueError,'collection-record-shape'):c.status()

    def test_older_slot_or_post_genesis_mismatch_quarantines(self):
        with case() as c:
            c.submit(FakeOpener(c));p=deepcopy(c.package);p['bundle']['rpcEvidence']['transaction']['result']['slot']=99
            self.assertEqual(c.recover(FakeOpener(c,package=p))['state'],'quarantined')
        with case() as c:
            c.submit(FakeOpener(c));rpc=FakeOpener(c)
            def change(method):
                if method=='getTransaction':rpc.genesis=m.GENESIS['mainnet-beta']
            rpc.callback=change
            self.assertEqual(c.recover(rpc)['state'],'quarantined')

    def test_conflicting_imported_receipt_does_not_get_collector_provenance(self):
        with case() as c:
            c.submit(FakeOpener(c))
            m.receipts.observe(c.home,c.wallet,c.pool,failed(c.package),clock=lambda:c.now)
            # Capture committed but replay interrupted: status must still compare
            # its exact terminal identity with the existing receipt gate.
            with patch.object(m.Submission,'replay',return_value=None):c.recover(FakeOpener(c))
            self.assertEqual(c.status()['state'],'quarantined')
            self.assertFalse(c.status()['genesisBoundReceiptCollected'])

    def test_network_envelope_errors_are_sanitized(self):
        class Broken:
            def open(self,request,timeout=None):return io.BytesIO(b'{"jsonrpc":"2.0","id":1,"error":{"message":"PRIVATE-MARKER"}}')
        rpc=m.SendRpc(Broken());r=rpc.request('sendTransaction',['fixture',{}])
        self.assertEqual(r,{'state':'rpc-error'})
        with self.assertRaisesRegex(ValueError,'duplicate-send-refused'):rpc.request('sendTransaction',['fixture',{}])
        with self.assertRaises(ValueError):m.ReceiptRpc(Broken()).request('sendTransaction',[])

    def test_request_and_response_caps(self):
        class Huge:
            def open(self,request,timeout=None):return io.BytesIO(b'x'*(4*1024*1024+1))
        rpc=m.ReceiptRpc(Huge())
        for _ in range(4):self.assertEqual(rpc.request('getGenesisHash',[])['state'],'response-too-large')
        with self.assertRaises(ValueError):rpc.request('getGenesisHash',[])

    def test_clock_regression_and_scope_mismatch_refuse(self):
        with case() as c:
            c.submit(FakeOpener(c));c.now-=1
            with self.assertRaisesRegex(ValueError,'submission-clock-regressed'):c.status()
        with case() as c:
            with self.assertRaisesRegex(ValueError,'submission-source-scope'):
                m.recover(c.home,c.wallet,c.wallet,opener=FakeOpener(c),clock=lambda:c.now)

    def test_cli_only_synthetic_exclusive_private_report(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz';cmd=[sys.executable,'-E','-s',str(HERE/'admission_submission_cli.py'),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=out.read_bytes();self.assertEqual(json.loads(gzip.decompress(raw))['casesPassed'],18)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),raw)
            for flag in ('--execute','--directory','--wallet','--allow-devnet-submit','--receipt'):
                self.assertNotEqual(subprocess.run(cmd+[flag],capture_output=True).returncode,0)


class EndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_restricted_signer as fixtures
        fixtures.RealSourceBackendTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):
        import test_restricted_signer as fixtures
        fixtures.RealSourceBackendTests.tearDownClass.__func__(cls)
    def setUp(self):
        import test_restricted_signer as fixtures
        fixtures.RealSourceBackendTests.setUp(self)
    def tearDown(self):
        import test_restricted_signer as fixtures
        fixtures.RealSourceBackendTests.tearDown(self)
    def files(self):
        import test_restricted_signer as fixtures
        return fixtures.RealSourceBackendTests.files(self)
    def evidence(self):
        import test_restricted_signer as fixtures
        return fixtures.RealSourceBackendTests.evidence(self)

    def test_actual_source_signer_to_synthetic_transport_and_receipt(self):
        from types import SimpleNamespace
        from admission_receipt_checks import receipt
        import test_restricted_signer as fixtures
        import pre_sign_admission as admission
        e,p,baseline=fixtures.RealSourceBackendTests.prepare(self)
        before=self.files()
        with patch.object(admission,'BASELINE',baseline),patch('socket.socket',side_effect=AssertionError('network')):
            signed=m.restricted_signer.dispatch(self.home,self.wallet,self.pool,e,p,allow_private_key_signing=True)
            self.assertTrue(signed['accountingHandoffReady'])
            b=admission.Admission(m.handoff.storage(self.home))
            try:
                private=b.private_accounting_handoff();package=receipt(e,private)
            finally:b.close()
            c=SimpleNamespace(e=e,package=package,signed={'signedTransactionBase64':private['signedTransactionBase64']},path=m.handoff.storage(self.home))
            r=m.submit(self.home,self.wallet,self.pool,allow_devnet_submit=True,opener=FakeOpener(c))
            self.assertEqual(r['state'],'rpc-acknowledged');self.assertEqual(r['sendRequestsThisRun'],1)
            r=m.recover(self.home,self.wallet,self.pool,opener=FakeOpener(c))
            self.assertEqual(r['state'],'entry-effects-observed');self.assertTrue(r['genesisBoundReceiptCollected'])
            self.assertFalse(r['reservationReleased']);self.assertFalse(r['executionApproved'])
        self.assertEqual(before,self.files())


if __name__=='__main__':unittest.main()
