"""Reverse direction through actual collectors/parsers over fake HTTP only."""
import base64
from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import fresh_quote
import reverse_checks
from reverse_quote import prepare
import test_fresh_quote as fixture_tests
from test_fresh_quote import Clock, edit, NOW
from test_unsigned_simulation import SimulationOpener


class ReverseOpener(SimulationOpener):
    def __init__(self,first,second,scope,change=None,hook=None,funds=1000):
        reverse, _, _ = prepare(fresh_quote.preflight.split_capture(first)[0],scope,now_ms=first['finishedAtMs'])
        # Source is now the existing destination account. No hypothetical credit.
        edit(second,10,64,funds.to_bytes(8,'little'))
        second['accountKeys'][9],second['accountKeys'][10]=second['accountKeys'][10],second['accountKeys'][9]
        rows=second['evidence']['accounts']['result']['value']
        rows[9],rows[10]=rows[10],rows[9]
        super().__init__(first,second,reverse,change,hook)


class ReverseTests(unittest.TestCase):
    def observe(self,change=None,hook=None,funds=1000,**kwargs):
        return fixture_tests.FreshQuoteTests().run_observe(simulate=True,assess_costs=True,reverse_reference=True,
            opener_factory=lambda f,s,scope:ReverseOpener(f,s,scope,change,hook,funds),**kwargs)

    def test_offline_checks(self):
        self.assertEqual(reverse_checks.run()['casesPassed'],10)

    def test_reverse_raw_flow_has_exact_quantity_and_no_execution(self):
        r,o=self.observe()
        self.assertEqual(r['state'],'controlled-reverse-cost-observation-consistent',r)
        ref=r['reverseReference']; q=r['quote']['quote']
        self.assertEqual(q['inAmount'],ref['referenceEntryOutputAtomic'])
        self.assertEqual(q['source'],ref['entryReference']['quote']['destination'])
        self.assertEqual(r['costReadiness']['calculation']['simulatedOutputAtomic'],q['outAmount'])
        self.assertEqual(r['feePlan']['knownFeeCapSubtotalLamports'],'20000')
        self.assertFalse(r['feePlan']['roundTripFundingEstablished'])
        self.assertIsNone(ref['quotedRoundTripReturnPct']);self.assertFalse(ref['entryExecuted'])
        self.assertFalse(ref['entryFundingVerified']);self.assertFalse(ref['entrySimulationVerified'])
        self.assertFalse(r['sourceStateChanged']);self.assertFalse(r['privateKeyAccessed'])
        self.assertEqual(r['transactionsSent'],0);self.assertEqual(r['signaturesCreated'],0)
        self.assertEqual(len(o.calls),20)
        calls=[x for x in o.calls if x['method']=='simulateTransaction']
        self.assertEqual(len(calls),1)
        self.assertEqual(base64.b64decode(calls[0]['params'][0])[:65],b'\x01'+bytes(64))
        self.assertFalse(calls[0]['params'][1]['sigVerify'])
        self.assertNotIn('validated-exit-leg-absent',r['costReadiness']['economics']['reasons'])
        self.assertFalse(any(x.startswith('Exit and failed-attempt') for x in r['costReadiness']['limitations']))
        self.assertTrue(any('existing actual token' in x for x in r['limitations']))
        self.assertFalse(any('18 public' in x for x in r['limitations']))

    def test_expected_proceeds_cannot_replace_actual_reverse_funds(self):
        for funds in (0,905):
            r,o=self.observe(funds=funds)
            self.assertEqual(r['state'],'unavailable',r)
            self.assertFalse(any(x['method']=='simulateTransaction' for x in o.calls))
        r,_=self.observe(funds=906)
        self.assertEqual(r['state'],'controlled-reverse-cost-observation-consistent',r)

    def test_unknown_or_reserved_reverse_funds_and_changed_ledger(self):
        for case in ('unknown','token','native','head'):
            def ledger(n,v):
                if n==2:
                    if case=='unknown':v['tokenAccounts'][1]['heldAtomic']=None
                    if case=='token':v['tokenAccounts'][1]['heldAtomic']='95'
                    if case=='native':v['nativeHeldLamports']='90001'
                    if case=='head':v['ledgerHeadSha256']='c'*64
            r,o=self.observe(ledger_hook=ledger)
            self.assertEqual(r['state'],'unavailable',case)
            self.assertFalse(any(x['method']=='simulateTransaction' for x in o.calls))

    def test_exit_funded_but_two_caps_not_funded_is_only_partial_evidence(self):
        def ledger(n,v):v['nativeHeldLamports']='85000'
        r,_=self.observe(ledger_hook=ledger)
        self.assertEqual(r['state'],'controlled-reverse-cost-observation-consistent',r)
        self.assertEqual(r['feePlan']['currentNativeSpendableLamports'],'15000')
        self.assertEqual(r['feePlan']['shortfallForKnownFeeCapsLamports'],'5000')
        self.assertFalse(r['feePlan']['knownFeeCapSubtotalCovered'])
        self.assertFalse(r['feePlan']['roundTripFundingEstablished'])
        self.assertFalse(r['executionApproved'])

    def test_final_unknown_reverse_reservation_prevents_cost_acceptance(self):
        def ledger(n,v):
            if n==3:v['tokenAccounts'][1]['heldAtomic']=None
        r,_=self.observe(ledger_hook=ledger)
        self.assertEqual(r['state'],'unavailable')
        self.assertIsNone(r['feePlan'])
        self.assertFalse(r['simulationVerified'])

    def test_changed_pool_and_invalid_account_state_reject(self):
        for case in ('pool','native','blockhash'):
            def mutate(f,s,scope):
                if case=='pool':edit(s,4,64,(10001).to_bytes(8,'little'))
                if case=='native':s['evidence']['accounts']['result']['value'][8]['lamports']=9999
                if case=='blockhash':s['evidence']['blockhash']['result']['value']=False
            r,_=self.observe(mutate=mutate)
            self.assertEqual(r['state'],'unavailable',case)

    def test_simulation_failures_lateness_and_final_ledger_drift(self):
        for change in (lambda v:v['value'].update(err='private-error'),
                       lambda v:v['value'].pop('fee'),
                       lambda v:v['value']['preTokenBalances'][0]['uiTokenAmount'].update(amount='9999')):
            r,o=self.observe(change=change)
            self.assertEqual(r['state'],'unavailable');self.assertFalse(r['simulationVerified'])
            self.assertNotIn('private-error',json.dumps(r))
            self.assertEqual(sum(x['method']=='simulateTransaction' for x in o.calls),1)
        clock=Clock()
        def late(n,b):
            if n==19:clock.at+=10001
        r,_=self.observe(clock=clock,hook=late)
        self.assertEqual(r['state'],'unavailable')
        def drift(n,v):
            if n==3:v['ledgerHeadSha256']='c'*64
        r,_=self.observe(ledger_hook=drift)
        self.assertEqual(r['state'],'unavailable')

    def test_stop_and_invalid_mode(self):
        r,o=self.observe(stop=lambda _:True)
        self.assertEqual(r['state'],'unavailable');self.assertEqual(len(o.calls),10)
        with self.assertRaises(ValueError):
            fresh_quote.observe(Path('/unused'),'unused','unused',reverse_reference=True)

    def test_offline_cli_private_output_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'check.json.gz'
            args=[sys.executable,'-E','-s',str(Path(__file__).with_name('reverse_cost_cli.py')),'--output',str(out)]
            r=subprocess.run(args,capture_output=True,text=True,timeout=15)
            self.assertEqual(r.returncode,0,r.stderr)
            v=json.loads(gzip.decompress(out.read_bytes()))
            self.assertEqual(v['casesPassed'],10);self.assertEqual(v['networkRequests'],0)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            before=out.read_bytes()
            self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0)
            self.assertEqual(out.read_bytes(),before)


if __name__=='__main__':unittest.main()
