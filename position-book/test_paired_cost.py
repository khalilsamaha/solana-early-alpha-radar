from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import paired_cost as m
from paired_checks import fixture,leg,run,shift,NOW
import test_fresh_quote as f
from test_unsigned_simulation import SimulationOpener
from test_reverse_quote import ReverseOpener


class PairedCostTests(unittest.TestCase):
    def assess(self,a=None,b=None,attempts=1):
        if a is None:a,b=fixture()
        return m.assess(a,b,baseline=a['costInputs']['baseline'],failed_exit_attempts=attempts)

    def test_offline_checks(self):self.assertEqual(run()['casesPassed'],10)

    def test_cap_budget_not_fee_estimate_priority_or_historical_fees(self):
        a,b=fixture();before=deepcopy((a,b));r=self.assess(a,b)
        self.assertEqual((a,b),before);c=r['calculation']
        self.assertEqual(r['state'],'independent-leg-costs-consistent',r)
        self.assertEqual(c['observedIndependentFeeSumLamports'],'10002')
        self.assertEqual(c['modelledFeeCapBudgetLamports'],'18000')
        self.assertEqual(c['additionalFailedExitFeeAllowanceLamports'],'6000')
        self.assertTrue(c['modelledFeeCapBudgetCovered'])
        for key in ('executionApproved','roundTripFundingEstablished','currentFundingVerified',
                    'postEntryPoolObserved','actualExecutionObserved','authorizesRetries','reservationCreated'):
            self.assertFalse(r[key],key)
        self.assertIsNone(r['netProfit']);self.assertFalse(c['completeExecutionCostBudget'])
        self.assertEqual(c['actualNativeDebitLamports'],'0')

    def test_scenario_is_explicit_bounded_and_not_retry_authorization(self):
        for attempts,budget in [(0,'12000'),(1,'18000'),(2,'24000')]:
            self.assertEqual(self.assess(attempts=attempts)['calculation']['modelledFeeCapBudgetLamports'],budget)
        for invalid in (None,True,-1,3,'1',1.5):
            with self.assertRaises(ValueError):self.assess(attempts=invalid)
            with patch('paired_cost.fresh_quote.observe',side_effect=AssertionError('must not observe')):
                with self.assertRaises(ValueError):m.observe(Path('/unused'),'w','p',failed_exit_attempts=invalid)

    def test_native_shortfall_after_unchanged_reservations_stays_visible(self):
        a,b=fixture()
        for e in (a,b):e['costInputs']['reservations']['nativeHeldLamports']='90000'
        r=self.assess(a,b);c=r['calculation']
        self.assertEqual(r['state'],'independent-leg-costs-consistent',r)
        self.assertEqual(c['lowerObservedNativeSpendableLamports'],'10000')
        self.assertEqual(c['shortfallForModelledFeeCapsLamports'],'8000')
        self.assertFalse(c['modelledFeeCapBudgetCovered']);self.assertFalse(r['executionApproved'])

    def test_different_actual_native_balance_uses_lower_observation(self):
        a,b=fixture();args=b['costInputs'];c=args['capture'];c['evidence']['accounts']['result']['value'][8]['lamports']=15000
        from unsigned_simulation_checks import simulation_response
        x=simulation_response(c,args['price']['quote']['outAmount']);x['value']['failed']=False;x['value'].pop('err')
        args['simulation_item']['result']=x
        r=self.assess(a,b)
        self.assertEqual(r['state'],'independent-leg-costs-consistent',r)
        self.assertEqual(r['calculation']['shortfallForModelledFeeCapsLamports'],'3000')

    def test_old_entry_cannot_be_presented_as_current_funding(self):
        a,b=leg(),leg(True,16000);r=self.assess(a,b)
        self.assertEqual(r['state'],'independent-leg-costs-consistent',r)
        self.assertTrue(r['observationClocks']['entryExpiredAtPairCompletion'])
        self.assertFalse(r['currentFundingVerified']);self.assertFalse(r['roundTripFundingEstablished'])
        self.assertEqual(r['entryCostEvidence']['evaluatedAtMs'],a['completedAtMs'])
        a,b=leg(),leg(True,61000)
        self.assertEqual(self.assess(a,b)['state'],'unavailable')

    def test_reverse_order_same_slot_and_changed_scope_rejected(self):
        for case in ('order','slot','scope','reservations'):
            a,b=fixture()
            if case=='order':a,b=b,a
            if case=='slot':
                shift(b,-4000,-10)
                b['costInputs']['simulation_started']-=4000
                b['costInputs']['simulation_received']-=4000
                b['costInputs']['simulation_finished']-=4000
            if case=='scope':b['entryScope']['amountIn']='99'
            if case=='reservations':b['costInputs']['reservations']['tokenAccounts'][0]['heldAtomic']='1'
            self.assertEqual(self.assess(a,b)['state'],'unavailable',case)

    def test_individually_valid_legs_cannot_hide_changed_pool_or_partial_exit(self):
        from paired_checks import edit,derive,message,simulation_response
        import base64,hashlib
        for case in ('pool','quantity'):
            a,b=fixture();args=b['costInputs'];c=args['capture'];scope=b['scope']
            if case=='pool':
                edit(b['initialPool'],4,64,(10001).to_bytes(8,'little'))
                edit(c,4,64,(10001).to_bytes(8,'little'))
            else:scope['amountIn']='97'
            price=derive(b['initialPool'],scope,slippage_bps=100,now_ms=b['completedAtMs'])
            scope['minimumAmountOut']=price['quote']['minimumOutAmount']
            c['packet']['policy'].update({k:v for k,v in scope.items() if k!='format'})
            msg=message(scope,c['packet']['policy']['blockhash'])
            c['packet']['unsignedTransactionBase64']=base64.b64encode(b'\x01'+bytes(64)+msg).decode()
            c['packet']['feeAssertion']['messageSha256']=hashlib.sha256(msg).hexdigest()
            c['messageSha256']=c['packet']['feeAssertion']['messageSha256']
            args['price']=price
            value=simulation_response(c,price['quote']['outAmount'])
            value['value']['failed']=False;value['value'].pop('err')
            args['simulation_item']['result']=value
            self.assertEqual(m.cost_readiness.assess(**args)['state'],'single-leg-cost-evidence-consistent')
            r=self.assess(a,b)
            self.assertEqual(r['state'],'unavailable')
            self.assertEqual(r['reasons'],['pair-economic-inputs' if case=='pool' else 'pair-quantity'])

    def test_raw_handoff_is_only_emitted_after_successful_observation(self):
        observed=[]
        r,_=f.FreshQuoteTests().run_observe(simulate=True,assess_costs=True,evidence_sink=observed.append,
            opener_factory=SimulationOpener,stop=lambda _:True)
        self.assertEqual(r['state'],'unavailable');self.assertEqual(observed,[])
        def broken_sink(e):raise ValueError('private-callback-error')
        r,_=f.FreshQuoteTests().run_observe(simulate=True,assess_costs=True,evidence_sink=broken_sink,
            opener_factory=SimulationOpener)
        self.assertEqual(r['state'],'unavailable');self.assertFalse(r['simulationVerified'])
        self.assertNotIn('private-callback-error',json.dumps(r))

    def test_live_orchestration_real_collectors_never_exports_raw_or_sends(self):
        original=m.fresh_quote.observe;calls=[]
        _,_,base,scope=f.setup();a=scope['accounts']
        def observation(home,wallet,pool,**kw):
            reverse=kw['reverse_reference'];offset=4000 if reverse else 0
            clock=f.Clock();clock.at+=offset
            def mutate(first,second,scope):
                for c in (first,second):
                    shift(c,offset,10 if reverse else 0)
                    c['evidence']['blockTime']['result']+=offset//1000
            def ledger(n,v):
                if not reverse:v['tokenAccounts'].append(dict(account=a['destination'],mint=a['outputMint'],heldAtomic='0'))
            r,o=f.FreshQuoteTests().run_observe(mutate=mutate,clock=clock,ledger_hook=ledger,
                opener_factory=ReverseOpener if reverse else SimulationOpener,
                simulate=True,assess_costs=True,reverse_reference=reverse,
                evidence_sink=kw['_evidence_sink'],observer=original)
            calls.extend(o.calls);return r
        with patch('paired_cost.fresh_quote.observe',observation),patch('paired_cost.fresh_quote.preflight.BASELINE',base):
            r=m.observe(Path('/synthetic'),a['wallet'],a['pool'],failed_exit_attempts=1,clock=lambda:NOW+8000)
        self.assertEqual(r['state'],'independent-paired-cost-observation-consistent',r)
        self.assertEqual(len(calls),40);self.assertEqual(r['networkRequests'],40)
        self.assertEqual(sum(x['method']=='simulateTransaction' for x in calls),2)
        self.assertFalse(any(x['method']=='sendTransaction' for x in calls))
        self.assertEqual(r['pairedAssessment']['calculation']['modelledFeeCapBudgetLamports'],'30000')
        for secret in ('unsignedTransactionBase64','preTokenBalances','costInputs','initialPool'):
            self.assertNotIn(secret,json.dumps(r))
        for finish in (NOW, NOW+70000):
            calls.clear()
            with patch('paired_cost.fresh_quote.observe',observation),patch('paired_cost.fresh_quote.preflight.BASELINE',base):
                r=m.observe(Path('/synthetic'),a['wallet'],a['pool'],failed_exit_attempts=1,clock=lambda:finish)
            self.assertEqual(r['state'],'unavailable')
            self.assertEqual(len(calls),40);self.assertFalse(r['executionApproved'])

    def test_first_leg_failure_never_attempts_reverse_and_summaries_do_not_pass(self):
        for state in ('unavailable','controlled-cost-observation-consistent'):
            with patch('paired_cost.fresh_quote.observe',return_value=dict(state=state,networkRequests=4)) as observe:
                r=m.observe(Path('/unused'),'w','p',failed_exit_attempts=1)
            self.assertEqual(observe.call_count,1);self.assertEqual(r['networkRequests'],4)
            self.assertEqual(r['state'],'unavailable');self.assertIsNone(r['pairedAssessment'])

    def test_offline_cli_and_argument_guards(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'check.json.gz'
            args=[sys.executable,'-E','-s',str(Path(__file__).with_name('paired_cost_cli.py')),'--output',str(p)]
            r=subprocess.run(args,capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stderr)
            report=json.loads(gzip.decompress(p.read_bytes()));self.assertEqual(report['casesPassed'],10)
            self.assertEqual(report['networkRequests'],0);self.assertEqual(p.stat().st_mode&0o777,0o600)
            before=p.read_bytes();self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0)
            self.assertEqual(p.read_bytes(),before)
            for extra in (['--failed-exit-attempts','1'],['--simulate-devnet'],['--input','x']):
                command=args[:-1]+[str(Path(d)/'invalid.json.gz')]+extra
                self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
                self.assertFalse((Path(d)/'invalid.json.gz').exists())


if __name__=='__main__':unittest.main()
