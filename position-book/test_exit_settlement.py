"""Connected settlement, interruption boundaries and full-source closure."""
from copy import deepcopy
import gzip,json,sqlite3,subprocess,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import exit_settlement as m
from exit_settlement_checks import case,run
import test_fresh_exit as full


class SettlementTests(unittest.TestCase):
    def test_portable_contract(self):self.assertEqual(run()['casesPassed'],21)
    def test_cli_private_exclusive_without_operational_flags(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz';cmd=[sys.executable,'-E','-s',str(Path(__file__).with_name('exit_settlement_cli.py')),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=out.read_bytes();self.assertEqual(json.loads(gzip.decompress(raw))['casesPassed'],21)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),raw)
            for flag in ('--action','--directory','--wallet','--close-exit','--allow-devnet-submit','--receipt'):
                other=Path(d)/'absent.gz';self.assertNotEqual(subprocess.run(cmd[:-1]+[str(other),flag],capture_output=True).returncode,0);self.assertFalse(other.exists())
    def test_receipt_write_failure_counts_requests_and_never_collects_balances(self):
        with case() as c:
            c.open_exit()
            with patch.object(m.submission.ExitSubmission,'save_capture',side_effect=sqlite3.OperationalError('PRIVATE')):r=c.finish()
            self.assertEqual(r['networkRequests'],4);self.assertEqual(r['balanceRequestsThisRun'],0)
            self.assertEqual(r['state'],'inspection-required');self.assertNotIn('PRIVATE',json.dumps(r))
            self.assertEqual(c.inspect()['state'],'exit-accounting-pending')
    def test_accounting_lost_response_preserves_commit_and_recovery_does_not_refetch(self):
        with case() as c:
            c.open_exit();apply=m.accounting.apply
            def lost(*args,**kw):apply(*args,**kw);raise OSError('PRIVATE')
            with patch.object(m.accounting,'apply',lost):r=c.finish()
            self.assertIsNone(r['accountingAppliedThisRun']);self.assertIsNone(r['scopedCommitmentsReleased'])
            self.assertEqual(r['networkRequests'],4);self.assertEqual(c.inspect()['state'],'exit-position-flat-held')
            r=c.advance();self.assertEqual(r['networkRequests'],0);self.assertFalse(r['accountingAppliedThisRun'])
    def test_closure_insert_failure_rolls_back_only_closure_and_reports_eight_reads(self):
        with case() as c:
            c.open_exit();insert=m.closure._insert
            def broken(book,record):insert(book,record);raise OSError('PRIVATE')
            with patch.object(m.closure,'_insert',broken):r=c.finish()
            self.assertEqual(r['networkRequests'],8);self.assertIsNone(r['closureAppliedThisRun'])
            self.assertIsNone(r['scopedCommitmentsReleased']);self.assertNotIn('PRIVATE',json.dumps(r))
            s=c.inspect();self.assertEqual(s['state'],'exit-position-flat-held');self.assertFalse(s['closureRecorded'])
            self.assertTrue(s['accounting']['accountingUsable'])
    def test_lost_closure_return_recovers_without_network_or_second_release(self):
        with case() as c:
            c.open_exit();commit=m.closure._commit
            def lost(*args,**kw):commit(*args,**kw);raise OSError('PRIVATE')
            with patch.object(m.closure,'_commit',lost):r=c.finish()
            self.assertEqual(r['networkRequests'],8);self.assertEqual(r['state'],'inspection-required')
            self.assertIsNone(r['closureRecorded']);self.assertIsNone(r['scopedCommitmentsReleased'])
            before=c.path.read_bytes()
            with patch.object(m.submission,'recover',side_effect=AssertionError('RPC')),patch.object(m.closure.balance,'collect',side_effect=AssertionError('balance')):
                s=c.advance(close_exit=True);self.assertTrue(s['closureRecorded']);self.assertEqual(s['networkRequests'],0)
            self.assertEqual(before,c.path.read_bytes());self.assertFalse(s['closureAppliedThisRun'])
    def test_stop_between_accounting_and_balance_allows_settlement_only(self):
        with case() as c:
            c.open_exit();apply=m.accounting.apply
            def stop(*args,**kw):r=apply(*args,**kw);(c.home/'STOP').touch(mode=0o600);return r
            with patch.object(m.accounting,'apply',stop):r=c.finish()
            self.assertEqual(r['networkRequests'],4);self.assertEqual(r['state'],'exit-settled-closure-stopped')
            self.assertTrue(r['accountingAppliedThisRun']);self.assertFalse(r['scopedCommitmentsReleased'])
    def test_stop_and_expiry_during_closure_roll_back_release(self):
        for mode in ('stop','expiry'):
            with case() as c:
                c.open_exit();insert=m.closure._insert
                def changed(book,record):
                    insert(book,record)
                    if mode=='stop':(c.home/'STOP').touch(mode=0o600)
                    else:c.timer.at+=10000
                with patch.object(m.closure,'_insert',changed):r=c.finish()
                self.assertEqual(r['networkRequests'],8);self.assertFalse(c.inspect()['closureRecorded'])
    def test_stop_during_balance_counts_partial_requests(self):
        with case() as c:
            c.open_exit()
            def stop(method):
                if method=='getMultipleAccounts':(c.home/'STOP').touch(mode=0o600)
            r=c.finish(balance=c.balances(callback=stop))
            self.assertEqual(r['receiptRequestsThisRun'],4);self.assertEqual(r['balanceRequestsThisRun'],2)
            self.assertFalse(r['scopedCommitmentsReleased'])
    def test_final_projection_identity_mismatch_withholds_current_release_claim(self):
        with case() as c:
            c.open_exit();c.finish();public=m.closure.public
            def wrong(*args,**kw):
                r=public(*args,**kw)
                if r['closureRecorded']:r['settlement']['exitAccountingSha256']='0'*64
                return r
            with patch.object(m.closure,'public',wrong):
                with self.assertRaisesRegex(ValueError,'exit-settlement-closure-binding'):c.inspect()
                r=c.advance();self.assertEqual(r['state'],'inspection-required');self.assertIsNone(r['scopedCommitmentsReleased'])
                self.assertEqual(r['networkRequests'],0)
    def test_read_only_combined_snapshot_excludes_writer_and_execution(self):
        with case() as c:
            c.open_exit();c.finish();projection=m.lifecycle.projection;seen=[]
            def inspect(book,*args):
                self.assertTrue(book.j.read_only);self.assertEqual(book.db.execute('PRAGMA query_only').fetchone()[0],1)
                db=sqlite3.connect(c.path,timeout=0)
                try:
                    with self.assertRaises(sqlite3.OperationalError):db.execute('BEGIN EXCLUSIVE')
                finally:db.close()
                seen.append(True);return projection(book,*args)
            before=c.path.read_bytes()
            with patch.object(m.lifecycle,'projection',inspect),patch.object(m.submission,'submit',side_effect=AssertionError('send')):
                r=c.inspect();self.assertTrue(r['coherent']);self.assertEqual(r['networkRequests'],0)
            self.assertTrue(seen);self.assertEqual(before,c.path.read_bytes())


class FullSourceTests(unittest.TestCase):
    setUpClass=full.ActualBackendTests.__dict__['setUpClass']
    tearDownClass=full.ActualBackendTests.__dict__['tearDownClass']
    setUp=full.ActualBackendTests.setUp
    tearDown=full.ActualBackendTests.tearDown
    clock=full.ActualBackendTests.clock
    submit=full.ActualBackendTests.submit
    collect=full.ActualBackendTests.collect
    settle=full.ActualBackendTests.settle
    capture=full.ActualBackendTests.capture
    verify=full.ActualBackendTests.verify
    source_bytes=full.ActualBackendTests.source_bytes
    edit_db=full.ActualBackendTests.edit_db
    def test_actual_fresh_exit_then_settlement_closure_and_isolated_restore(self):
        import fresh_exit
        from test_admission_exit_recovery import delayed
        from admission_exit_capture_checks import Opener
        from exit_submission_checks import FakeRpc
        from exit_accounting_checks import package,ReceiptRpc
        from exit_balance_checks import FakeRpc as BalanceRpc
        self.collect();a=self.settle()['accounting'];self.stamp=m.view.now()
        e=delayed(self.e['costInputs']['capture'],a,self.stamp);raw=e['initialPool'];first=deepcopy(e['capture'])
        first.update(packet=None,selection='explicit-pool',accountKeys=raw['accountKeys']+[first['accountKeys'][-1]])
        programdata=deepcopy(first['evidence']['accounts']['result']['value'][-1])
        first['evidence']['accounts']=deepcopy(raw['evidence']['accounts']);first['evidence']['accounts']['result']['value'].append(programdata)
        first['evidence']['poolBootstrap']=deepcopy(raw['evidence']['bootstrap'])
        first['evidence']['programBootstrap']['result']['context']['slot']=first['evidence']['poolBootstrap']['result']['context']['slot']
        for name in ('genesisBefore','genesisAfter','blockTime'):first['evidence'][name]=deepcopy(raw['evidence'][name])
        first['evidence']['blockhash']={'state':'not-requested'};first['evidence']['fee']={'state':'not-requested'}
        baseline=deepcopy(self.e['costInputs']['baseline']);baseline.update(kind='observed-devnet-deployment',observedAtMs=0)
        key=self.home/'signer.pk8';key.write_bytes(self.ephemeral_exit_key);key.chmod(0o600)
        transports=[];test=self;cases=[]
        class Lazy:
            def open(self,request,timeout=None):
                if not transports:
                    b=m.submission.transport._open(test.home,test.wallet,test.pool,m.view.now)
                    try:
                        state=m.submission.ExitSubmission(b).signing()
                        c=SimpleNamespace(exit_state=state,exit_wire=state['signed']['signedWireBase64'],path=b.j.path,signed={})
                    finally:b.close()
                    cases.append(c);transports.append(FakeRpc(c,lost=True))
                return transports[0].open(request,timeout)
        with patch.object(m.submission.handoff.preparation,'BASELINE',baseline):
            r=fresh_exit.prepare_sign_submit(self.home,self.wallet,self.pool,allow_private_key_signing=True,allow_devnet_submit=True,
                collection_opener=Opener(first,e),submission_opener=Lazy(),clock=m.view.now)
            self.assertEqual(r['state'],'exit-submission-unknown',r);key.unlink();self.stamp=m.view.now()+30000
            c=cases[0];c.now=self.stamp;c.book=lambda:m.submission.transport._open(self.home,self.wallet,self.pool,self.clock)
            p,_=package(c);before={str(p):p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
            with patch.object(fresh_exit.backend,'_invoke',side_effect=AssertionError('key')),patch.object(m.submission,'submit',side_effect=AssertionError('send')):
                result=m.advance(self.home,self.wallet,self.pool,close_exit=True,receipt_opener=ReceiptRpc(c,p),balance_opener=BalanceRpc(c),clock=self.clock,monotonic=lambda:0)
            self.assertEqual(result['state'],'closed-scoped-commitments-released',result);self.assertEqual(result['networkRequests'],8)
            self.assertTrue(result['coherent']);self.assertFalse(result['fundsAvailableForNewEntry'])
            self.assertEqual(before,{str(p):p.read_bytes() for p in self.home.rglob('*') if p.is_file()})
            self.assertEqual(sum(x['method']=='sendTransaction' for x in transports[0].requests),1)
            (self.home/'STOP').touch(mode=0o600);self.stamp+=30000
            saved=self.source_bytes();again=m.advance(self.home,self.wallet,self.pool,close_exit=True,clock=self.clock,monotonic=lambda:0)
            self.assertTrue(again['closureRecorded']);self.assertEqual(again['networkRequests'],0);self.assertEqual(saved,self.source_bytes())
            self.capture();self.verify();self.assertEqual(saved,self.source_bytes())

if __name__=='__main__':unittest.main()
