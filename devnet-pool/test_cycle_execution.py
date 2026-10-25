"""Cycle 2 uses disposable signatures, existing historical journals and synthetic RPC only."""
import base64
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error
import cycle_preparation as c
import cycle_binding as binding
import swap_submission as s
import test_cycle_preparation as prior
import test_funding_reconciliation as funding
import test_controlled_swap as setup
from pool_fixtures import BASE, Response, fake_key
from swap_rehearsal_fixtures import simulation


class Transport(setup.SwapTransport):
    def __init__(self,home,wallet,*,reverse=False,change=None,pending=False,failure=False,lost_ack=False):
        super().__init__(home,change)
        self.wallet=wallet;self.reverse=reverse;self.pending=pending;self.failure=failure;self.lost_ack=lost_ack
        self.sent=False;self.simulated=False;self.jhome=home/binding.CYCLE
        self.child=self.jhome/s.journal_name(reverse)
        self.old=json.loads((home/s.swap.CHILD/'plan.json').read_text())['packet']['policy']['blockhash']
        r=json.loads((self.jhome/'preparation.json').read_text())
        self.rows[wallet]['lamports']=int(r['balances']['walletLamports'])
        a=r['source']['scope']['accounts'];self.first=None
        for key,amount in ((a['source'],r['balances']['originalTokenAtomic']),(a['destination'],r['balances']['backgroundAcquiredAtomic'])):
            raw=bytearray(base64.b64decode(self.rows[key]['data'][0]));raw[64:72]=int(amount).to_bytes(8,'little')
            self.rows[key]['data'][0]=base64.b64encode(raw).decode()
        if reverse:
            self.first=s.read(self.jhome/s.CHILD,'receipt-evidence.json',131072)
            rec=s.report(self.jhome,wallet)['observation']['receipt']
            self.rows[wallet]['lamports']=int(rec['walletAfterLamports'])
            for e in rec['tokenEffects'].values():
                row=self.rows[e['account']];raw=bytearray(base64.b64decode(row['data'][0]))
                raw[64:72]=int(e['afterAtomic']).to_bytes(8,'little');row['data'][0]=base64.b64encode(raw).decode()
    def signature(self):
        return s.swap.signed_binding(s.read(self.child,'plan.json')['packet'],s.read(self.child,'signed.json')['wire'])['signatures'][0]
    def tx(self):
        v=simulation(s.read(self.child,'presend-preflight.json',4*1024*1024))['value']
        if self.failure:v['postTokenBalances']=copy.deepcopy(v['preTokenBalances'])
        return dict(slot=170 if self.reverse else 160,version='legacy',transaction=[s.read(self.child,'signed.json')['wire'],'base64'],meta=dict(
            err={'InstructionError':[2,{'Custom':1}]} if self.failure else None,fee=v['fee'],preBalances=v['preBalances'],postBalances=v['postBalances'],
            preTokenBalances=v['preTokenBalances'],postTokenBalances=v['postTokenBalances'],loadedAddresses=dict(writable=[],readonly=[])))
    def open(self,req,timeout=None):
        q=json.loads(req.data);method=q['method']
        if method not in ('getLatestBlockhash','getFeeForMessage','getMultipleAccounts','isBlockhashValid','simulateTransaction','sendTransaction',
                          'getSignatureStatuses','getTransaction','getBlockHeight'):
            return super().open(req,timeout)
        self.calls.append(q);assert req.full_url=='https://api.devnet.solana.com'
        slot=(170 if self.reverse else 160) if self.simulated else (168 if self.reverse else 158)
        if method=='getLatestBlockhash':v=dict(context={'slot':slot},value=dict(blockhash=fake_key('cycle-two-reverse' if self.reverse else 'cycle-two-entry'),lastValidBlockHeight=3000))
        elif method=='getFeeForMessage':v=dict(context={'slot':slot},value=5000)
        elif method=='getMultipleAccounts':v=dict(context={'slot':slot},value=[copy.deepcopy(self.rows[k]) for k in q['params'][0]])
        elif method=='isBlockhashValid':v=dict(context={'slot':slot},value=q['params'][0]!=self.old)
        elif method=='getBlockHeight':v=1000
        elif method=='simulateTransaction':
            v=simulation(s.read(self.child,'preflight.json',4*1024*1024));v['context']['slot']=169 if self.reverse else 159;self.simulated=True
        elif method=='sendTransaction':
            assert (self.child/'submission-boundary.json').exists();assert q['params'][1]['maxRetries']==0
            self.sent=True
            if self.lost_ack:raise urllib.error.URLError('synthetic lost ack')
            v=self.signature()
        elif method=='getSignatureStatuses':
            sig=q['params'][0][0];row=None
            if self.first and sig==self.first['transaction']['transaction'][0]:raise AssertionError('wire confused with signature')
            if self.first and sig==s.read(self.jhome/s.CHILD,'simulation-review.json')['signature']:row=self.first['status']
            elif self.sent and not self.pending and sig==self.signature():row=dict(slot=self.tx()['slot'],confirmationStatus='finalized',confirmations=None,err=self.tx()['meta']['err'])
            v=dict(context={'slot':180},value=[row])
        else:
            sig=q['params'][0]
            v=self.first['transaction'] if self.first and sig==s.read(self.jhome/s.CHILD,'simulation-review.json')['signature'] else self.tx() if self.sent and sig==self.signature() else None
        if self.change:v=self.change(q,v)
        return Response(json.dumps(dict(jsonrpc='2.0',id=q['id'],result=v)).encode())


class CycleExecutionCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prior.CyclePreparationCase.setUpClass.__func__(cls)
        c.run(cls.template,cls.wallet,cls.pool,prepare=True,reconcile_funding=True,opener=funding.FundingTransport(cls.template,cls.wallet))
    tearDownClass=classmethod(prior.CyclePreparationCase.tearDownClass.__func__)
    setUp=prior.CyclePreparationCase.setUp
    tearDown=prior.CyclePreparationCase.tearDown
    old_files=prior.CyclePreparationCase.old_files
    def entry(self,t=None):return s.execute(self.home,self.wallet,self.pool,cycle=True,opener=t or Transport(self.home,self.wallet),sleeper=lambda _:None)
    def exit(self,t=None):return s.execute_reverse(self.home,self.wallet,self.pool,cycle=True,opener=t or Transport(self.home,self.wallet,reverse=True),sleeper=lambda _:None)
    def test_roundtrip_preserves_history_and_carries_cumulative_spending(self):
        before=self.old_files();r=self.entry();self.assertEqual(r['state'],'finalized-success',r)
        self.assertEqual(r['sendRequestsThisRun'],1);self.assertEqual(r['cycleId'],binding.CYCLE)
        self.assertEqual(r['spendingGuard']['cumulativeConfirmedFeeLamports'],'15000')
        self.assertEqual(r['spendingGuard']['cumulativeConfirmedAndReservedFeeLamports'],'25000')
        x=self.exit();self.assertEqual(x['state'],'finalized-success',x)
        self.assertEqual(x['spendingGuard']['state'],'closed')
        self.assertEqual(x['spendingGuard']['cumulativeConfirmedFeeLamports'],'20000')
        self.assertEqual(x['spendingGuard']['cumulativeGrossEntryAllocatedAtomic'],'2000')
        self.assertEqual(x['roundTrip']['residualAcquiredTokenAtomic'],'0')
        self.assertEqual(before,self.old_files())

    def test_repeat_entry_and_exit_never_send_again(self):
        r=self.entry();t=Transport(self.home,self.wallet);again=self.entry(t)
        self.assertEqual(r['signature'],again['signature']);self.assertEqual(t.calls,[])
        x=self.exit();t=Transport(self.home,self.wallet,reverse=True);again=self.exit(t)
        self.assertEqual(x['signature'],again['signature']);self.assertEqual(t.calls,[])

    def test_unknown_entry_holds_allocation_and_recovery_never_resends(self):
        t=Transport(self.home,self.wallet,pending=True);r=self.entry(t)
        self.assertEqual(r['spendingGuard']['heldEntryPrincipalAtomic'],'1000')
        self.assertEqual(r['spendingGuard']['cumulativeConfirmedAndReservedFeeLamports'],'30000')
        t.calls.clear();t.change=lambda q,v:4000 if q['method']=='getBlockHeight' else v
        r=s.recover(self.home,self.wallet,cycle=True,opener=t,sleeper=lambda _:None)
        self.assertEqual(r['state'],'expired-outcome-unknown')
        self.assertEqual(r['spendingGuard']['reservedFeeLamports'],'20000')
        self.assertFalse(any(q['method']=='sendTransaction' for q in t.calls))
        t.pending=False;t.change=None;t.calls.clear()
        r=s.recover(self.home,self.wallet,cycle=True,opener=t,sleeper=lambda _:None)
        self.assertEqual(r['state'],'finalized-success');self.assertEqual(r['spendingGuard']['confirmedFeeLamports'],'5000')
        t.calls.clear();s.recover(self.home,self.wallet,cycle=True,opener=t);self.assertEqual(t.calls,[])

    def test_lost_ack_observes_exact_signature_without_second_send(self):
        t=Transport(self.home,self.wallet,lost_ack=True);r=self.entry(t)
        self.assertEqual(r['state'],'finalized-success');self.assertEqual(r['sendRequestsThisRun'],1)

    def test_failed_entry_records_fee_without_retry_or_reverse(self):
        t=Transport(self.home,self.wallet,failure=True);r=self.entry(t)
        self.assertEqual(r['state'],'finalized-failure');self.assertEqual(r['spendingGuard']['state'],'entry-failed')
        self.assertEqual(r['spendingGuard']['cumulativeConfirmedFeeLamports'],'15000')
        with self.assertRaises(ValueError):self.exit(Transport(self.home,self.wallet))
        self.assertFalse((self.home/binding.CYCLE/s.REVERSE_CHILD).exists())

    def test_failed_exit_retains_position_and_cumulative_fee(self):
        self.entry();r=self.exit(Transport(self.home,self.wallet,reverse=True,failure=True))
        self.assertEqual(r['state'],'finalized-failure');self.assertEqual(r['spendingGuard']['state'],'exit-failed-position-open')
        self.assertGreater(int(r['spendingGuard']['lastReconciledAcquiredAtomic']),0)
        self.assertEqual(r['spendingGuard']['cumulativeConfirmedFeeLamports'],'20000')
        t=Transport(self.home,self.wallet,reverse=True);self.exit(t);self.assertEqual(t.calls,[])

    def test_unknown_exit_recovers_only_cycle_two_receipt(self):
        self.entry();t=Transport(self.home,self.wallet,reverse=True,pending=True);r=self.exit(t)
        self.assertEqual(r['spendingGuard']['state'],'exit-unresolved');self.assertEqual(r['spendingGuard']['reservedFeeLamports'],'10000')
        t.pending=False;t.calls.clear();r=s.recover(self.home,self.wallet,cycle=True,reverse=True,opener=t,sleeper=lambda _:None)
        self.assertEqual(r['spendingGuard']['state'],'closed');self.assertFalse(any(q['method']=='sendTransaction' for q in t.calls))

    def test_stop_before_entry_and_before_exit_does_not_create_attempt(self):
        stop=self.home/'STOP';stop.touch(mode=0o600)
        with self.assertRaisesRegex(ValueError,'stop-requested'):self.entry()
        self.assertFalse((self.home/binding.CYCLE/s.CHILD).exists());stop.unlink()
        self.entry();stop.touch(mode=0o600)
        with self.assertRaisesRegex(ValueError,'stop-requested'):self.exit()
        self.assertFalse((self.home/binding.CYCLE/s.REVERSE_CHILD).exists())
        self.assertTrue(s.status(self.home,self.wallet,cycle=True)['stopRequested'])

    def test_drift_after_preparation_refuses_before_signer(self):
        t=Transport(self.home,self.wallet);t.rows[self.wallet]['lamports']+=1
        with patch.object(s.swap,'invoke_signer',side_effect=AssertionError('must not sign')):r=self.entry(t)
        self.assertEqual(r['state'],'preparation-incomplete');self.assertEqual(r['sendRequestsThisRun'],0)
        self.assertFalse((self.home/binding.CYCLE/s.CHILD/'signing-attempt.json').exists())
        t=Transport(self.home,self.wallet);self.entry(t);self.assertEqual(t.calls,[])

    def test_reservation_exists_before_signing_and_boundary_before_send(self):
        signer=s.swap.invoke_signer;t=Transport(self.home,self.wallet);opening=t.open
        def sign(*args,**kw):
            with s.spend_guard.Guard(self.home/binding.CYCLE) as g:
                state=g.summary();self.assertEqual(state['reservedFeeLamports'],'20000')
                self.assertEqual(state['cycleBinding']['historicalSwapFeeLamports'],'10000')
            return signer(*args,**kw)
        def request(req,timeout=None):
            if json.loads(req.data)['method']=='sendTransaction':
                with s.spend_guard.Guard(self.home/binding.CYCLE) as g:self.assertIsNotNone(g.summary()['legs']['entry']['boundaryAtMs'])
            return opening(req,timeout)
        t.open=request
        with patch.object(s.swap,'invoke_signer',side_effect=sign):r=self.entry(t)
        self.assertEqual(r['state'],'finalized-success')

    def test_signer_independently_rejects_missing_reservation(self):
        signer=s.swap.invoke_signer
        def sign(*args,**kw):
            p=self.home/binding.CYCLE/s.spend_guard.NAME
            saved=p.read_bytes();p.unlink()
            try:
                with self.assertRaisesRegex(ValueError,'restricted-signer-refused'):signer(*args,**kw)
                self.assertFalse((self.home/binding.CYCLE/s.CHILD/'signing-attempt.json').exists())
            finally:p.write_bytes(saved);p.chmod(0o600)
            raise ValueError('test-refusal')
        with patch.object(s.swap,'invoke_signer',side_effect=sign):r=self.entry()
        self.assertEqual(r['sendRequestsThisRun'],0);self.assertEqual(r['spendingGuard']['reservedFeeLamports'],'20000')

    def test_signer_independently_rejects_changed_cycle_identity(self):
        signer=s.swap.invoke_signer
        def sign(*args,**kw):
            child=self.home/binding.CYCLE/s.CHILD;p=child/'plan.json';saved=p.read_bytes();value=json.loads(saved)
            value['cycleBinding']['preparationSha256']='0'*64;p.write_text(json.dumps(value))
            request=child/'signing-request.json';old=request.read_bytes();req=json.loads(old);req['planSha256']=s.pool.digest(value);request.write_text(json.dumps(req))
            try:
                with self.assertRaisesRegex(ValueError,'restricted-signer-refused'):signer(*args,**kw)
                self.assertFalse((child/'signing-attempt.json').exists())
            finally:p.write_bytes(saved);request.write_bytes(old)
            raise ValueError('test-refusal')
        with patch.object(s.swap,'invoke_signer',side_effect=sign):r=self.entry()
        self.assertEqual(r['sendRequestsThisRun'],0)

    def test_preparation_change_during_action_is_not_hidden_by_cache(self):
        path=self.home/binding.CYCLE/'preparation.json';before=path.read_bytes()
        t=Transport(self.home,self.wallet)
        def change(q,v):
            if q['method']=='getLatestBlockhash':path.write_bytes(before+b' ')
            return v
        t.change=change
        with self.assertRaisesRegex(ValueError,'cycle-preparation-changed-during-operation'):self.entry(t)
        self.assertFalse((self.home/binding.CYCLE/s.CHILD/'signed.json').exists())
        path.write_bytes(before)
        self.assertEqual(s.status(self.home,self.wallet,cycle=True)['state'],'preparation-incomplete')

    def test_wrong_wallet_pool_and_other_cycle_are_rejected(self):
        for wallet,pool in ((fake_key('wrong-wallet'),self.pool),(self.wallet,fake_key('wrong-pool'))):
            with self.assertRaises(ValueError):s.execute(self.home,wallet,pool,cycle=True,opener=Transport(self.home,self.wallet))
        with self.assertRaises(ValueError):binding.load(self.home)
        self.assertFalse((self.home/binding.CYCLE/s.CHILD).exists())

    def test_extra_cycle_directory_and_preparation_policy_change_refuse(self):
        child=self.home/binding.CYCLE;extra=child/'cycle-three';extra.mkdir(mode=0o700)
        with self.assertRaises(ValueError):self.entry()
        extra.rmdir();p=child/'preparation.json';r=json.loads(p.read_text());r['budget']['historicalSwapFeeLamports']='0';p.write_text(json.dumps(r))
        (child/'complete.json').write_text(json.dumps(dict(format=c.VERSION,preparationSha256=c.controlled.digest(r))))
        with self.assertRaises(ValueError):self.entry()
        self.assertFalse((child/s.CHILD).exists())

    def test_status_and_terminal_recovery_do_not_refresh_or_send(self):
        self.entry();(self.home/'STOP').touch(mode=0o600);t=Transport(self.home,self.wallet)
        r=s.recover(self.home,self.wallet,cycle=True,opener=t);self.assertEqual(t.calls,[])
        self.assertEqual(r['state'],'finalized-success')
        self.assertEqual(s.status(self.home,self.wallet,cycle=True)['spendingGuard']['cumulativeConfirmedFeeLamports'],'15000')

    def test_inspect_needs_no_private_key_and_preserves_every_file(self):
        import cycle_execute_cli
        (self.home/'signer.pk8').unlink();before={str(p):p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        r=cycle_execute_cli.inspect(self.home,self.wallet,self.pool)
        self.assertEqual(r['nextAction'],'entry');self.assertFalse(r['privateKeyAccessed'])
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.home.rglob('*') if p.is_file()})

    def test_stop_at_submission_boundary_keeps_reserved_budget_without_send(self):
        write=s.write_new
        def stopped(path,value):
            write(path,value)
            if path.name=='submission-boundary.json':(self.home/'STOP').touch(mode=0o600)
        with patch.object(s,'write_new',side_effect=stopped):r=self.entry()
        self.assertEqual(r['sendRequestsThisRun'],0);self.assertTrue(r['submissionBoundaryRecorded'])
        self.assertEqual(r['spendingGuard']['reservedFeeLamports'],'20000')
        self.assertFalse(r['resubmitAllowed'])

    def test_actual_process_death_after_boundary_is_durable(self):
        import subprocess,sys
        code='''
import sys,os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,sys.argv[1])
import test_cycle_execution as t
import swap_submission as s
home=Path(sys.argv[2]);wallet=sys.argv[3];pool=sys.argv[4]
baseline=dict(t.copy.deepcopy(t.BASE),network='devnet',kind='observed-devnet-deployment',observedAtMs=0)
write=s.write_new
def crash(path,value):
 write(path,value)
 if path.name=='submission-boundary.json':os._exit(73)
with patch('preflight.BASELINE',baseline),patch('preflight_capture.BASELINE',baseline),patch.object(s,'write_new',side_effect=crash):
 s.execute(home,wallet,pool,cycle=True,opener=t.Transport(home,wallet),sleeper=lambda _:None)
'''
        p=subprocess.run([sys.executable,'-c',code,str(Path(__file__).parent),str(self.home),self.wallet,self.pool],capture_output=True,text=True,timeout=40)
        self.assertEqual(p.returncode,73,p.stderr)
        r=s.status(self.home,self.wallet,cycle=True);self.assertTrue(r['submissionBoundaryRecorded'])
        self.assertEqual(r['spendingGuard']['reservedFeeLamports'],'20000')
        t=Transport(self.home,self.wallet,pending=True);r=self.entry(t);self.assertEqual(t.calls,[])
        r=s.recover(self.home,self.wallet,cycle=True,opener=t,sleeper=lambda _:None)
        self.assertEqual(r['spendingGuard']['reservedFeeLamports'],'20000');self.assertEqual(r['sendRequestsThisRun'],0)

    def test_contradictory_receipt_quarantines_without_releasing_budget(self):
        def change(q,v):
            if q['method']=='getTransaction' and v:v['meta']['postBalances'][0]-=1
            return v
        r=self.entry(Transport(self.home,self.wallet,change=change))
        self.assertEqual(r['state'],'quarantined');self.assertEqual(r['spendingGuard']['state'],'quarantined')
        self.assertEqual(r['spendingGuard']['reservedFeeLamports'],'20000')

    def test_fresh_process_inspection_and_submit_flag_validation(self):
        import subprocess,sys,gzip
        cli=Path(__file__).with_name('cycle_execute_cli.py');out=Path(self.tmp.name)/'inspect.json.gz'
        args=[sys.executable,'-E','-s',str(cli),'--directory',str(self.home),'--wallet',self.wallet,'--pool',self.pool,'--output',str(out)]
        p=subprocess.run(args+['--action','inspect'],capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stderr)
        with gzip.open(out,'rt') as stream:r=json.load(stream)
        self.assertEqual(r['nextAction'],'entry');self.assertEqual(r['networkRequests'],0)
        out.unlink();p=subprocess.run(args+['--action','entry'],capture_output=True,text=True,timeout=10)
        self.assertNotEqual(p.returncode,0);self.assertFalse((self.home/binding.CYCLE/s.CHILD).exists())

    def test_cli_entry_uses_fixed_cycle_and_exports_no_signed_bytes(self):
        import cycle_execute_cli,sys,io,gzip
        from contextlib import redirect_stdout
        output=Path(self.tmp.name)/'entry.json.gz';t=Transport(self.home,self.wallet);execute=s.execute
        args=['cycle_execute_cli.py','--action','entry','--allow-devnet-submit','--directory',str(self.home),
              '--wallet',self.wallet,'--pool',self.pool,'--output',str(output)]
        def run(*a,**kw):return execute(*a,**kw,opener=t,sleeper=lambda _:None)
        with patch.object(sys,'argv',args),patch.object(s,'execute',side_effect=run),redirect_stdout(io.StringIO()):cycle_execute_cli.main()
        with gzip.open(output,'rt') as stream:r=json.load(stream)
        self.assertEqual(r['state'],'finalized-success');self.assertEqual(r['cycleId'],binding.CYCLE)
        self.assertNotIn(s.read(self.home/binding.CYCLE/s.CHILD,'signed.json')['wire'],json.dumps(r))

    def test_legacy_first_cycle_without_guard_still_carries_replayed_spending(self):
        for name in (s.CHILD,s.REVERSE_CHILD):
            p=self.home/name/'execution.json';v=json.loads(p.read_text());del v['spendingGuardVersion'];p.write_text(json.dumps(v))
            (self.home/name/s.spend_guard.MARKER).unlink()
        (self.home/s.spend_guard.NAME).unlink()
        r=self.entry();self.assertEqual(r['state'],'finalized-success',r)
        self.assertEqual(r['spendingGuard']['cycleBinding']['historicalSwapFeeLamports'],'10000')
        self.assertEqual(r['spendingGuard']['cumulativeConfirmedFeeLamports'],'15000')
        self.assertFalse((self.home/s.spend_guard.NAME).exists())
