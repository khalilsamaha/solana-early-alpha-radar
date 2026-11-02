import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import admission_timing as m
from admission_timing_checks import case,rejected
import test_fresh_quote as f
from test_unsigned_simulation import SimulationOpener

class TimingTests(unittest.TestCase):
    def pipeline(self,*,factory=None,clock=None,ledger_hook=None):
        base=f.setup()[2]
        def observer(home,wallet,pool,**kw):
            return m.observe(home,wallet,pool,opener=kw['opener'],clock=kw['clock'],monotonic=lambda:0,
                maximum_exit_attempts=2,maximum_exit_fee_lamports='10000',maximum_total_fee_lamports='30000')
        with patch.object(m.admission,'BASELINE',base),patch.object(m,'vacant'),\
             patch('socket.socket',side_effect=AssertionError('real network')),\
             patch.object(m.admission,'Admission',side_effect=AssertionError('write')):
            return f.FreshQuoteTests().run_observe(simulate=True,assess_costs=True,refreshed_deployment=True,
                observer=observer,opener_factory=factory or (lambda a,b,s:SimulationOpener(a,b,s)),
                clock=clock,ledger_hook=ledger_hook)

    def test_real_collectors_raw_validation_and_exact_unsigned_request(self):
        r,o=self.pipeline();self.assertEqual(r['state'],'entry-admission-timing-consistent',r)
        self.assertEqual(r['networkRequests'],20);self.assertEqual(len(o.calls),20)
        self.assertEqual(r['assessment']['projectedFeeCommitmentLamports'],'30000')
        self.assertEqual([v['stage'] for v in r['timings']],['local-slot-check','fresh-entry-collection','locked-source-before','raw-admission-validation','locked-source-after'])
        self.assertGreater(r['remainingMs'],0);self.assertEqual(r['originalDeadlineMs']-r['completedAtMs'],r['remainingMs'])
        params=next(v['params'] for v in o.calls if v['method']=='simulateTransaction')
        self.assertFalse(params[1]['sigVerify']);self.assertFalse(params[1]['replaceRecentBlockhash'])
        self.assertFalse(r['signingApproved']);self.assertFalse(r['admissionLedgerCreated'])
        self.assertNotIn('sendTransaction',r['requestMethods']);self.assertNotIn(params[0],json.dumps(r))

    def test_failed_rpc_not_retried_and_error_sanitized(self):
        import urllib.error
        def factory(a,b,s):
            rows=f.responses(a,b);rows[3]=urllib.error.URLError('do-not-export-secret')
            return f.Opener(rows)
        r,o=self.pipeline(factory=factory);rejected(r)
        self.assertEqual(len(o.calls),4);self.assertEqual(r['networkRequests'],4)
        self.assertNotIn('do-not-export-secret',json.dumps(r));self.assertEqual(r['collectionStage'],'pool-quote')

    def test_real_collector_source_change_and_deadline_not_refreshed(self):
        clock=f.Clock()
        def changed(n,r):
            if n==4:r['ledgerHeadSha256']='c'*64
        r,o=self.pipeline(clock=clock,ledger_hook=changed);rejected(r);self.assertEqual(len(o.calls),20)
        original=m.admission.review
        def slow(*args,**kw):
            r=original(*args,**kw);clock.at=r['validUntilExclusiveMs'];return r
        clock=f.Clock()
        with patch.object(m.admission,'review',slow):r,o=self.pipeline(clock=clock)
        rejected(r);self.assertLessEqual(r['remainingMs'],0);self.assertEqual(len(o.calls),20)

    def test_clock_cannot_regress_between_stages(self):
        r=m.base();ticks=iter([100,110])
        with m.phase(r,'first',lambda:next(ticks),lambda:0):pass
        with self.assertRaisesRegex(ValueError,'timing-clock-regression'):
            with m.phase(r,'second',lambda:105,lambda:0):self.fail('regressed clock entered phase')
        self.assertEqual(r['lastMeasuredAtMs'],110)

    def test_original_earlier_binding_deadline_wins(self):
        def shorter(c,k,r):r['binding']['binding']['validUntilExclusiveMs']=c.now+1
        with case(collector_hook=shorter,review_hook=lambda c,r:setattr(c,'now',c.now+1)) as c:
            r=c.run();rejected(r);self.assertEqual(r['remainingMs'],0)

    def test_source_slot_created_during_collection_preserves_it(self):
        def appeared(c,k,r):(c.home.parent/(c.home.name+'-entry-handoff-v1')).mkdir()
        with case(collector_hook=appeared) as c:
            r=c.run();rejected(r);self.assertEqual(r['diagnosticCode'],'timing-existing-admission')
            self.assertTrue((c.home.parent/(c.home.name+'-entry-handoff-v1')).is_dir())
            self.assertEqual(c.collections,1)

    def test_missing_raw_handoff_is_unavailable(self):
        with case() as c:
            original=m.fresh_quote.observe
            def missing(*args,**kwargs):kwargs['_evidence_sink']=lambda value:None;return original(*args,**kwargs)
            with patch.object(m.fresh_quote,'observe',missing):r=c.run()
            rejected(r);self.assertEqual(r['diagnosticCode'],'timing-raw-handoff')

    def test_offline_cli_private_exclusive_and_rejects_execution_or_incomplete_scope(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.json.gz';cmd=[sys.executable,'-E','-s',str(Path(__file__).with_name('admission_timing_cli.py')),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=out.read_bytes();v=json.loads(gzip.decompress(raw));self.assertEqual(v['casesPassed'],30)
            self.assertEqual(v['timingOptimization'],'exact-signature-replay-1')
            self.assertEqual(out.stat().st_mode&0o777,0o600);self.assertEqual(v['realNetworkRequests'],0)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(raw,out.read_bytes())
            for opts in (['--allow-devnet-submit'],['--observe-devnet'],['--wallet','missing']):
                other=cmd[:-1]+[str(Path(d)/'other.gz')]+opts
                self.assertNotEqual(subprocess.run(other,capture_output=True).returncode,0)
                self.assertFalse((Path(d)/'other.gz').exists())

if __name__=='__main__':unittest.main()
