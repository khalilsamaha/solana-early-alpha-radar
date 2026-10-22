import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from swap_rehearsal import (_prepare,report,invoke_signer,scope_for,policy_check,CHILD,SimulationRpc,simulation_review,
                       signed_binding,loads,private_file)
from core import initialize,write_new
from swap_rehearsal_fixtures import scenario,Transport,dependencies,simulation


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)/'wallet'
        self.wallet=initialize(self.home)['wallet'];self.c,self.b,self.scope=scenario(self.wallet)
        self.packet=self.c['packet'];self.transport=Transport(self.c)
    def tearDown(self):self.tmp.cleanup()
    def run_prepare(self,**kw):
        args=dict(opener=self.transport,**dependencies(self.c,self.b));args.update(kw)
        return _prepare(self.home,self.wallet,self.scope,self.packet,**args)
    def signed(self):return loads(private_file(self.home/CHILD/'signed.json',8192))['wire']
    def test_end_to_end_exact_signature_and_simulation(self):
        r=self.run_prepare();self.assertEqual(r['state'],'signed-simulation-consistent',r)
        self.assertEqual(r['signaturesCreatedThisRun'],1);self.assertEqual(r['transactionsSent'],0)
        self.assertEqual([c['method'] for c in self.transport.calls],['simulateTransaction','getGenesisHash'])
        opts=self.transport.calls[0]['params'][1]
        self.assertTrue(opts['sigVerify']);self.assertFalse(opts['replaceRecentBlockhash'])
        self.assertEqual(opts['minContextSlot'],101)
        self.assertNotIn(self.signed(),json.dumps(r));signed_binding(self.packet,self.signed())
    def test_second_prepare_and_status_never_resign_or_request(self):
        first=self.run_prepare();n=len(self.transport.calls)
        second=self.run_prepare();self.assertEqual(second['state'],first['state']);self.assertEqual(second['networkRequests'],0)
        self.assertEqual(len(self.transport.calls),n);self.assertEqual(report(self.home)['state'],first['state'])
        with self.assertRaises(ValueError):invoke_signer(self.home)
    def test_scope_mismatch_before_directory_or_rpc(self):
        self.scope['amountIn']='101'
        with self.assertRaises(ValueError):self.run_prepare()
        self.assertFalse((self.home/CHILD).exists());self.assertEqual(self.transport.calls,[])
    def test_stop_before_any_plan(self):
        (self.home/'STOP').touch()
        with self.assertRaises(ValueError):self.run_prepare()
        self.assertFalse((self.home/CHILD).exists())
    def test_stale_preflight_no_sign(self):
        self.c['evidence']['accounts']['receivedAtMs']-=11000
        r=self.run_prepare();self.assertEqual(r['state'],'preparation-incomplete')
        self.assertFalse((self.home/CHILD/'signing-attempt.json').exists());self.assertFalse(self.transport.calls)
    def test_preflight_packet_replacement_no_sign(self):
        def collect(**kw):
            c=copy.deepcopy(self.c);c['packet']['policy']['amountIn']='101';return c
        self.assertEqual(self.run_prepare(collector=collect)['state'],'preparation-incomplete')
        self.assertFalse((self.home/CHILD/'signed.json').exists())
    def test_crash_after_durable_plan_never_retries(self):
        def crash(**kw):raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.run_prepare(collector=crash)
        self.assertTrue((self.home/CHILD/'plan.json').exists())
        r=self.run_prepare();self.assertEqual(r['state'],'plan-recorded');self.assertEqual(r['networkRequests'],0)
    def test_crash_after_signing_preserves_wire_no_retry(self):
        def crash(home):invoke_signer(home);raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.run_prepare(signer=crash)
        r=self.run_prepare();self.assertEqual(r['state'],'signed-not-simulated');self.assertFalse(self.transport.calls)
    def test_simulation_mismatches_remain_incomplete(self):
        changes=[lambda v:v['value'].update(err={'arbitrary':'secret'}),
                 lambda v:v['value'].update(replacementBlockhash={'blockhash':'x'}),
                 lambda v:v['value'].update(fee=6001),
                 lambda v:v['context'].update(slot=99),
                 lambda v:v['value'].update(unitsConsumed=999999),
                 lambda v:v['value']['postBalances'].__setitem__(1,1234),
                 lambda v:v['value']['postTokenBalances'][0]['uiTokenAmount'].update(amount='1'),
                 lambda v:v['value']['preTokenBalances'][0]['uiTokenAmount'].update(amount='1')]
        # Fresh wallet/session for each case; no reset of a signing boundary.
        for i,change in enumerate(changes):
            with self.subTest(i=i):
                h=Path(self.tmp.name)/('case'+str(i));w=initialize(h)['wallet'];c,b,s=scenario(w)
                r=_prepare(h,w,s,c['packet'],opener=Transport(c,change),**dependencies(c,b))
                self.assertEqual(r['state'],'preparation-incomplete');self.assertEqual(r['transactionsSent'],0)
                self.assertNotIn('secret',json.dumps(r))
    def test_method_allowlist(self):
        rpc=SimulationRpc(self.transport)
        with self.assertRaises(ValueError):rpc.request('sendTransaction',[])
        self.assertFalse(self.transport.calls)
    def test_signer_independently_rejects_wire_change(self):
        def mutate(home):
            path=home/CHILD/'signing-request.json';d=json.loads(path.read_text());d['messageBase64']='AAAA'
            path.write_text(json.dumps(d));invoke_signer(home)
        r=self.run_prepare(signer=mutate);self.assertEqual(r['state'],'preparation-incomplete')
        self.assertFalse((self.home/CHILD/'signing-attempt.json').exists())
    def test_hard_limits(self):
        s=copy.deepcopy(self.scope);p=copy.deepcopy(self.packet);s['maxTotalFeeLamports']=p['policy']['maxTotalFeeLamports']='10001'
        with self.assertRaisesRegex(ValueError,'hard-cap'):policy_check(s,p,self.wallet,self.c['finishedAtMs'])
    def test_private_storage_and_no_signed_wire_export(self):
        r=self.run_prepare()
        self.assertEqual((self.home/CHILD).stat().st_mode&0o777,0o700)
        for p in (self.home/CHILD).iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)
        self.assertNotIn('unsignedTransactionBase64',json.dumps(r));self.assertFalse(r['signedBytesExported'])


    def test_signing_attempt_without_result_is_unknown_and_never_retried(self):
        def attempt(home):
            write_new(home/CHILD/'signing-attempt.json',{'atMs':1});raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.run_prepare(signer=attempt)
        r=self.run_prepare();self.assertEqual(r['state'],'signing-outcome-unknown');self.assertTrue(r['signatureOutcomeUnknown'])
        self.assertFalse(self.transport.calls)
    def test_stop_after_sign_prevents_simulation(self):
        def stop(home):invoke_signer(home);(home/'STOP').touch()
        r=self.run_prepare(signer=stop);self.assertEqual(r['state'],'preparation-incomplete');self.assertFalse(self.transport.calls)
        self.assertTrue((self.home/CHILD/'signed.json').exists())
    def test_expiry_after_sign_prevents_simulation(self):
        import time
        clock=[time.time_ns()//1000000]
        def expire(home):invoke_signer(home);clock[0]+=20000
        r=self.run_prepare(signer=expire,clock=lambda:clock[0]);self.assertEqual(r['state'],'preparation-incomplete')
        self.assertFalse(self.transport.calls)
    def test_dangling_stop_link_blocks(self):
        (self.home/'STOP').symlink_to(self.home/'missing')
        with self.assertRaises(ValueError):self.run_prepare()
        self.assertFalse((self.home/CHILD).exists())
    def test_existing_session_lock_prevents_concurrent_prepare(self):
        from core import Session
        with Session(self.home):
            with self.assertRaises(OSError):self.run_prepare()
        self.assertFalse((self.home/CHILD).exists())
    def test_signer_and_status_reject_hardlinked_plan(self):
        def unsafe(home):
            os.link(home/CHILD/'plan.json',home/CHILD/'extra-plan.json');invoke_signer(home)
        with self.assertRaisesRegex(ValueError,'unsafe-private-file'):self.run_prepare(signer=unsafe)
        self.assertFalse((self.home/CHILD/'signing-attempt.json').exists())
    def test_signer_independent_caps_even_if_all_message_bindings_rebuilt(self):
        from swap_fixtures import instruction_data
        from contract import decode
        import struct
        self.packet['policy']['amountIn']='1001';self.scope['amountIn']='1001'
        instruction_data(self.packet,2,bytes.fromhex('8fbe5adac41e33de')+struct.pack('<QQ',1001,190))
        # Build request directly to test the signer independently of Python's earlier cap.
        from swap_rehearsal import digest,decode_wire
        import base64,time
        child=self.home/CHILD;child.mkdir(mode=0o700)
        plan=dict(format='swap-signing-plan-1',scope=self.scope,packet=self.packet,recordedAtMs=time.time_ns()//1000000)
        write_new(child/'plan.json',plan);write_new(child/'preflight.json',self.c)
        write_new(child/'signing-request.json',dict(format='restricted-swap-request-1',planSha256=digest(plan),
            preflightSha256=digest(self.c),expiresAtMs=self.c['finishedAtMs']+9000,computeUnits=200000,
            microLamportsPerCU='1',messageBase64=base64.b64encode(decode_wire(self.packet['unsignedTransactionBase64'])[1]).decode()))
        with self.assertRaises(ValueError):invoke_signer(self.home)
        self.assertFalse((child/'signing-attempt.json').exists())
    def test_simulation_projection_withholds_raw_error_logs(self):
        self.transport.change=lambda v:v['value'].update(err={'secret':'arbitrary'},logs=['private provider text'])
        self.run_prepare();stored=(self.home/CHILD/'simulation-response.json').read_text()
        self.assertNotIn('arbitrary',stored);self.assertNotIn('private provider text',stored)
        self.assertTrue(json.loads(stored)['result']['value']['failed'])
    def test_missing_token_evidence_not_synthetic_success(self):
        self.transport.change=lambda v:v['value'].pop('preTokenBalances')
        self.assertEqual(self.run_prepare()['state'],'preparation-incomplete')
    def test_simulation_transport_failure_no_resimulation(self):
        import urllib.error
        class Failed:
            def open(self,*a,**k):raise urllib.error.URLError('private transport text')
        r=self.run_prepare(opener=Failed());self.assertEqual(r['state'],'preparation-incomplete')
        again=self.run_prepare();self.assertEqual(again['networkRequests'],0);self.assertFalse(self.transport.calls)


if __name__=='__main__':unittest.main()
