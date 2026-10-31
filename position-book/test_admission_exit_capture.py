"""Collector ordering, deadline and actual offline CLI evidence boundaries."""
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

import admission_exit_capture_checks as c


class ExitCaptureTests(unittest.TestCase):
    def test_all_portable_cases_and_cli_output_exclusivity(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'result.json.gz'
            args=[sys.executable,'-E','-s',str(Path(__file__).with_name('admission_exit_capture_cli.py')),'--output',str(path)]
            proc=subprocess.run(args,capture_output=True,text=True,timeout=90)
            self.assertEqual(proc.returncode,0,proc.stderr)
            r=json.loads(gzip.decompress(path.read_bytes()))
            self.assertEqual(r['casesPassed'],19);self.assertEqual(len(r['cases']),19)
            self.assertEqual(r['networkRequests'],0);self.assertFalse(r['executionApproved'])
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            old=path.read_bytes()
            self.assertNotEqual(subprocess.run(args,capture_output=True,timeout=10).returncode,0)
            self.assertEqual(path.read_bytes(),old)

    def test_exact_transport_order_endpoint_and_monotonic_budget(self):
        first,e,b=c.setup(type('C',(),{'wallet':c.preflight_fixture(True)[0]['packet']['policy']['accounts']['wallet']})())
        rpc=c.Opener(first,e);clock=c.Clock()
        with patch.object(c.m.view.cycles.c.submit.swap,'stop',return_value=False):
            t=c.m.Transport(Path('/unused'),clock,rpc,lambda:0,clock())
            def req(method,url=c.m.fresh_quote.ENDPOINTS['devnet']):
                return urllib.request.Request(url,data=json.dumps(dict(method=method,params=[],id=1)).encode())
            for method in ('sendTransaction','requestAirdrop','simulateTransaction','getFeeForMessage'):
                with self.assertRaises(ValueError):t.open(req(method),10)
            with self.assertRaises(ValueError):t.open(req('getGenesisHash','https://api.mainnet-beta.solana.com'),10)
            self.assertEqual(rpc.calls,[])
            t.calls=list(c.m.METHODS)
            with self.assertRaises(ValueError):t.open(req('getGenesisHash'),10)
            t.calls=[];t.monotonic=lambda:31
            with self.assertRaises(ValueError):t.open(req('getGenesisHash'),10)
            self.assertEqual(rpc.calls,[])

    def test_final_local_validation_counts_toward_deadline(self):
        with c.case() as case:
            c.settle(case);c.apply(case);clock=c.Clock();sink=[]
            original=c.m.exit.review
            def slow(*args):
                r=original(*args);clock.at+=10000;return r
            old=case.path.read_bytes()
            with patch.object(c.m.exit,'review',side_effect=slow):
                r,rpc=c.capture(case,clock=clock,sink=sink.append)
            self.assertEqual(r['diagnosticCode'],'exit-capture-expired');self.assertEqual(sink,[])
            self.assertEqual(len(rpc.calls),20);self.assertEqual(case.path.read_bytes(),old)

    def test_provenance_hashing_counts_toward_deadline(self):
        with c.case() as case:
            c.settle(case);c.apply(case);clock=c.Clock();sink=[]
            original=c.m.digest
            def slow(value):
                result=original(value)
                if isinstance(value,list) and len(value)==20:clock.at+=10000
                return result
            old=case.path.read_bytes()
            with patch.object(c.m,'digest',side_effect=slow):
                r,_=c.capture(case,clock=clock,sink=sink.append)
            self.assertEqual(r['diagnosticCode'],'exit-capture-expired');self.assertEqual(sink,[])
            self.assertEqual(case.path.read_bytes(),old)

    def test_private_result_remains_compatible_with_existing_raw_preparation(self):
        with c.case() as case:
            c.settle(case);c.apply(case);items=[]
            r,_=c.capture(case,sink=items.append)
            self.assertEqual(r['state'],'exit-evidence-collected-research-only')
            case.now=r['provenance']['completedAtMs']+1
            _,_,b=c.setup(case)
            prepared=c.prepare(case,items[0]['evidence'],b)
            self.assertTrue(prepared['createdThisRun'])
            self.assertEqual(prepared['binding']['entryAccountingSha256'],r['binding']['entryAccountingSha256'])
            self.assertFalse(prepared['signingApproved'])
            old=case.path.read_bytes()
            later=c.Clock();later.at=case.now+10
            stopped,rpc=c.capture(case,clock=later)
            self.assertEqual(stopped['diagnosticCode'],'exit-capture-already-prepared')
            self.assertEqual(rpc.calls,[]);self.assertEqual(case.path.read_bytes(),old)


if __name__=='__main__':unittest.main()
