import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch

import exit_balance as m
from exit_balance_checks import signed_case,collect_receipt,apply,observe,FakeRpc

HERE=Path(__file__).resolve().parent

class ExitBalanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager=signed_case();cls.c=cls.manager.__enter__()
        collect_receipt(cls.c);apply(cls.c);cls.stamp=cls.c.now
        b=cls.c.book()
        try:cls.ctx=m.context(b,cls.c.home,cls.c.wallet,cls.c.pool,lambda:cls.c.now)
        finally:b.close()
        sink=[];r=observe(cls.c,_evidence_sink=sink.append)
        assert r['balanceReconciliationPassed'],r
        cls.capture=sink[0]
    @classmethod
    def tearDownClass(cls):cls.manager.__exit__(None,None,None)
    def setUp(self):self.c.now=self.stamp
    def tearDown(self):
        (self.c.home/'STOP').unlink(missing_ok=True);self.c.now=self.stamp

    def test_portable_cli(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz';cmd=[sys.executable,'-E','-s',str(HERE/'exit_balance_cli.py'),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=out.read_bytes();v=json.loads(gzip.decompress(raw));self.assertEqual(v['casesPassed'],18)
            self.assertTrue(all(x=='passed' for x in v['cases'].values()));self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(raw,out.read_bytes())
            self.assertNotEqual(subprocess.run(cmd+['--allow-devnet-submit'],capture_output=True).returncode,0)

    def test_private_capture_tampering_and_expiry(self):
        for name,mutate in (
            ('identity',lambda c:c['identity'].update(accountingSha256='0'*64)),
            ('roles',lambda c:c['accountKeys'].reverse()),
            ('trace',lambda c:c['requestTrace'][1].update(parametersSha256='0'*64)),
            ('future',lambda c:c.update(startedAtMs=self.stamp+1)),
            ('order',lambda c:c['evidence']['accounts'].update(receivedAtMs=self.stamp-1)),
            ('genesis',lambda c:c['evidence']['genesisAfter'].update(result=m.GENESIS['mainnet-beta'])),
        ):
            with self.subTest(name=name):
                c=deepcopy(self.capture);mutate(c)
                with self.assertRaises(ValueError):m.review(self.ctx,c,self.stamp)
        with self.assertRaisesRegex(ValueError,'balance-expired'):m.review(self.ctx,self.capture,self.capture['startedAtMs']+m.FRESH_MS)
        with self.assertRaises(ValueError):m.review(self.ctx,{'snapshot':'public-report'},self.stamp)

    def test_stop_during_response_and_no_extra_request(self):
        def callback(method):
            if method=='getMultipleAccounts':(self.c.home/'STOP').touch(mode=0o600)
        rpc=FakeRpc(self.c,callback=callback);before=self.c.path.read_bytes();r=observe(self.c,rpc)
        self.assertEqual(r['diagnosticCode'],'balance-stopped');self.assertEqual(len(rpc.requests),2)
        self.assertEqual(before,self.c.path.read_bytes())

    def test_changed_source_after_observation_does_not_deliver(self):
        original=m.context;calls=[];sink=[]
        def changed(*a,**kw):
            c=original(*a,**kw);calls.append(True)
            if len(calls)==2:c['identity']['accountingSha256']='0'*64
            return c
        with patch.object(m,'context',changed):r=observe(self.c,_evidence_sink=sink.append)
        self.assertEqual(r['diagnosticCode'],'balance-source-changed');self.assertFalse(sink)

    def test_changed_controlled_commitments_stop_before_network(self):
        original=deepcopy(self.c.e['costInputs']['reservations'])
        for key,value in (('ledgerHeadSha256','0'*64),('nativeHeldLamports','1'),('phase','open')):
            current=deepcopy(original);current[key]=value;rpc=FakeRpc(self.c)
            with patch.object(m.view,'read_locked',return_value=current):r=observe(self.c,rpc)
            self.assertEqual(r['diagnosticCode'],'balance-source-changed');self.assertFalse(rpc.requests)

    def test_monotonic_budget_and_slow_sink_remain_unavailable(self):
        ticks=iter([0,0,10])
        rpc=m.Rpc(self.c.home,self.ctx,lambda:self.stamp,lambda:next(ticks),FakeRpc(self.c))
        with self.assertRaisesRegex(ValueError,'balance-expired'):rpc.request('getGenesisHash',[])
        self.assertEqual(len(rpc.calls),1)
        def sink(_):self.c.now+=m.FRESH_MS
        r=observe(self.c,_evidence_sink=sink)
        self.assertEqual(r['diagnosticCode'],'balance-expired');self.assertFalse(r['balanceReconciliationPassed']);self.assertIsNone(r['snapshot'])

    def test_transport_order_parameters_and_bounded_errors(self):
        for method,params in (('sendTransaction',[]),('getMultipleAccounts',[]),('getGenesisHash',['extra'])):
            rpc=m.Rpc(self.c.home,self.ctx,lambda:self.stamp,lambda:0,FakeRpc(self.c))
            with self.assertRaises(ValueError):rpc.request(method,params)
            self.assertFalse(rpc.calls)
        class BytesRpc:
            def __init__(self,raw):self.raw=raw;self.calls=0
            def open(self,*args,**kw):self.calls+=1;return io.BytesIO(self.raw)
        for raw in (b'x'*(m.MAX_RESPONSE+1),b'{"jsonrpc":"2.0","id":1,"id":1,"result":"x"}',
                    b'{"jsonrpc":"2.0","id":true,"result":"x"}',b'{"jsonrpc":"2.0","id":1,"error":{"message":"private"}}'):
            opener=BytesRpc(raw);rpc=m.Rpc(self.c.home,self.ctx,lambda:self.stamp,lambda:0,opener)
            with self.assertRaises(ValueError):rpc.request('getGenesisHash',[])
            self.assertEqual(opener.calls,1)

    def test_readonly_collection_does_not_import_writes_or_signing(self):
        before=self.c.path.read_bytes();opener=FakeRpc(self.c)
        with patch.object(m.accounting,'apply',side_effect=AssertionError('apply')),patch.object(m.accounting.submission,'submit',side_effect=AssertionError('send')):
            r=observe(self.c,opener)
        self.assertTrue(r['balanceReconciliationPassed']);self.assertEqual(before,self.c.path.read_bytes())
        self.assertEqual(r['requestMethods'],list(m.METHODS));self.assertFalse(r['reservationReleased'])

if __name__=='__main__':unittest.main()
