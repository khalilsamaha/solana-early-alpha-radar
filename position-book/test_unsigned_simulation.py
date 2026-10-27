"""Unsigned simulation over fake HTTP plus own-bank adverse effect cases."""
import base64
from copy import deepcopy
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.request

import fresh_quote
import unsigned_simulation as sim
from unsigned_simulation_checks import fixture, run, simulation_response
import test_fresh_quote as fixture_tests
from test_fresh_quote import Opener, responses, Clock, NOW, GENESIS


class SimulationOpener(Opener):
    def __init__(self,first,second,scope,change=None,hook=None,cluster=None):
        super().__init__(responses(first,second),hook)
        self.capture=deepcopy(second); self.scope=scope; self.change=change; self.cluster=cluster
        self.output=fresh_quote.derive(fresh_quote.preflight.split_capture(first)[0],scope,
                                      slippage_bps=100,now_ms=first['finishedAtMs'])['quote']['outAmount']

    def open(self,request,timeout):
        body=json.loads(request.data)
        if len(self.calls)>=18:
            if body['method']=='simulateTransaction':
                c=self.capture; c['packet']['unsignedTransactionBase64']=body['params'][0]
                c['packet']['policy'].update({k:v for k,v in self.scope.items() if k!='format'})
                c['packet']['feeAssertion']['lamports']='5000'
                value=simulation_response(c,self.output)
                if self.change:self.change(value)
            else:value=self.cluster or GENESIS['devnet']
            self.responses.append(value)
        return super().open(request,timeout)


