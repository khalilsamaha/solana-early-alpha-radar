import copy,sys,unittest
from pathlib import Path
from review import build
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from test_join_quotes import fixture

def sample(disposition='defer',version=False):
    _,q=fixture('baseline');s=q['signals'][0]
    s['features']={'disposition':disposition,'liquidityUsd':0,'historyReady':True}
    if version:s['features'].update(qualificationVersion='qualification-1',qualificationMode='shadow',qualificationAt=s['signalAt'])
    q['probes'][0]['signal']=copy.deepcopy(s)
    return q
def group(r):return next(iter(r['groups'].values()))
class ReviewTests(unittest.TestCase):
    def test_labels_are_not_recomputed_and_inputs_are_unchanged(self):
        for label in ['retain','defer',None]:
            q=sample(label);before=copy.deepcopy(q);r=build(q)
            self.assertEqual(group(r)['disposition'],label or 'unknown');self.assertEqual(q,before)
            self.assertEqual(group(r)['horizons']['30000']['validatedQuotedReturns'],1)
    def test_legacy_and_verified_versions_are_explicit(self):
        self.assertEqual(group(build(sample()))['qualificationVersion'],'version-unrecorded-or-invalid')
        self.assertEqual(group(build(sample(version=True)))['qualificationVersion'],'qualification-1')
        q=sample(version=True)
        for s in [q['signals'][0],q['probes'][0]['signal']]:s['features']['qualificationAt']+=1
        self.assertEqual(group(build(q))['qualificationVersion'],'version-unrecorded-or-invalid')
    def test_invalid_amount_or_stored_return_keeps_admitted_denominator(self):
        for field,value in [('inAmount','2'),('quotedUsdcChangePct',99),('executionVerified',True)]:
            q=sample();q['probes'][0]['observations'][2][field]=value;r=group(build(q))['horizons']['30000']
            self.assertEqual(r['admitted'],1);self.assertEqual(r['validatedQuotedReturns'],0);self.assertIsNone(r['meanPct'])
    def test_failed_exit_is_not_a_zero_and_unknown_liquidity_is_separate(self):
        q=sample();q['probes'][0]['observations'][2]['status']='http-error';r=build(q)
        self.assertEqual(group(r)['horizons']['30000']['states'],{'sell-quote-failed':1})
        self.assertNotIn('liquidity-unknown',r['cases'][0]['entryEvidenceFlags'])
    def test_nonadmitted_and_missing_probe_denominators(self):
        q=sample();q['probes']=[];r=group(build(q));self.assertEqual(r['admitted'],1)
        self.assertEqual(r['horizons']['30000']['withoutValidatedReturn'],1)
        q['signals'][0]['decision']='cohort-spacing';r=group(build(q));self.assertEqual(r['signals'],1);self.assertEqual(r['admitted'],0)
    def test_conflicting_features_duplicate_sequences_and_nonadmitted_probe_fail(self):
        q=sample();q['probes'][0]['signal']['features']['disposition']='retain'
        with self.assertRaises(ValueError):build(q)
        for name in ['signals','probes']:
            q=sample();q[name]*=2
            with self.assertRaises(ValueError):build(q)
        q=sample();q['signals'][0]['decision']='observer-busy'
        with self.assertRaises(ValueError):build(q)
    def test_first_reverse_has_actual_delay_and_never_claims_instantaneous_cost(self):
        r=build(sample());x=r['cases'][0]['exits']['0']
        self.assertEqual(x['actualResponseAfterBuyMs'],10300);self.assertIn('after spacing',x['label'])
        self.assertIsNone(group(r)['horizons']['0']['onTime'])
    def test_late_quote_not_in_on_time_subset(self):
        q=sample();o=q['probes'][0]['observations'][2];o['startedAt']+=6000;o['receivedAt']+=6000
        h=group(build(q))['horizons']['30000'];self.assertEqual(h['validatedQuotedReturns'],1);self.assertEqual(h['onTimeCount'],0)
    def test_recovery_from_probe_is_visible_and_never_backfills_other_signals(self):
        q=sample();q['signals']=[];r=build(q);self.assertEqual(r['recoveredSignalsFromProbes'],1);self.assertEqual(len(r['cases']),1)
    def test_legacy_missing_pricing_and_zero_new_pricing_remain_distinct(self):
        q=sample();r=build(q);self.assertIsNone(r['cases'][0]['buyPricing']['inUsdValue'])
        q['probes'][0]['observations'][0].update(pricingEvidenceVersion='quote-pricing-1',inUsdValue=0,outUsdValue=0)
        r=build(q);self.assertEqual(r['cases'][0]['buyPricing']['inUsdValue'],0);self.assertFalse(r['cases'][0]['buyPricing']['missingUsdValuation'])
if __name__=='__main__':unittest.main()
