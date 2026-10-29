"""Cost assessment consumes raw evidence, preserves unknowns and cannot authorize."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import fresh_quote as observer
import cost_readiness as m
from cost_checks import fixture,run,NOW
import test_fresh_quote as f
from test_unsigned_simulation import SimulationOpener


class CostReadinessTests(unittest.TestCase):
    def test_synthetic_rejections_and_cap_not_observed_fee(self):
        r=run();self.assertEqual(r['casesPassed'],13)
        good=r['cases']['consistent-single-leg'];c=good['calculation']
        self.assertEqual(c['requiredNativeForThisLegLamports'],'6000')
        self.assertEqual(c['simulatedNetworkFeeLamports'],'5001')
        self.assertEqual(c['nativeRemainingAfterCapLamports'],'94000')
        self.assertEqual(c['feeCapHeadroomLamports'],'999')
        self.assertIsNone(c['exitFeeBudgetLamports']);self.assertIsNone(c['failedAttemptBudgetLamports'])
        self.assertEqual(good['economics']['state'],'unavailable');self.assertIsNone(good['economics']['calculation'])
        self.assertFalse(good['executionApproved']);self.assertFalse(good['measuredNetProfit'])

    def test_reserved_funds_and_historical_fees_are_not_double_counted(self):
        x=fixture();x['reservations'].update(nativeHeldLamports='2000',confirmedFeeLamports='999999999')
        x['reservations']['tokenAccounts'][0]['heldAtomic']='100'
        c=m.assess(**x)['calculation']
        self.assertEqual(c['nativeSpendableLamports'],'98000')
        self.assertEqual(c['nativeRemainingAfterCapLamports'],'92000')
        self.assertEqual(c['tokenSpendableAtomic'],'900');self.assertEqual(c['tokenRemainingAfterInputAtomic'],'800')

    def test_no_mutation_and_contract_module_names_do_not_collide(self):
        import contract
        original=contract;x=fixture();before=deepcopy(x)
        self.assertEqual(m.assess(**x)['state'],'single-leg-cost-evidence-consistent')
        self.assertEqual(x,before);self.assertIs(sys.modules['contract'],original)
        self.assertTrue(hasattr(original,'validate'));self.assertTrue(hasattr(m.cost,'evaluate'))

    def test_each_clock_ledger_and_scope_rejection(self):
        mutations=[lambda x:x.update(now_ms=True),lambda x:x.update(now_ms=NOW-1),
            lambda x:x['reservations'].update(readStartedAtMs=NOW),
            lambda x:x['reservations'].update(ledgerHeadSha256='invalid'),
            lambda x:x['reservations'].update(wallet='wrong'),
            lambda x:x['reservations']['tokenAccounts'].append(deepcopy(x['reservations']['tokenAccounts'][0])),
            lambda x:x['simulation_item']['result']['value'].update(fee=6001),
            lambda x:x['price']['quote'].update(requestedAtMs=NOW-10001)]
        for mutate in mutations:
            x=fixture();mutate(x);r=m.assess(**x)
            self.assertEqual(r['state'],'unavailable',r);self.assertIsNone(r['calculation'])

    def observe(self,**kw):
        return f.FreshQuoteTests().run_observe(simulate=True,assess_costs=True,
            refreshed_deployment=True,
            opener_factory=lambda a,b,s:SimulationOpener(a,b,s),**kw)

    def test_full_pipeline_costs_use_raw_evidence_and_final_local_read(self):
        r,o=self.observe()
        self.assertEqual(r['state'],'controlled-cost-observation-consistent',r)
        self.assertEqual(len(o.calls),20);self.assertTrue(r['simulationVerified'])
        c=r['costReadiness'];self.assertEqual(c['state'],'single-leg-cost-evidence-consistent')
        self.assertEqual(c['evidence']['simulationEvidenceSha256'],r['simulation']['evidenceSha256'])
        self.assertEqual(c['calculation']['networkFeeCapLamports'],'10000')
        self.assertEqual(c['calculation']['observedNetworkFeeLamports'],'5000')
        self.assertEqual(c['calculation']['tokenRemainingAfterInputAtomic'],'0')
        self.assertEqual(c['economics']['state'],'unavailable')
        self.assertFalse(r['sourceStateChanged']);self.assertFalse(r['privateKeyAccessed'])
        self.assertNotIn('unsignedTransactionBase64',json.dumps(r))
        self.assertNotIn('preTokenBalances',json.dumps(r))

    def test_post_simulation_reservation_failure_still_refuses(self):
        def change(n,v):
            if n==3:v['nativeHeldLamports']='9999999'
        r,o=self.observe(ledger_hook=change)
        self.assertEqual(r['state'],'unavailable');self.assertFalse(r['simulationVerified'])
        self.assertEqual(r['costReadiness']['state'],'unavailable');self.assertEqual(len(o.calls),20)

    def test_cost_computation_cannot_extend_original_deadline(self):
        clock=f.Clock();real=m.assess
        def slow(*a,**kw):
            r=real(*a,**kw);clock.at+=10001;return r
        with patch('cost_readiness.assess',slow):r,o=self.observe(clock=clock)
        self.assertEqual(r['state'],'unavailable');self.assertFalse(r['simulationVerified'])
        self.assertEqual(r['diagnosticCode'],'observation-expired-before-completion')

    def test_raw_simulation_handoff_fails_closed(self):
        import unsigned_simulation as sim
        original=sim.collect
        def no_raw(*a,**kw):kw.pop('_evidence_sink');return original(*a,**kw)
        with patch('unsigned_simulation.collect',no_raw):r,o=self.observe()
        self.assertEqual(r['state'],'unavailable');self.assertFalse(r['simulationVerified'])
        self.assertIsNone(r['costReadiness'])

    def test_no_cost_mode_without_simulation(self):
        with self.assertRaisesRegex(ValueError,'costs-require-simulation'):
            observer.observe(Path('/unused'),'wallet','pool',assess_costs=True)

    def test_cli_offline_private_exclusive_and_no_input_report_mode(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'report.json.gz'
            args=[sys.executable,'-E','-s',str(Path(__file__).with_name('cost_cli.py')),'--output',str(path)]
            r=subprocess.run(args,capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stderr)
            saved=path.read_bytes();data=json.loads(gzip.decompress(saved))
            self.assertEqual(data['casesPassed'],13);self.assertEqual(data['networkRequests'],0)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(args,capture_output=True,timeout=15).returncode,0)
            self.assertEqual(path.read_bytes(),saved)
            self.assertNotEqual(subprocess.run(args+['--input',str(path)],capture_output=True,timeout=15).returncode,0)


if __name__=='__main__':unittest.main()
