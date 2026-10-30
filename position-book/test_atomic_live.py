"""Collector, parser, deadline and CPI adversarial checks over fake HTTP only."""
import base64
from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import atomic_effects as m
import atomic_simulation as live
import fresh_quote
from atomic_effects_checks import fixture, response, run
from atomic_rehearsal_checks import trace_quantity
from contract import decode_wire
from post_entry_checks import mutate_row, NOW
from test_post_entry_live import PoolOpener
import test_fresh_quote as fixtures
from test_fresh_quote import Opener, Clock, GENESIS
from post_entry_simulation import AtomicTransport


class AtomicOpener(PoolOpener):
    def __init__(self,first,second,scope,change=None,hook=None,fee=6000,cluster=None):
        super().__init__(first,second,scope,hook=hook)
        self.atomic_change=change;self.atomic_fee=fee;self.atomic_cluster=cluster
    def open(self,request,timeout):
        n=len(self.calls)
        if n<20:return super().open(request,timeout)
        body=json.loads(request.data)
        if n==20:value=dict(context=dict(slot=102),value=self.atomic_fee)
        elif n==21:
            value=response(self.capture,body['params'][0])
            if self.atomic_change:self.atomic_change(value)
        else:value=self.atomic_cluster or GENESIS['devnet']
        self.responses.append(value)
        return Opener.open(self,request,timeout)


