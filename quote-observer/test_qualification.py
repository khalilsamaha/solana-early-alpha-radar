import unittest,copy
from qualification_analysis import classify,compare,REGISTERED_HASH

class QualificationTests(unittest.TestCase):
    def fixture(self):
        s={'seq':1,'entryId':'e','mint':'m','signalAt':1000,'originalPool':'p','cohort':'early-activity','decision':'admitted',
           'samplingPolicy':'cohort-budgets-v2','features':{'historyReady':False,'liquidityUsd':None,'disposition':'defer'}}
        e={'id':'e','mint':'m','at':1000,'pairAddress':'p','cohort':'early-activity','qualification':{'historyReady':False,'disposition':'defer'},'entryFeatures':{'liquidityUsd':None}}
        q={'signals':[s],'probes':[{'signal':copy.deepcopy(s),'state':'complete-with-failures','observations':[{'leg':'buy','status':'quoted'},{'leg':'sell','targetOffsetMs':120000,'status':'http-error','httpStatus':400}]}]}
        r={'entries':[e],'evaluation':{'results':[]},'shadowRegistration':{'rulesSha256':REGISTERED_HASH,'registeredAtMs':500}}
        return q,r
    def test_unknown_liquidity_is_not_zero_and_false_dominates_combined_rule(self):
        self.assertEqual(classify({'liquidityUsd':None},'known-liquidity-5000-v1'),'unknown')
        self.assertEqual(classify({'liquidityUsd':0},'known-liquidity-5000-v1'),'excluded')
        self.assertEqual(classify({'liquidityUsd':None,'disposition':'defer'},'qualified-liquidity-5000-v1'),'excluded')
        self.assertEqual(classify({'liquidityUsd':6000,'disposition':None},'qualified-liquidity-5000-v1'),'unknown')
    def test_failed_sell_and_skipped_entry_are_preserved_in_separate_denominators(self):
        q,r=self.fixture();s=copy.deepcopy(q['signals'][0]);s.update(seq=2,entryId='other',decision='cohort-spacing');q['signals'].append(s)
        before=copy.deepcopy((q,r));out=compare(q,r)
        g=out['groups']['cohort-budgets-v2/prospective/early-activity/history-ready-v1/excluded']
        self.assertEqual(g['eligibleSignals'],2);self.assertEqual(g['admitted'],1);self.assertEqual(g['quoteOutcomes']['120000']['observed'],0)
        self.assertEqual(g['quoteOutcomes']['120000']['notObserved'],1);self.assertEqual((q,r),before)
        self.assertEqual(out['admittedCases'][0]['entryClassification'],'deferred-research')
    def test_policy_and_registration_boundaries_are_separate(self):
        q,r=self.fixture();r['shadowRegistration']['registeredAtMs']=1001
        self.assertIn('/exploratory/',next(iter(compare(q,r)['groups'])))
        r['shadowRegistration']['rulesSha256']='other'
        self.assertFalse(compare(q,r)['registrationVerified'])
    def test_later_research_features_do_not_replace_signal_features(self):
        q,r=self.fixture();r['entries'][0]['entryFeatures']['liquidityUsd']=90000
        out=compare(q,r);self.assertIn('liquidityUsd',out['admittedCases'][0]['featureDisagreements'])
        self.assertEqual(out['admittedCases'][0]['ruleBuckets']['known-liquidity-5000-v1'],'unknown')
    def test_matching_requires_full_identity_and_duplicate_signals_rejected(self):
        q,r=self.fixture();r['entries'][0]['mint']='different'
        with self.assertRaises(ValueError):compare(q,r)
        q,r=self.fixture();q['signals']*=2
        with self.assertRaises(ValueError):compare(q,r)
    def test_rules_apply_to_winners_and_losers_and_do_not_claim_execution(self):
        q,r=self.fixture();p=q['probes'][0]
        for value in (1900,-99):
            p['observations'][-1]={'leg':'sell','status':'quoted','targetOffsetMs':120000,'quotedUsdcChangePct':value}
            out=compare(q,r);case=out['admittedCases'][0]
            self.assertEqual(case['ruleBuckets']['history-ready-v1'],'excluded');self.assertFalse(case['classificationIsTradeApproval'])
            group=out['groups']['cohort-budgets-v2/prospective/early-activity/history-ready-v1/excluded']
            self.assertEqual(group['quoteOutcomes']['120000']['meanPct'],value)
if __name__=='__main__':unittest.main()
