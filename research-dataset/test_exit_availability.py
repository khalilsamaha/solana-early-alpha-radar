import copy,unittest
from build import build
from test_dataset import fixture
class ExitAvailabilityTests(unittest.TestCase):
 def review(self,q):return build([q])
 def test_quotes_failures_and_transport_remain_exclusive_with_full_denominator(self):
  for status,code,category,expected in [('http-error',400,'quote-generation-failure-reported','provider-reported-quote-failure'),('http-error',503,None,'transport-or-service-failure'),('timeout',None,None,'transport-or-service-failure'),('http-error',400,'unknown','other-quote-failure')]:
   q=fixture();q['probes'][0]['observations'][2].update(status=status,httpStatus=code,providerCategory=category)
   r=self.review(q);group=r['exitAvailabilityReview']['groups'][0]['horizons']['30000']
   self.assertEqual(group['admitted'],1);self.assertEqual(group['states'],{expected:1});self.assertIsNone(group['meanOnTimeQuotedChangePct'])
   self.assertIsNone(r['rows'][0]['targets']['30000']['returnPct'])
 def test_late_valid_quote_is_not_a_timely_success_and_target_is_preserved(self):
  q=fixture();o=q['probes'][0]['observations'][2];o['startedAt']+=6000;o['receivedAt']+=6000
  r=self.review(q);self.assertEqual(r['rows'][0]['exitAvailability']['30000'],'late-validated-quote')
  self.assertEqual(r['rows'][0]['targets']['30000']['returnPct'],10)
  self.assertEqual(r['exitAvailabilityReview']['groups'][0]['horizons']['30000']['onTimeReturned'],0)
 def test_skipped_and_missing_do_not_get_provider_failure_labels(self):
  q=fixture();q['probes']=[];q['signals'][0]['decision']='observer-busy';r=self.review(q)
  self.assertEqual(r['rows'][0]['exitAvailability']['30000'],'not-admitted')
  self.assertEqual(r['exitAvailabilityReview']['groups'][0]['admitted'],0)
  q=fixture();q['probes'][0]['observations'].pop(2);r=self.review(q)
  self.assertEqual(r['rows'][0]['exitAvailability']['30000'],'missing-observation')
 def test_new_review_does_not_change_source_predictors_or_return_summaries(self):
  q=fixture();before=copy.deepcopy(q);r=self.review(q)
  self.assertEqual(q,before);g=r['exitAvailabilityReview']['groups'][0]['horizons']['30000']
  self.assertEqual(g['onTimeReturned'],1);self.assertEqual(g['onTimePositive'],1);self.assertEqual(g['meanOnTimeQuotedChangePct'],10)
  self.assertEqual(r['exitAvailabilityReview']['groups'][0]['metadataCoverage']['organicScore']['states'],{'not-recorded':1})
  self.assertNotIn('exitAvailability',r['rows'][0]['predictors']);self.assertFalse(r['exitAvailabilityReview']['changesAdmissions'])