class AtomicLiveTests(unittest.TestCase):
    def observe(self,change=None,hook=None,fee=6000,cluster=None,**kw):
        def observer(*args,**kwargs):return fresh_quote.observe(*args,**kwargs,post_entry_projection=True,atomic_rehearsal=True)
        return fixtures.FreshQuoteTests().run_observe(simulate=True,assess_costs=True,observer=observer,
            opener_factory=lambda f,s,scope:AtomicOpener(f,s,scope,change,hook,fee,cluster),**kw)

    def reject(self,r):
        self.assertEqual(r['state'],'unavailable',r)
        for k in ('simulationVerified','liveCollectorVerified','executionApproved'):self.assertFalse(r[k],k)
        self.assertIsNone(r['atomicRehearsal'])
        self.assertIsNone(r['postEntryProjection'])
        self.assertEqual((r['signaturesCreated'],r['transactionsSent']),(0,0))

    def test_portable_cases(self):self.assertEqual(run()['casesPassed'],21)

    def test_end_to_end_two_unsigned_simulations_own_fee_full_effects_and_exact_requests(self):
        r,o=self.observe()
        self.assertEqual(r['state'],'controlled-atomic-rehearsal-observation-consistent',r)
        self.assertEqual(r['networkRequests'],23)
        self.assertEqual(r['requestMethods'].count('simulateTransaction'),2)
        a=r['atomicRehearsal'];self.assertTrue(a['liveCollectorVerified']);self.assertTrue(a['simulationVerified'])
        self.assertEqual(a['fee']['observedCombinedLamports'],'6000')
        self.assertEqual(r['simulation']['feeLamports'],'5000')
        self.assertEqual(a['trace']['originalTokenChangeAtomic'],'-7')
        self.assertEqual(a['trace']['residualAcquiredAtomic'],'0')
        self.assertEqual(a['innerInstructionEncoding'],'json-parsed')
        for k in ('oracleReferenceEffectsMatched','finalPoolEffectsMatched','finalTokenAccountsMatched','returnedDeploymentMatched'):self.assertTrue(a[k])
        for k in ('executionApproved','twoTransactionExecutionVerified','roundTripFundingEstablished','sourceEquivalenceVerified'):self.assertFalse(a[k])
        fee=o.calls[20];sim=o.calls[21]
        self.assertEqual(fee['method'],'getFeeForMessage')
        wire=base64.b64decode(sim['params'][0]);self.assertEqual(base64.b64decode(fee['params'][0]),wire[65:])
        self.assertEqual(wire[:65],b'\x01'+bytes(64))
        opt=sim['params'][1];self.assertIs(opt['sigVerify'],False);self.assertIs(opt['replaceRecentBlockhash'],False)
        self.assertIs(opt['innerInstructions'],True);self.assertEqual(opt['accounts']['addresses'][-1],m.CLOCK)
        self.assertEqual(len(opt['accounts']['addresses']),11)
        self.assertNotIn('unsignedTransactionBase64',json.dumps(r));self.assertNotIn('sendTransaction',r['requestMethods'])
        self.assertGreater(r['timing']['remainingMs'],0)

    def test_different_fee_and_failed_simulation_never_pass_or_retry(self):
        for fee in (None,True,10001,5000):
            r,o=self.observe(fee=fee);self.reject(r);self.assertLessEqual(len(o.calls),23)
        r,o=self.observe(lambda v:v['value'].update(err={'private':'secret'}));self.reject(r)
        self.assertEqual(len(o.calls),22);self.assertNotIn('secret',json.dumps(r))
        r,_=self.observe(cluster=GENESIS['mainnet-beta']);self.reject(r)

    def test_partial_trace_inventory_mask_missing_clock_and_effect_drift(self):
        changes=[lambda v:v['value']['innerInstructions'].pop(),
            lambda v:v['value']['innerInstructions'][0]['instructions'][1]['parsed']['info']['tokenAmount'].update(amount='905'),
            lambda v:v['value']['innerInstructions'][1]['instructions'][0]['parsed']['info']['tokenAmount'].update(amount='905'),
            lambda v:v['value']['accounts'].pop(),
            lambda v:mutate_row(v['value']['accounts'][8],381,(999).to_bytes(8,'little')),
            lambda v:mutate_row(v['value']['accounts'][9],4074,b'\x01'),
            lambda v:v['value']['preTokenBalances'][2]['uiTokenAmount'].update(amount='10001')]
        for change in changes:
            r,_=self.observe(change);self.reject(r)

    def test_every_added_response_final_reservation_and_validation_obey_original_deadline(self):
        for response_number in (21,22,23):
            clock=Clock()
            def hook(n,b):
                if n==response_number:clock.at+=10001
            r,o=self.observe(hook=hook,clock=clock);self.reject(r);self.assertEqual(len(o.calls),response_number)
        clock=Clock()
        def ledger(n,v):
            if n==4:clock.at+=10001
        r,_=self.observe(clock=clock,ledger_hook=ledger);self.reject(r)
        clock=Clock();real=m.assess
        def slow(*args):
            r=real(*args);clock.at+=10001;return r
        with patch('atomic_effects.assess',slow):r,_=self.observe(clock=clock)
        self.reject(r);self.assertLess(r['timing']['remainingMs'],0)

    def test_final_reservations_stop_clock_and_source_identity_are_checked(self):
        for mode in ('identity','native','token','open','clock','stop'):
            stop=[False]
            def ledger(n,v):
                if n!=4:return
                if mode=='identity':v['ledgerHeadSha256']='c'*64
                if mode=='native':v['nativeHeldLamports']='99999'
                if mode=='token':v['tokenAccounts'][0]['heldAtomic']=None
                if mode=='open':v['phase']='open'
                if mode=='clock':v['readStartedAtMs']=NOW
                if mode=='stop':stop[0]=True
            r,_=self.observe(ledger_hook=ledger,stop=lambda _:stop[0]);self.reject(r)

    def test_trace_encoding_is_strict_and_provider_text_not_exported(self):
        a,p,d,e=fixture();sp=e['simulationParams'];raw=response(a['capture'],d['unsignedTransactionBase64'])
        raw['value'].update(logs=['SECRET'],returnData={'secret':'SECRET'})
        clean=live.sanitize(dict(state='received',result=raw),sp);self.assertNotIn('SECRET',json.dumps(clean))
        changes=[lambda v:v['value']['innerInstructions'][0]['instructions'][0]['parsed'].update(type='transfer'),
            lambda v:v['value']['innerInstructions'][0]['instructions'][0]['parsed']['info'].update(signers=['anything']),
            lambda v:v['value']['innerInstructions'][0]['instructions'][0].update(stackHeight=3),
            lambda v:v['value']['innerInstructions'][0]['instructions'][0]['parsed']['info']['tokenAmount'].update(amount='1e6'),
            lambda v:v['value']['accounts'][9]['data'].__setitem__(0,'A'*6004),
            lambda v:v['value']['preBalances'].append(1)]
        for change in changes:
            bad=deepcopy(raw);change(bad)
            r=live.AtomicRpc(Opener([bad])).request('simulateTransaction',sp)
            self.assertEqual(r['state'],'invalid-atomic-simulation-response')
        compiled=response(a['capture'],d['unsignedTransactionBase64'],parsed=False)
        raw['value']['innerInstructions'][0]['instructions'][0]=compiled['value']['innerInstructions'][0]['instructions'][0]
        with self.assertRaises(ValueError):live.sanitize(dict(state='received',result=raw),sp)

    def test_transport_exact_arming_no_repeat_send_or_extra_request(self):
        a,p,d,e=fixture();t=AtomicTransport(Opener([None]*5),monotonic=lambda:1);t.calls=['getGenesisHash']*20
        def req(method,params):return urllib.request.Request(fresh_quote.ENDPOINTS['devnet'],
            data=json.dumps(dict(method=method,params=params,id=1)).encode())
        fp=e['feeParams'];sp=e['simulationParams']
        with self.assertRaises(ValueError):t.open(req('getFeeForMessage',fp),10)
        t.arm_atomic_fee(fp)
        with self.assertRaises(ValueError):t.arm_atomic_fee(fp)
        for method,params in [('sendTransaction',sp),('getFeeForMessage',[])]:
            with self.assertRaises(ValueError):t.open(req(method,params),10)
        t.open(req('getFeeForMessage',fp),10)
        with self.assertRaises(ValueError):t.open(req('getFeeForMessage',fp),10)
        t.arm_atomic_simulation(sp)
        with self.assertRaises(ValueError):t.arm_atomic_simulation(sp)
        bad=deepcopy(sp);bad[1]['sigVerify']=0
        with self.assertRaises(ValueError):t.open(req('simulateTransaction',bad),10)
        t.open(req('simulateTransaction',sp),10)
        with self.assertRaises(ValueError):t.open(req('simulateTransaction',sp),10)
        t.open(req('getGenesisHash',[]),10)
        with self.assertRaises(ValueError):t.open(req('getGenesisHash',[]),10)

    def test_oracle_numeric_reference_legacy_wrap_and_same_bank_second_instruction(self):
        raw=bytearray(4075);raw[8]=1;raw[43:51]=(100).to_bytes(8,'little')
        out=m.oracle_update(bytes(raw),110,2,4)
        self.assertEqual(int.from_bytes(out[51:67],'little'),(2<<32)*10)
        self.assertEqual(int.from_bytes(out[67:83],'little'),(1<<31)*10)
        self.assertEqual(int.from_bytes(out[43:51],'little'),100)
        self.assertEqual(m.oracle_update(out,110,3,7),out)
        out=m.oracle_update(out,115,2,4)
        self.assertEqual(int.from_bytes(out[9:11],'little'),1)
        self.assertEqual(int.from_bytes(out[83:91],'little'),115)
        self.assertEqual(int.from_bytes(out[91:107],'little'),(2<<32)*15)
        raw[9:11]=(99).to_bytes(2,'little');offset=43+99*40
        raw[offset:offset+8]=(100).to_bytes(8,'little');raw[offset+8:offset+24]=(2**128-1).to_bytes(16,'little')
        out=m.oracle_update(bytes(raw),115,1,1)
        self.assertEqual(int.from_bytes(out[9:11],'little'),0)
        self.assertEqual(int.from_bytes(out[51:67],'little'),(1<<32)*15-1)
        with self.assertRaises(ValueError):m.oracle_update(out,114,1,1)
        raw[8]=0;out=m.oracle_update(bytes(raw),115,1,1)
        self.assertEqual(out[8],1);self.assertEqual(out[offset+8:offset+40],bytes(32))

    def test_mode_and_cli_scope_no_execution_no_overwrite(self):
        for options in ({},{'simulate':True},{'simulate':True,'assess_costs':True},
                        dict(simulate=True,assess_costs=True,post_entry_projection=True,projected_exit_message=True)):
            with self.assertRaises(ValueError):fresh_quote.observe(Path('/unused'),'w','p',atomic_rehearsal=True,**options)
        cli=Path(__file__).with_name('atomic_live_cli.py')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'check.gz';cmd=[sys.executable,str(cli),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            original=out.read_bytes();self.assertEqual(json.loads(gzip.decompress(original))['casesPassed'],21)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(out.read_bytes(),original)
            cmd=[sys.executable,str(cli),'--output',str(Path(tmp)/'absent.gz')]
            for flags in (['--simulate-devnet'],['--allow-devnet-submit'],['--wallet','w'],['--action','execute']):
                self.assertNotEqual(subprocess.run(cmd+flags,capture_output=True).returncode,0)
            self.assertFalse((Path(tmp)/'absent.gz').exists())


if __name__=='__main__':unittest.main()
