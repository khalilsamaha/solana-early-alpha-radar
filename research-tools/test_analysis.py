import copy
import unittest
import test_research as tr
entry,T=tr.entry,tr.T
import paper_model as m
import research_analysis as a

class AnalysisTests(unittest.TestCase):
    def report(self,e,age=600):
        es=e if isinstance(e,list) else [e]
        return {'entries':es,'cutoffMs':T+age*1000,'evaluation':m.evaluate(es,T+age*1000)}
    def test_missing_liquidity_is_unknown_not_zero(self):
        e=entry([(0,100)])
        self.assertEqual(a.rule_state(e,'known-liquidity-5000-v1'),'unknown')
        e['entryFeatures']={'liquidityUsd':0}
        self.assertEqual(a.rule_state(e,'known-liquidity-5000-v1'),'excluded')
    def test_no_future_features_used_in_rule(self):
        e=entry([(0,100),(30,110)]);e['path'][-1]['liquidityUsd']=100000
        self.assertEqual(a.rule_state(e,'known-liquidity-5000-v1'),'unknown')
    def test_rule_boolean_logic_with_unknown(self):
        e=entry([(0,100)],qualification={'disposition':'defer'})
        self.assertEqual(a.rule_state(e,'qualified-liquidity-5000-v1'),'excluded')
        e['qualification']['disposition']='retain'
        self.assertEqual(a.rule_state(e,'qualified-liquidity-5000-v1'),'unknown')
    def test_checkpoint_wait_does_not_change_model(self):
        e=entry([(0,100),(30,110)])
        r=self.report(e,age=240);before=copy.deepcopy(r['evaluation']);out=a.analyze(r)
        self.assertEqual(before,r['evaluation'])
        self.assertIn('awaiting-checkpoint-evidence',[v['evidenceState'] for v in out['scenarioEvidence']])
        self.assertTrue(all(v['modelStatus']=='unresolved' for v in out['scenarioEvidence']))
    def test_mature_gap_not_hidden_as_waiting(self):
        r=self.report(entry([(0,100),(30,110)]));out=a.analyze(r)
        self.assertNotIn('awaiting-checkpoint-evidence',[v['evidenceState'] for v in out['scenarioEvidence']])
    def test_recorded_five_minute_prevents_wait_label(self):
        e=entry([(0,100),(30,110)],checkpoints=[{'horizon':'5m','status':'missing'}])
        out=a.analyze(self.report(e,age=320))
        self.assertNotIn('awaiting-checkpoint-evidence',[v['evidenceState'] for v in out['scenarioEvidence']])
    def test_alternate_pool_explained_not_spliced(self):
        e=entry([(0,100),(30,110),(60,120)])
        e['path'].append({'at':T+75000,'price':9999,'pairAddress':'OTHER'})
        r=self.report(e);out=a.analyze(r)
        self.assertIn('unresolved-with-alternate-pool',[x['evidenceState'] for x in out['scenarioEvidence']])
        self.assertFalse(out['poolEvidence'][e['id']]['migrationVerified'])
        self.assertTrue(all(x['status']=='unresolved' for x in r['evaluation']['results'] if x['delayMs']==10000))
    def test_pool_future_observation_excluded(self):
        e=entry([(0,100)]);e['path'].append({'at':T+999999,'price':10,'pairAddress':'FUTURE'})
        self.assertEqual(a.pool_evidence(e,T+1000)['alternatePools'],[])
    def test_no_registration_means_no_prospective_results(self):
        out=a.analyze(self.report(entry([(0,100),(30,100),(60,100),(90,100)])))
        self.assertTrue(all(x['entries']==0 for k,x in out['shadowGroups'].items() if k.startswith('prospective/')))
    def test_registration_splits_by_entry_time(self):
        e1=entry([(0,100)],qualification={'historyReady':True});e2=copy.deepcopy(e1);e2['id']='NEW';e2['at']=T+1
        reg={'rulesSha256':a.RULES_HASH,'registeredAtMs':T+1}
        out=a.analyze(self.report([e1,e2]),reg)
        k='baseline/history-ready-v1/selected/time-60/delay10000/cost100'
        self.assertEqual(out['shadowGroups']['exploratory/'+k]['entries'],1)
        self.assertEqual(out['shadowGroups']['prospective/'+k]['entries'],1)
    def test_shadow_excluded_winner_retained_and_cost_applied(self):
        e=entry([(0,100),(15,100),(30,105),(60,110),(90,120),(150,130)],entryFeatures={'liquidityUsd':1000})
        out=a.analyze(self.report(e))
        k='exploratory/baseline/known-liquidity-5000-v1/'
        rejected=out['shadowGroups'][k+'excluded/time-60/delay10000/cost100']
        self.assertEqual(rejected['aboveEntry'],1)
        self.assertAlmostEqual(rejected['meanNetPct'],(1.2*.99/1.01-1)*100)
        self.assertEqual(out['shadowGroups'][k+'selected/time-60/delay10000/cost100']['entries'],0)

    def test_wrong_registration_refused(self):
        with self.assertRaises(ValueError):a.analyze(self.report(entry([(0,100)])),{'rulesSha256':'bad','registeredAtMs':T})
    def test_features_allowlist_and_freshness(self):
        f=a.features({'at':T,'candidate':{'liquidityUsd':0,'secret':'CANARY'},'evidence':{'inputs':{'marketObservedAt':T+1,'securityCheckedAt':T-1000}}})
        self.assertNotIn('CANARY',str(f));self.assertEqual(f['liquidityUsd'],0)
        self.assertIsNone(f['marketObservedAt']);self.assertEqual(f['securityCheckedAt'],T-1000)
    def test_collapse_case_records_real_observed_trigger(self):
        e=entry([(0,100),(15,100),(30,1),(45,1),(60,1),(90,1),(150,1)])
        out=a.analyze(self.report(e))
        r=next(x for x in out['severeLossCases'] if x['policy']=='target20-stop15-time120')
        self.assertEqual(r['triggerReturnPct'],-99)
        self.assertEqual(r['largestObservedStepDown']['returnPct'],-99)
        self.assertLess(r['netReturnPct'],-99)

