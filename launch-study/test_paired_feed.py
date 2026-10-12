import copy, unittest
from joined_report import build
from paired_feed import evidence
from test_join_quotes import fixture
from test_study import T, P

def transport(price,body,applied=None,cache='MISS',age=None):
 return {'version':'feed-provenance-1','provider':'dexscreener','endpoint':'tokens-batch','pairAddress':P,'priceUsd':price,
  'queuedAt':body-200,'requestStartedAt':body-190,'headersAt':body-2,'bodyAt':body,'appliedAt':body if applied is None else applied,
  'clocksOrdered':True,'httpStatus':200,'queueMs':10,'headersMs':188,'bodyMs':2,'applyDelayMs':0 if applied is None else applied-body,
  'cfCacheStatus':cache,'httpAgeSeconds':age,'priceUnchangedSince':body,'repeatedPriceCount':0}

def setup(cohort='fast30-shadow'):
 c,q=fixture(cohort);e=c['entries'][0]['data'];o=c['outcomes'][0]['data']
 e['priceEvidence']={'version':'entry-price-projection-1','basis':'provider-response-time','poolAddress':P,
  'samples':[{'at':T-100,'price':2}],'sourceSampleCount':1,'truncated':False}
 e['feedEvidence']=transport(2,T-100,T)
 o['feedEvidence']=transport(o['priceUsd'],o['sampleAt'],o['at'])
 return c,q

def run(c,q):return build({'format':'launch-study-report-1','capture':c},q)['pairedFeedAudit']

class PairedFeedTests(unittest.TestCase):
 def test_three_cohorts_match_their_entry_id_and_checkpoint_without_changing_returns(self):
  for cohort in ('baseline','early-activity','fast30-shadow'):
   c,q=setup(cohort);before=copy.deepcopy((c,q));a=run(c,q);h=a['horizons']['30000'];row=a['cases'][0]
   self.assertEqual(h['records'],1);self.assertEqual(h['largeCloseOriginalPoolOnTimeWithBothTimings'],1)
   self.assertEqual(h['largeWithBothLocalPipelinesWithin1s'],1);self.assertEqual(row['paperReturnPct'],50);self.assertEqual(row['quotedChangePct'],10)
   self.assertEqual(row['routeScope'],'original-only-token-pools');self.assertEqual((c,q),before)
 def test_unknown_old_transport_is_not_zero_or_cache_miss(self):
  c,q=fixture();a=run(c,q);r=a['cases'][0];self.assertEqual(r['entryTiming']['state'],'not-recorded');self.assertIsNone(r['bothLocalPipelinesWithin1s']);self.assertEqual(a['horizons']['30000']['largeWithBothCacheMiss'],0)
 def test_cache_age_and_hit_without_age_are_separate(self):
  c,q=setup();f=c['outcomes'][0]['data']['feedEvidence'];f.update(cfCacheStatus='HIT',httpAgeSeconds=16)
  a=run(c,q);self.assertEqual(a['horizons']['30000']['largeWithPositiveHttpAge'],1)
  f['httpAgeSeconds']=None;a=run(c,q);self.assertEqual(a['cases'][0]['checkpointTiming']['cacheEvidence'],'cache-hit-without-positive-age');self.assertEqual(a['horizons']['30000']['largeWithPositiveHttpAge'],0)
 def test_original_pool_presence_is_not_exclusivity(self):
  c,q=setup();q['probes'][0]['observations'][2]['routePlan'].append({'pool':'other','inputMint':q['signals'][0]['mint'],'outputMint':'another'})
  a=run(c,q);self.assertEqual(a['cases'][0]['routeScope'],'original-plus-other-token-pools');self.assertEqual(a['horizons']['30000']['largeCloseOriginalPoolOnTimeWithBothTimings'],1)
 def test_truncated_route_does_not_pass_original_pool_gate(self):
  c,q=setup();q['probes'][0]['observations'][0]['routePlanTruncated']=True
  a=run(c,q);self.assertEqual(a['cases'][0]['routeScope'],'unavailable');self.assertEqual(a['horizons']['30000']['closeOriginalPoolOnTime'],0)
 def test_unadmitted_cases_do_not_enter_admitted_audit_or_create_fake_returns(self):
  c,q=setup();q['signals'][0]['decision']='observer-busy';q['probes']=[];a=run(c,q)
  self.assertEqual(a['cases'],[]);self.assertEqual(a['admittedWatches'],0)
 def test_sell_failure_and_invalid_buy_keep_denominators_without_return_imputation(self):
  for index in (0,2):
   c,q=setup();q['probes'][0]['observations'][index]['status']='http-error';a=run(c,q)
   self.assertEqual(a['horizons']['30000']['records'],1);self.assertEqual(a['horizons']['30000']['paired'],0);self.assertIsNone(a['cases'][0]['quotedChangePct'])
 def test_future_outcome_provenance_is_not_used_after_cutoff(self):
  c,q=setup();q['capturedAt']=T+10000;a=run(c,q)
  self.assertEqual(a['cases'][0]['checkpointTiming']['state'],'paper-pending');self.assertIsNone(a['cases'][0]['checkpointTiming']['record'])
 def test_gapped_paper_does_not_enter_comparison(self):
  c,q=setup();c['outcomes'][0]['data']['coverage']='gapped';a=run(c,q)
  self.assertEqual(a['cases'][0]['checkpointTiming']['state'],'paper-gapped');self.assertEqual(a['horizons']['30000']['paired'],0)
 def test_wrong_price_or_pool_provenance_is_unusable(self):
  for key,value in [('priceUsd',999),('pairAddress','different')]:
   c,q=setup();c['entries'][0]['data']['feedEvidence'][key]=value;a=run(c,q)
   self.assertEqual(a['cases'][0]['entryTiming']['state'],'binding-mismatch');self.assertEqual(a['horizons']['30000']['closeOriginalPoolOnTimeWithBothTimings'],0)
 def test_receipt_must_fall_between_body_and_apply_not_merely_before_signal(self):
  c,q=setup();c['entries'][0]['data']['priceEvidence']['samples'][0]['at']=T-300;a=run(c,q)
  self.assertEqual(a['cases'][0]['entryTiming']['state'],'comparison-clock-mismatch')
 def test_slow_local_pipeline_remains_measured_and_is_not_cache_evidence(self):
  c,q=setup();f=c['entries'][0]['data']['feedEvidence'];f['queuedAt']-=2000;f['queueMs']+=2000;a=run(c,q)
  self.assertGreater(a['cases'][0]['entryTiming']['localPipelineMs'],1000);self.assertEqual(a['horizons']['30000']['largeWithBothLocalPipelinesWithin1s'],0)
 def test_missing_repetition_start_is_unknown_not_zero(self):
  c,q=setup();c['entries'][0]['data']['feedEvidence'].pop('priceUnchangedSince');a=run(c,q)
  self.assertIsNone(a['cases'][0]['entryTiming']['reportedPriceUnchangedMs'])
if __name__=='__main__':unittest.main()
