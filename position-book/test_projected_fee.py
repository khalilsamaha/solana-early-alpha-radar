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
import projected_fee as m
from projected_fee_checks import fixture,run
import test_fresh_quote as f
from test_post_entry_live import PoolOpener
from post_entry_simulation import FeeTransport,Transport
from core import GENESIS


class FeeOpener(PoolOpener):
    def __init__(self,*args,fee=6000,cluster=None,hook=None,**kw):
        super().__init__(*args,**kw);self.exit_fee=fee;self.exit_cluster=cluster;self.exit_hook=hook
    def open(self,request,timeout):
        if len(self.calls)<20:return super().open(request,timeout)
        body=json.loads(request.data)
        if self.exit_hook:self.exit_hook(len(self.calls)+1,body)
        value=dict(context=dict(slot=102),value=self.exit_fee) if len(self.calls)==20 else self.exit_cluster or GENESIS['devnet']
        self.responses.append(value)
        return f.Opener.open(self,request,timeout)


class ProjectedFeeTests(unittest.TestCase):
    def observe(self,fee=6000,cluster=None,hook=None,**kw):
        def observer(*args,**k):return f.m.observe(*args,**k,post_entry_projection=True,projected_exit_message=True,projected_exit_fee=True)
        return f.FreshQuoteTests().run_observe(simulate=True,assess_costs=True,observer=observer,
            opener_factory=lambda *a:FeeOpener(*a,fee=fee,cluster=cluster,hook=hook),**kw)

    def reject(self,r):
        self.assertEqual(r['state'],'unavailable',r);self.assertIsNone(r['projectedExitFee'])
        self.assertIsNone(r['projectedExitMessage']);self.assertFalse(r['simulationVerified'])
        self.assertFalse(r['liveCollectorVerified']);self.assertFalse(r['executionApproved'])

    def test_fee_is_message_specific_and_caps_not_double_counted(self):
        a,p,d,e=fixture();before=deepcopy((a,p,d,e));r=m.assess(a,p,d,e)
        self.assertEqual(r['state'],'projected-exit-fee-consistent',r)
        c=r['calculation'];self.assertEqual(c['entryObservedFeeLamports'],'5001')
        self.assertEqual(c['exitObservedFeeLamports'],'6000');self.assertEqual(c['observedTwoLegFeesLamports'],'11001')
        self.assertEqual(c['conditionalTwoLegCapLamports'],'12000');self.assertEqual(c['nativeRemainingAfterBothCapsLamports'],'88000')
        self.assertEqual(base64.b64decode(e['params'][0]),m.decode_wire(d['unsignedTransactionBase64'])[1])
        self.assertNotEqual(e['params'][0],d['unsignedTransactionBase64'])
        for k in ('executionApproved','signingApproved','roundTripFundingEstablished','walletWideReservationsKnown','exitSimulationVerified','actualEntryExecuted','liveCollectorVerified'):
            self.assertFalse(r[k],k)
        self.assertEqual((a,p,d,e),before);self.assertIsNone(r['failedAttemptBudgetLamports'])

    def test_all_portable_rejections_and_no_network(self):
        with patch('socket.socket',side_effect=AssertionError('network')):self.assertEqual(run()['casesPassed'],11)
        for value in (-1,0,True,3.2,'5000',None,2**64):
            a,p,d,e=fixture();e['fee']['result']['value']=value
            self.assertEqual(m.assess(a,p,d,e)['state'],'unavailable',value)

    def test_reversed_draft_and_parent_tamper_reject(self):
        for what in ('scope','hash','request','parent','future'):
            a,p,d,e=fixture()
            if what=='scope':d['scope']['amountIn']='1'
            if what=='hash':d['parentSimulationSha256']='0'*64
            if what=='request':e['params'][1]['minContextSlot']-=1
            if what=='parent':a['simulation_item']['result']['value']['accounts'].pop()
            if what=='future':e['finishedAtMs']=a['now_ms']+1
            self.assertEqual(m.assess(a,p,d,e)['state'],'unavailable',what)

    def test_full_collector_requests_exact_message_then_final_cluster(self):
        r,o=self.observe();self.assertEqual(r['state'],'controlled-projected-fee-observation-consistent',r)
        self.assertEqual(r['networkRequests'],22);self.assertEqual(r['requestMethods'][-2:],['getFeeForMessage','getGenesisHash'])
        self.assertEqual(r['requestMethods'].count('simulateTransaction'),1)
        b=r['projectedExitMessage']['binding'];e=r['projectedExitFee'];self.assertTrue(e['liveCollectorVerified'])
        self.assertEqual(e['evidence']['messageSha256'],b['messageSha256'])
        import hashlib
        self.assertEqual(hashlib.sha256(base64.b64decode(o.calls[20]['params'][0])).hexdigest(),b['messageSha256'])
        self.assertEqual(e['calculation']['observedTwoLegFeesLamports'],'11000')
        self.assertEqual(e['calculation']['conditionalTwoLegCapLamports'],'20000')
        self.assertEqual(r['transactionsSent'],0);self.assertNotIn('unsignedTransactionBase64',json.dumps(r))
        self.assertFalse(r['privateKeyAccessed']);self.assertFalse(r['sourceStateChanged'])

    def test_null_excess_fee_and_cluster_fail_without_retry(self):
        for fee in (None,True,10001):
            r,o=self.observe(fee=fee);self.reject(r);self.assertEqual(len(o.calls),21)
        r,o=self.observe(cluster=GENESIS['mainnet-beta']);self.reject(r);self.assertEqual(len(o.calls),22)

    def test_fee_deadline_and_last_local_read_remain_inside_original_window(self):
        for where in ('fee','cluster','ledger'):
            clock=f.Clock()
            def hook(n,b):
                if n==({'fee':21,'cluster':22}.get(where)):clock.at+=10001
            def ledger(n,v):
                if where=='ledger' and n==4:clock.at+=10001
            r,_=self.observe(clock=clock,hook=hook,ledger_hook=ledger);self.reject(r)

    def test_final_ledger_changes_unknown_reservations_and_stop_fail(self):
        for where in ('ledger','cycle','reserve','phase','stop'):
            stopped=[False]
            def ledger(n,v):
                if n==4:
                    if where=='ledger':v['ledgerHeadSha256']='c'*64
                    if where=='cycle':v['cycleBindingSha256']='c'*64
                    if where=='reserve':v['nativeHeldLamports']=None
                    if where=='phase':v['phase']='open'
                    if where=='stop':stopped[0]=True
            r,_=self.observe(ledger_hook=ledger,stop=lambda _:stopped[0]);self.reject(r)

    def test_transport_opt_in_exact_params_cap_and_no_send(self):
        a,p,d,e=fixture();o=f.Opener([None]*3);t=FeeTransport(o,monotonic=lambda:1)
        def req(method,params):return urllib.request.Request(f.m.ENDPOINTS['devnet'],data=json.dumps(dict(id=1,method=method,params=params)).encode())
        with self.assertRaises(ValueError):t.arm_fee(e['params'])
        t.calls=['getGenesisHash']*20
        with self.assertRaises(ValueError):t.open(req('getFeeForMessage',e['params']),10)
        t.arm_fee(e['params'])
        with self.assertRaises(ValueError):t.arm_fee(e['params'])
        for method,params in [('sendTransaction',e['params']),('simulateTransaction',p),('getFeeForMessage',[])]:
            with self.assertRaises(ValueError):t.open(req(method,params),10)
        t.open(req('getFeeForMessage',e['params']),10)
        with self.assertRaises(ValueError):t.open(req('getFeeForMessage',e['params']),10)
        t.open(req('getGenesisHash',[]),10)
        with self.assertRaises(ValueError):t.open(req('getGenesisHash',[]),10)
        old=Transport(o,monotonic=lambda:1);old.calls=['getGenesisHash']*20
        with self.assertRaises(ValueError):old.open(req('getFeeForMessage',e['params']),10)

    def test_cli_output_private_exclusive_no_send_flags(self):
        cli=Path(__file__).with_name('projected_fee_cli.py')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'out.gz';cmd=[sys.executable,'-E','-s',str(cli),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(json.loads(gzip.decompress(out.read_bytes()))['casesPassed'],11)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            original=out.read_bytes();self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(original,out.read_bytes())
            cmd[-1]=str(Path(tmp)/'absent.gz')
            for flag in ('--allow-devnet-submit','--simulate-devnet'):
                self.assertNotEqual(subprocess.run(cmd+[flag],capture_output=True).returncode,0)
            self.assertFalse((Path(tmp)/'absent.gz').exists())
        with self.assertRaises(ValueError):f.m.observe(Path('/unused'),'w','p',projected_exit_fee=True)


if __name__=='__main__':unittest.main()