class UnsignedSimulationTests(unittest.TestCase):
    def observe(self,change=None,hook=None,cluster=None,**kwargs):
        return fixture_tests.FreshQuoteTests().run_observe(simulate=True,
            opener_factory=lambda f,s,scope:SimulationOpener(f,s,scope,change,hook,cluster),**kwargs)

    def test_offline_cases(self):
        self.assertEqual(run()['casesPassed'],13)

    def test_complete_real_collectors_with_one_exact_unsigned_simulation(self):
        r,o=self.observe()
        self.assertEqual(r['state'],'unsigned-quote-simulation-consistent',r)
        self.assertTrue(r['simulationVerified']);self.assertEqual(r['networkRequests'],20)
        self.assertEqual(r['simulation']['simulatedOutputAtomic'],'906')
        self.assertEqual(r['simulation']['feeLamports'],'5000')
        self.assertEqual(r['simulation']['messageSha256'],r['preflight']['wireMessageSha256'])
        self.assertFalse(r['privateKeyAccessed']); self.assertFalse(r['sourceStateChanged'])
        self.assertFalse(r['executionApproved']); self.assertFalse(r['nextCycleAuthorized'])
        self.assertEqual(r['signaturesCreated'],0);self.assertEqual(r['transactionsSent'],0)
        requests=[x for x in o.calls if x['method']=='simulateTransaction']
        self.assertEqual(len(requests),1)
        wire,opts=requests[0]['params']
        self.assertEqual(base64.b64decode(wire)[:65],b'\x01'+bytes(64))
        self.assertIs(opts['sigVerify'],False); self.assertIs(opts['replaceRecentBlockhash'],False)
        self.assertEqual(opts['commitment'],'finalized');self.assertEqual(len(opts['accounts']['addresses']),8)

    def test_failures_never_pass_or_retry(self):
        mutations=[lambda v:v['value'].pop('preTokenBalances'),
            lambda v:v['value'].update(err={'private-provider-error':'do not export'}),
            lambda v:v['value'].update(accounts=None),
            lambda v:v['value'].update(replacementBlockhash={'blockhash':'changed'}),
            lambda v:v['value']['accounts'][7].update(lamports=1),
            lambda v:v['value']['postTokenBalances'][1]['uiTokenAmount'].update(amount='999999')]
        for change in mutations:
            r,o=self.observe(change)
            self.assertEqual(r['state'],'unavailable',r);self.assertFalse(r['simulationVerified'])
            self.assertEqual(len([x for x in o.calls if x['method']=='simulateTransaction']),1)
            self.assertNotIn('private-provider-error',json.dumps(r))

    def test_own_prestate_is_required_and_changed_vaults_are_not_old_price_passes(self):
        c,p,item=fixture(); v=item['result']['value']
        # Keep a valid input delta but shift both actual before/after vault state.
        v['preTokenBalances'][2]['uiTokenAmount']['amount']='10001'
        v['postTokenBalances'][2]['uiTokenAmount']['amount']=str(int(v['postTokenBalances'][2]['uiTokenAmount']['amount'])+1)
        row=v['accounts'][3]; raw=bytearray(base64.b64decode(row['data'][0]));raw[64:72]=(int.from_bytes(raw[64:72],'little')+1).to_bytes(8,'little');row['data'][0]=base64.b64encode(raw).decode()
        with self.assertRaisesRegex(ValueError,'simulation-prestate-changed'):
            sim.review(c['packet'],c,p,item,now_ms=NOW)

    def test_consistent_but_different_output_is_not_price_agreement(self):
        c,p,item=fixture()
        x=simulation_response(c,str(int(p['quote']['outAmount'])+1)); x['value']['failed']=False
        with self.assertRaisesRegex(ValueError,'simulation-quote-effects-differ'):
            sim.review(c['packet'],c,p,dict(state='received',result=x),now_ms=NOW)

    def test_late_response_cluster_change_stop_and_final_ledger_change(self):
        clock=Clock()
        def late(n,b):
            if n==19:clock.at+=10001
        r,o=self.observe(clock=clock,hook=late)
        self.assertEqual(r['state'],'unavailable');self.assertFalse(r['simulationVerified'])
        self.assertEqual(len(o.calls),19)
        r,_=self.observe(cluster=GENESIS['mainnet-beta'])
        self.assertEqual(r['state'],'unavailable');self.assertFalse(r['simulationVerified'])
        def ledger(n,v):
            if n==3:v['ledgerHeadSha256']='c'*64
        r,_=self.observe(ledger_hook=ledger)
        self.assertEqual(r['stage'],'post-simulation-reservations');self.assertEqual(r['state'],'unavailable')
        self.assertFalse(r['simulationVerified'])
        stop=[False]
        def stopping(n,b):
            if n==19:stop[0]=True
        r,_=self.observe(hook=stopping,stop=lambda _:stop[0])
        self.assertEqual(r['state'],'unavailable');self.assertFalse(r['simulationVerified'])

    def test_final_local_read_cannot_refresh_an_expired_quote_or_regress_clock(self):
        for mode in ('expired','regressed'):
            clock=Clock()
            def ledger(n,v):
                if n==3:
                    if mode=='expired':clock.at+=10001
                    else:clock.at-=100
            r,_=self.observe(clock=clock,ledger_hook=ledger)
            self.assertEqual(r['state'],'unavailable',r);self.assertFalse(r['simulationVerified'])

    def test_arm_exact_wire_flags_accounts_budget_and_no_send(self):
        c,p,item=fixture(); o=Opener([None]*30); t=sim.Transport(o,monotonic=lambda:1)
        def req(method,params):
            return urllib.request.Request(fresh_quote.ENDPOINTS['devnet'],data=json.dumps(dict(method=method,params=params,id=1)).encode())
        params=sim.parameters(c['packet'],c)
        for method in ('simulateTransaction','sendTransaction','requestAirdrop'):
            with self.assertRaises(ValueError):t.open(req(method,params),10)
        t.calls=['getGenesisHash']*18; t.arm(c['packet'],c,NOW)
        for field,value in [('sigVerify',True),('replaceRecentBlockhash',True),('minContextSlot',0)]:
            wrong=deepcopy(params);wrong[1][field]=value
            with self.assertRaises(ValueError):t.open(req('simulateTransaction',wrong),10)
        wrong=deepcopy(params);wrong[0]+='AAAA'
        with self.assertRaises(ValueError):t.open(req('simulateTransaction',wrong),10)
        wrong=deepcopy(params);wrong[1]['accounts']['addresses'].reverse()
        with self.assertRaises(ValueError):t.open(req('simulateTransaction',wrong),10)
        t.open(req('simulateTransaction',params),10)
        with self.assertRaises(ValueError):t.open(req('simulateTransaction',params),10)
        t.open(req('getGenesisHash',[]),10)
        with self.assertRaises(ValueError):t.open(req('getGenesisHash',[]),10)
        self.assertEqual(len(o.calls),2)

    def test_projection_bounds_and_sanitization(self):
        c,p,item=fixture();raw=item['result'];raw['value']['err']=None
        raw['value'].update(logs=['secret'],returnData={'private':'secret'})
        rpc=sim.SimulationRpc(Opener([raw]));got=rpc.request('simulateTransaction',[])
        self.assertNotIn('secret',json.dumps(got));self.assertEqual(got['state'],'received')
        for change in (lambda v:v['value']['accounts'][7]['data'].__setitem__(0,'x'*(sim.MAX_BASE64+1)),
                       lambda v:v['value'].update(preBalances=[0]*15),
                       lambda v:v['value']['preTokenBalances'].append({}),
                       lambda v:v['value'].update(fee=True)):
            bad=deepcopy(raw);change(bad)
            r=sim.SimulationRpc(Opener([bad])).request('simulateTransaction',[])
            self.assertEqual(r['state'],'invalid-simulation-response')

    def test_transport_failures_and_oversized_response_stay_unavailable(self):
        import urllib.error
        for failure in (urllib.error.URLError('secret'),TimeoutError('secret')):
            rpc=sim.SimulationRpc(Opener([failure]));r=rpc.request('simulateTransaction',[])
            self.assertEqual(r['state'],'network-error');self.assertNotIn('secret',json.dumps(r))
            self.assertEqual(len(rpc.calls),1)
        class Huge:
            def open(self,*args,**kwargs):return io.BytesIO(b'x'*(4*1024*1024+1))
        self.assertEqual(sim.SimulationRpc(Huge()).request('simulateTransaction',[])['state'],'response-too-large')

    def test_offline_cli_and_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'check.json.gz'
            args=[sys.executable,'-E','-s',str(Path(__file__).with_name('simulation_cli.py')),'--output',str(out)]
            r=subprocess.run(args,capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stderr)
            v=json.loads(gzip.decompress(out.read_bytes()));self.assertEqual(v['casesPassed'],13)
            self.assertEqual(v['networkRequests'],0);self.assertEqual(out.stat().st_mode&0o777,0o600)
            before=out.read_bytes();self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0)
            self.assertEqual(out.read_bytes(),before)


if __name__=='__main__':unittest.main()
