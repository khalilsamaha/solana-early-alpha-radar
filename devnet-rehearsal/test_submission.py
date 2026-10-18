import gzip,json,os,sqlite3,subprocess,sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import core
from rehearsal_fixtures import FakeRpc
from submission_fixtures import SubmissionRpc
from submission import execute,recover,stop,Lifecycle,SubmitRpc,RecoveryRpc
HERE=Path(__file__).resolve().parent

class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)/'wallet'; self.wallet=core.initialize(self.home)['wallet']
        core.prepare(self.home,FakeRpc())
    def run_case(self,mode='ok',**kw):
        rpc=SubmissionRpc(self.home,mode,**kw)
        r=execute(self.home,self.wallet,opener=rpc,sleeper=lambda _:None)
        return r,rpc
    def test_send_boundary_options_and_reconciled_fee(self):
        r,rpc=self.run_case()
        self.assertEqual(r['state'],'finalized-success'); self.assertEqual(r['submissionAttempts'],1)
        send=[p for p in rpc.calls if p['method']=='sendTransaction']; self.assertEqual(len(send),1)
        self.assertEqual(send[0]['params'][1],{'encoding':'base64','skipPreflight':False,'preflightCommitment':'finalized','maxRetries':0,'minContextSlot':100})
        self.assertEqual(r['receipt']['feeLamports'],5000)
        self.assertEqual(r['receipt']['walletAfterLamports'],'995000')
        self.assertNotIn('private-error-marker',json.dumps(r)); self.assertNotIn(send[0]['params'][0],json.dumps(r))
    def test_repeated_execute_makes_no_requests(self):
        self.run_case(); r,rpc=self.run_case(); self.assertEqual(rpc.calls,[])
        self.assertEqual(r['submissionAttempts'],1)
    def test_timeout_is_observed_not_resent(self):
        r,rpc=self.run_case('timeout'); self.assertEqual(r['state'],'finalized-success')
        self.assertEqual(sum(p['method']=='sendTransaction' for p in rpc.calls),1)
    def test_send_rpc_error_does_not_authorize_retry(self):
        r,rpc=self.run_case('rejected'); self.assertEqual(r['state'],'finalized-success')
        self.assertFalse(r['resubmitAllowed']); self.assertNotIn('private-error-marker',json.dumps(r))
    def test_wrong_acknowledgement_quarantines(self):
        r,rpc=self.run_case('wrong-signature'); self.assertEqual(r['state'],'quarantined')
        other=SubmissionRpc(self.home); r=recover(self.home,self.wallet,opener=other)
        self.assertEqual(other.calls,[]); self.assertEqual(r['state'],'quarantined')
    def test_receipt_contradictions_quarantine(self):
        for mode in ('wrong-wire','wrong-slot','bad-balance','bad-fee'):
            with self.subTest(mode=mode):
                home=Path(self.tmp.name)/mode; wallet=core.initialize(home)['wallet']; core.prepare(home,FakeRpc())
                r=execute(home,wallet,opener=SubmissionRpc(home,mode),sleeper=lambda _:None)
                self.assertEqual(r['state'],'quarantined')
    def test_missing_receipt_evidence_stays_unknown(self):
        for mode in ('missing-receipt','missing-balances'):
            with self.subTest(mode=mode):
                home=Path(self.tmp.name)/mode; wallet=core.initialize(home)['wallet']; core.prepare(home,FakeRpc())
                r=execute(home,wallet,opener=SubmissionRpc(home,mode),sleeper=lambda _:None)
                self.assertEqual(r['state'],'submission-unknown'); self.assertFalse(r['resubmitAllowed'])
    def test_finalized_failure_retains_actual_fee(self):
        r,rpc=self.run_case('final-failed'); self.assertEqual(r['state'],'finalized-failure')
        self.assertEqual(r['receipt']['feeLamports'],5000); self.assertNotIn('private-error-marker',json.dumps(r))
    def test_pending_polling_is_bounded(self):
        sleeps=[]; rpc=SubmissionRpc(self.home,'pending')
        r=execute(self.home,self.wallet,opener=rpc,sleeper=sleeps.append)
        self.assertEqual(r['state'],'submission-pending'); self.assertEqual(sleeps,[10,10])
        self.assertEqual(sum(p['method']=='sendTransaction' for p in rpc.calls),1)
        self.assertLessEqual(r['networkRequests'],30)
    def test_expired_unknown_after_boundary_never_renews(self):
        with Lifecycle(self.home) as s: s.boundary(s.plan())
        rpc=SubmissionRpc(self.home,'absent',expired=True)
        r=recover(self.home,self.wallet,opener=rpc,sleeper=lambda _:None)
        self.assertEqual(r['state'],'expired-outcome-unknown'); self.assertEqual(len(r['plans']),1)
        rpc2=SubmissionRpc(self.home,expired=True)
        r=execute(self.home,self.wallet,allow_replace=True,opener=rpc2)
        self.assertEqual(rpc2.calls,[]); self.assertEqual(len(r['plans']),1)
    def test_expired_plan_requires_explicit_opt_in(self):
        r,rpc=self.run_case(expired=True)
        self.assertEqual(r['state'],'not-submitted'); self.assertEqual(len(r['plans']),1)
        self.assertNotIn('sendTransaction',[p['method'] for p in rpc.calls])
    def test_explicit_replacement_preserves_old_plan(self):
        rpc=SubmissionRpc(self.home,expired=True)
        r=execute(self.home,self.wallet,allow_replace=True,opener=rpc,sleeper=lambda _:None)
        self.assertEqual(r['state'],'finalized-success'); self.assertEqual(r['planId'],2)
        self.assertEqual(r['plans'][0]['state'],'expired-unsubmitted')
        self.assertEqual(r['plans'][0]['result']['state'],'simulation-passed-not-submitted')
        self.assertNotEqual(r['plans'][0]['result']['signature'],r['plans'][1]['result']['signature'])
        self.assertEqual(len(r['preparationRequests']),6)
        with core.Session(self.home) as s: self.assertEqual(len(s.status()['plans']),2)
        with self.assertRaises(ValueError): core.prepare(self.home,FakeRpc())
    def test_old_signature_already_observed_blocks_send_and_renewal(self):
        r,rpc=self.run_case('already-seen',expired=True)
        self.assertEqual(r['state'],'quarantined'); self.assertEqual(r['submissionAttempts'],0)
        self.assertEqual(len(r['plans']),1)
    def test_existing_receipt_blocks_replacement(self):
        rpc=SubmissionRpc(self.home,'existing-receipt',expired=True)
        r=execute(self.home,self.wallet,allow_replace=True,opener=rpc)
        self.assertEqual(r['state'],'quarantined'); self.assertEqual(r['submissionAttempts'],0)
    def test_wrong_cluster_or_unavailable_height_never_sends(self):
        for mode in ('wrong-cluster','height-error','near-expiry'):
            r,rpc=self.run_case(mode)
            self.assertEqual(r['state'],'not-submitted'); self.assertEqual(r['submissionAttempts'],0)
            self.assertNotIn('sendTransaction',[p['method'] for p in rpc.calls])
    def test_wallet_argument_bound_before_rpc(self):
        rpc=SubmissionRpc(self.home)
        with self.assertRaises(ValueError): execute(self.home,core.SYSTEM,opener=rpc)
        self.assertEqual(rpc.calls,[])
    def test_stop_before_execute_and_after_boundary(self):
        original=Lifecycle.boundary
        def stop_after(s,p): original(s,p); stop(s.home)
        rpc=SubmissionRpc(self.home)
        with patch.object(Lifecycle,'boundary',stop_after): r=execute(self.home,self.wallet,opener=rpc)
        self.assertEqual(r['submissionAttempts'],1); self.assertEqual(r['reason'],'stopped-after-boundary-no-send')
        self.assertNotIn('sendTransaction',[p['method'] for p in rpc.calls])
        with core.Session(self.home): stop(self.home) # independent stop works while lock is held
        rpc2=SubmissionRpc(self.home,sent=True); r=recover(self.home,self.wallet,opener=rpc2)
        self.assertEqual(r['state'],'finalized-success')
    def test_stop_with_no_boundary_makes_no_requests(self):
        stop(self.home); r,rpc=self.run_case(); self.assertEqual(rpc.calls,[])
        self.assertEqual(r['submissionAttempts'],0)
    def test_recovery_transport_cannot_send_or_sign(self):
        rpc=RecoveryRpc(SubmissionRpc(self.home))
        for m in ('sendTransaction','simulateTransaction','requestAirdrop','getLatestBlockhash'):
            with self.assertRaises(ValueError): rpc.request(m,[])
        self.assertEqual(rpc.calls,[])
    def test_invalid_saved_message_rejected(self):
        with sqlite3.connect(self.home/'rehearsal.sqlite') as db:
            db.execute("UPDATE plans SET signed_wire='bad'")
        r,rpc=self.run_case(); self.assertEqual(rpc.calls,[]); self.assertEqual(r['submissionAttempts'],0)
    def test_abrupt_exit_after_boundary_recovers_without_send(self):
        script="""import sys,os
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from submission import Lifecycle
with Lifecycle(Path(sys.argv[2])) as s:
 s.boundary(s.plan())
 os._exit(77)
"""
        p=subprocess.run([sys.executable,'-c',script,str(HERE),str(self.home)],capture_output=True,text=True)
        self.assertEqual(p.returncode,77,p.stderr)
        rpc=SubmissionRpc(self.home,sent=True); r=recover(self.home,self.wallet,opener=rpc)
        self.assertEqual(r['state'],'finalized-success')
        self.assertNotIn('sendTransaction',[p['method'] for p in rpc.calls])
    def test_database_failure_at_boundary_prevents_transport(self):
        rpc=SubmissionRpc(self.home)
        with patch.object(Lifecycle,'boundary',side_effect=sqlite3.OperationalError('disk full')):
            with self.assertRaises(sqlite3.OperationalError): execute(self.home,self.wallet,opener=rpc)
        self.assertNotIn('sendTransaction',[p['method'] for p in rpc.calls])
    def test_concurrent_execute_blocked_by_session_lock(self):
        rpc=SubmissionRpc(self.home)
        with Lifecycle(self.home):
            with self.assertRaises(BlockingIOError): execute(self.home,self.wallet,opener=rpc)
        self.assertEqual(rpc.calls,[])
    def test_cli_requires_explicit_submit_and_wallet(self):
        output=Path(self.tmp.name)/'report.gz'
        p=subprocess.run([sys.executable,str(HERE/'submission_cli.py'),'--action','execute',
            '--directory',str(self.home),'--wallet',self.wallet,'--output',str(output)],capture_output=True)
        self.assertNotEqual(p.returncode,0); self.assertFalse(output.exists())
    def test_expiry_decision_cannot_regress_into_old_send(self):
        with Lifecycle(self.home) as session:
            session.expire(session.plan(),{'blockHeight':130})
        r,rpc=self.run_case()
        self.assertEqual(r['reason'],'expired-plan-height-regressed')
        self.assertNotIn('sendTransaction',[p['method'] for p in rpc.calls])
    def test_second_expired_plan_never_creates_third(self):
        with Lifecycle(self.home) as session: session.expire(session.plan(),{'blockHeight':130})
        rpc=SubmissionRpc(self.home)
        core.prepare(self.home,rpc,replace_expired=True)
        class ExpiredAgain(SubmissionRpc):
            def open(this,request,timeout):
                import io
                p=json.loads(request.data)
                if p['method']=='getBlockHeight':
                    this.calls.append(p)
                    return io.BytesIO(json.dumps({'jsonrpc':'2.0','id':p['id'],'result':300}).encode())
                return super().open(request,timeout)
        rpc=ExpiredAgain(self.home)
        r=execute(self.home,self.wallet,allow_replace=True,opener=rpc)
        self.assertEqual(len(r['plans']),2); self.assertEqual(r['submissionAttempts'],0)
        self.assertNotIn('sendTransaction',[p['method'] for p in rpc.calls])
    def test_replacement_failure_preserved_no_send_or_third_plan(self):
        rpc=SubmissionRpc(self.home,expired=True); rpc.base.mode='missing-balances'
        r=execute(self.home,self.wallet,allow_replace=True,opener=rpc)
        self.assertEqual(r['reason'],'replacement-preparation-incomplete')
        self.assertEqual(r['plans'][1]['state'],'preparation-incomplete')
        self.assertEqual(len(r['plans']),2); self.assertEqual(r['submissionAttempts'],0)
        rpc2=SubmissionRpc(self.home)
        again=execute(self.home,self.wallet,allow_replace=True,opener=rpc2)
        self.assertEqual(rpc2.calls,[]); self.assertEqual(len(again['plans']),2)
    def test_crash_after_transport_preserves_boundary(self):
        class CrashAfterSend(SubmissionRpc):
            def open(this,request,timeout):
                response=super().open(request,timeout)
                if json.loads(request.data)['method']=='sendTransaction': raise SystemExit(77)
                return response
        rpc=CrashAfterSend(self.home)
        with self.assertRaises(SystemExit): execute(self.home,self.wallet,opener=rpc)
        with Lifecycle(self.home) as s: self.assertEqual(s.execution()['state'],'submission-unknown')
        rpc2=SubmissionRpc(self.home,sent=True); r=recover(self.home,self.wallet,opener=rpc2)
        self.assertEqual(r['state'],'finalized-success')
        self.assertNotIn('sendTransaction',[p['method'] for p in rpc2.calls])
    def test_post_send_cluster_mismatch_never_finalizes(self):
        class WrongAfterSend(SubmissionRpc):
            def open(this,request,timeout):
                if this.sent: this.mode='wrong-cluster'
                return super().open(request,timeout)
        rpc=WrongAfterSend(self.home)
        r=execute(self.home,self.wallet,opener=rpc)
        self.assertEqual(r['state'],'submission-unknown')
    def test_output_collision_prevents_execute(self):
        output=Path(self.tmp.name)/'report.gz'; output.write_text('keep')
        p=subprocess.run([sys.executable,str(HERE/'submission_cli.py'),'--action','execute',
            '--allow-devnet-submit','--directory',str(self.home),'--wallet',self.wallet,
            '--output',str(output)],capture_output=True)
        self.assertNotEqual(p.returncode,0); self.assertEqual(output.read_text(),'keep')
        with Lifecycle(self.home) as s: self.assertIsNone(s.execution())
    def test_uncommitted_boundary_rolls_back_after_process_exit(self):
        script="""import sys,os
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from submission import Lifecycle
s=Lifecycle(Path(sys.argv[2]))
s.db.execute('BEGIN IMMEDIATE')
s.db.execute("INSERT INTO submission(id,plan_id,state,attempts) VALUES (1,1,'submission-unknown',1)")
os._exit(77)
"""
        p=subprocess.run([sys.executable,'-c',script,str(HERE),str(self.home)],capture_output=True,text=True)
        self.assertEqual(p.returncode,77,p.stderr)
        with Lifecycle(self.home) as s: self.assertIsNone(s.execution())
    def test_retention_cap_stops_before_send(self):
        with Lifecycle(self.home) as s:
            with s.tx():
                for _ in range(200): s.event('test',{})
        r,rpc=self.run_case()
        self.assertEqual(r['submissionAttempts'],0)
        self.assertNotIn('sendTransaction',[p['method'] for p in rpc.calls])
    def test_offline_self_check_report(self):
        output=Path(self.tmp.name)/'report.gz'
        p=subprocess.run([sys.executable,str(HERE/'submission_cli.py'),'--output',str(output)],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        with gzip.open(output,'rt') as f: r=json.load(f)
        self.assertEqual(r['casesPassed'],9); self.assertEqual(r['networkRequests'],0); self.assertEqual(r['transactionsSent'],0)

if __name__=='__main__': unittest.main()