# One targeted DB check; do not inherit and repeat the entire collector suite.
class EnrichmentTests(unittest.TestCase):
    def test_entry_features_and_path_liquidity_preserved(self):
        fixture=tr.CaptureTests();fixture.setUp()
        try:
            row={'id':f'FEATURE:{T}:1','at':T,'engineVersion':'0.2.9',
                 'candidate':{'mint':'FEATURE','pairAddress':'PF','priceUsd':100,'liquidityUsd':6000},
                 'qualification':{'historyReady':True,'metrics':{'return60sPct':12}}}
            fixture.add('alerts',row)
            fixture.add('snapshots',{'at':T+30000,'mint':'FEATURE','priceUsd':90,'pairAddress':'PF','liquidityUsd':5000})
            fixture.add('research-outcomes',{'at':T+60000,'entryAt':T,'mint':'FEATURE','cohort':'baseline','horizon':'1m',
                'status':'missing','reasonCode':'different-pool','evidenceHistory':{'poolAddress':'PF','maxSamples':24,
                    'samples':[{'at':T+30000,'price':90,'liquidity':5000}]}})
            fixture.db.commit();r=fixture.capture();e=next(e for e in r['entries'] if e['mint']=='FEATURE')
            self.assertEqual(e['entryFeatures']['liquidityUsd'],6000)
            self.assertEqual(e['path'][1]['liquidityUsd'],5000)
            self.assertEqual(e['checkpoints'][0]['reasonCode'],'different-pool')
            self.assertEqual(e['checkpoints'][0]['historyMaxSamples'],24)
        finally:fixture.tearDown()

if __name__=='__main__':unittest.main()
