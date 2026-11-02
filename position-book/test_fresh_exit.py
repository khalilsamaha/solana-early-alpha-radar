"""Fresh exit composition, failure boundaries and the actual isolated backend."""
from copy import deepcopy
import gzip,json,sqlite3,subprocess,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import fresh_exit as m
from fresh_exit_checks import case,run
import test_restricted_exit_signer as source

class FreshExitTests(unittest.TestCase):
    def test_portable_suite(self):self.assertEqual(run()['casesPassed'],21)
    def test_cli_exclusive_private_offline(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz';cmd=[sys.executable,'-E','-s',str(Path(__file__).with_name('fresh_exit_cli.py')),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=out.read_bytes();self.assertEqual(json.loads(gzip.decompress(raw))['casesPassed'],21)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),raw)
            for flag in ('--action','--directory','--wallet','--allow-private-key-signing','--allow-devnet-submit'):
                other=Path(d)/'absent.gz';self.assertNotEqual(subprocess.run(cmd[:-1]+[str(other),flag],capture_output=True).returncode,0);self.assertFalse(other.exists())
    def test_shared_collection_budget(self):
        with case() as c:
            c.collector.hook=lambda n,q,o:setattr(c,'mono',29) if n==20 else None
            def change(method):
                if method=='getGenesisHash':c.mono=30
            r=c.run(rpc=c.opener(callback=change));self.assertEqual(r['senderRequests'],1);self.assertEqual(r['sendRequestsThisRun'],0)
            self.assertEqual(r['diagnosticCode'],'fresh-signing-monotonic')
    def test_collection_count_survives_write_failure(self):
        with case() as c,patch.object(m.collection.exit,'prepare',side_effect=sqlite3.OperationalError('PRIVATE')):
            r=c.run();self.assertEqual(r['collectionRequests'],20);self.assertEqual(c.signs,0);self.assertNotIn('PRIVATE',json.dumps(r))
    def test_boundary_and_ack_failures(self):
        for method,sends in [('mark',0),('acknowledge',1)]:
            with case() as c,patch.object(m.submission.ExitSubmission,method,side_effect=sqlite3.OperationalError('PRIVATE')):
                r=c.run();self.assertEqual(r['sendRequestsThisRun'],sends);self.assertIsNone(r['applicationSendBoundaryRecorded'])
                self.assertNotIn('PRIVATE',json.dumps(r));self.assertEqual(c.run()['networkRequests'],0)
    def test_stop_after_boundary(self):
        with case() as c:
            mark=m.submission.ExitSubmission.mark
            def stop(*args):r=mark(*args);(c.home/'STOP').touch(mode=0o600);return r
            with patch.object(m.submission.ExitSubmission,'mark',stop):r=c.run()
            self.assertEqual(r['sendRequestsThisRun'],0);self.assertEqual(c.status()['state'],'exit-submission-unknown')
    def test_mutated_sender_identity(self):
        with case() as c:
            submit=m.submission.submit
            def mutate(*args,**kw):
                guard=kw['_guard']
                def changed(stage,state):
                    state=deepcopy(state);state['request']['validUntilExclusiveMs']+=1;guard(stage,state)
                return submit(*args,**dict(kw,_guard=changed))
            with patch.object(m.submission,'submit',mutate):r=c.run()
            self.assertEqual(r['diagnosticCode'],'fresh-exit-identity');self.assertEqual(r['senderRequests'],0)
    def test_recovery_without_send_never_resumes(self):
        with case() as c:
            c.run(rpc=c.opener(valid=False))
            with patch.object(m.collection,'collect_and_prepare',side_effect=AssertionError('collect')),patch.object(m.backend,'_invoke',side_effect=AssertionError('sign')):
                r=c.recover();self.assertEqual(r['state'],'not-attempted');self.assertEqual(r['networkRequestsThisRun'],0);self.assertFalse(r['resumesExit'])

    def test_before_signing_budget_and_stop(self):
        for kind in ('budget','stop'):
            with case() as c:
                def hook(n,q,o):
                    if n!=20:return
                    if kind=='budget':c.mono=30
                    else:(c.home/'STOP').touch(mode=0o600)
                c.collector.hook=hook
                r=c.run();self.assertEqual(c.signs,0);self.assertEqual(r['senderRequests'],0)
    def test_unknown_signer_exception_is_sanitized(self):
        with case() as c:
            def lost(root,request):raise OSError('PRIVATE SECRET')
            r=c.run(adapter=lost);self.assertIsNone(r['privateKeyAccessed']);self.assertIsNone(r['signaturesCreated'])
            self.assertEqual(r['senderRequests'],0);self.assertNotIn('PRIVATE SECRET',json.dumps(r))
    def test_orphan_backend_marker_refuses_collection(self):
        with case() as c:
            (c.path.parent/m.backend.ATTEMPT).write_text('{}')
            r=c.run();self.assertEqual(r['diagnosticCode'],'fresh-exit-slot-occupied')
            self.assertEqual(r['networkRequests'],0);self.assertEqual(c.signs,0)

class ActualBackendTests(unittest.TestCase):
    setUpClass=source.IntegratedBackendTests.__dict__['setUpClass']
    tearDownClass=source.IntegratedBackendTests.__dict__['tearDownClass']
    setUp=source.IntegratedBackendTests.setUp
    tearDown=source.IntegratedBackendTests.tearDown
    clock=source.IntegratedBackendTests.clock
    submit=source.IntegratedBackendTests.submit
    collect=source.IntegratedBackendTests.collect
    settle=source.IntegratedBackendTests.settle
    capture=source.IntegratedBackendTests.capture
    verify=source.IntegratedBackendTests.verify
    source_bytes=source.IntegratedBackendTests.source_bytes
    edit_db=source.IntegratedBackendTests.edit_db
    def test_actual_backend_one_send_and_keyless_recovery(self):
        from test_admission_exit_recovery import delayed
        from admission_exit_capture_checks import Opener
        from exit_submission_checks import FakeRpc
        self.collect();accounting=self.settle()['accounting'];self.stamp=m.view.now()
        e=delayed(self.e['costInputs']['capture'],accounting,self.stamp)
        raw=e['initialPool'];first=deepcopy(e['capture'])
        first.update(packet=None,selection='explicit-pool',accountKeys=raw['accountKeys']+[first['accountKeys'][-1]])
        programdata=deepcopy(first['evidence']['accounts']['result']['value'][-1])
        first['evidence']['accounts']=deepcopy(raw['evidence']['accounts']);first['evidence']['accounts']['result']['value'].append(programdata)
        first['evidence']['poolBootstrap']=deepcopy(raw['evidence']['bootstrap'])
        first['evidence']['programBootstrap']['result']['context']['slot']=first['evidence']['poolBootstrap']['result']['context']['slot']
        for name in ('genesisBefore','genesisAfter','blockTime'):first['evidence'][name]=deepcopy(raw['evidence'][name])
        first['evidence']['blockhash']={'state':'not-requested'};first['evidence']['fee']={'state':'not-requested'}
        baseline=deepcopy(self.e['costInputs']['baseline']);baseline.update(kind='observed-devnet-deployment',observedAtMs=0)
        key=self.home/'signer.pk8';key.write_bytes(self.ephemeral_exit_key);key.chmod(0o600)
        before={str(p):p.read_bytes() for p in self.home.rglob('*') if p.is_file()};transports=[];test=self
        class Lazy:
            def open(self,request,timeout=None):
                if not transports:
                    b=m.submission.transport._open(test.home,test.wallet,test.pool,m.view.now)
                    try:
                        state=m.submission.ExitSubmission(b).signing()
                        c=SimpleNamespace(exit_state=state,exit_wire=state['signed']['signedWireBase64'],path=b.j.path,signed={})
                    finally:b.close()
                    transports.append(FakeRpc(c,lost=True))
                return transports[0].open(request,timeout)
        with patch.object(m.collection.exit,'BASELINE',baseline),patch('socket.socket',side_effect=AssertionError('network')):
            r=m.prepare_sign_submit(self.home,self.wallet,self.pool,allow_private_key_signing=True,allow_devnet_submit=True,
                collection_opener=Opener(first,e),submission_opener=Lazy(),clock=m.view.now)
            self.assertEqual(r['state'],'exit-submission-unknown',r);self.assertEqual(r['networkRequests'],25)
            self.assertTrue(r['privateKeyAccessed']);self.assertEqual(r['signaturesCreated'],1);self.assertTrue(r['completedWithinOriginalDeadline'])
            self.assertEqual(before,{str(p):p.read_bytes() for p in self.home.rglob('*') if p.is_file()});key.unlink();(self.home/'STOP').touch(mode=0o600);self.stamp=m.view.now()+30000
            with patch.object(m.backend,'_invoke',side_effect=AssertionError('sign')):
                r=m.recover(self.home,self.wallet,self.pool,opener=transports[0],clock=self.clock)
            self.assertEqual(r['state'],'exit-finalized-evidence');self.assertFalse(r['reservationReleased']);self.assertEqual(r['sendRequestsThisRun'],0)
            self.assertEqual(sum(x['method']=='sendTransaction' for x in transports[0].requests),1)

if __name__=='__main__':unittest.main()
