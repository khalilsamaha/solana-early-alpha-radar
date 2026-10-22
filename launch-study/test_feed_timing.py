import unittest
from feed_timing import project, state, summarize
from capture import project_entry, project_outcome
class FeedTimingTests(unittest.TestCase):
 def feed(self):return {'version':'feed-provenance-1','provider':'dexscreener','httpStatus':200,'endpoint':'tokens-batch','pairAddress':'pool','priceUsd':1,'queuedAt':10,'requestStartedAt':20,'headersAt':30,'bodyAt':40,'appliedAt':50,'clocksOrdered':True,'queueMs':10,'headersMs':10,'bodyMs':10,'applyDelayMs':10,'repeatedPriceCount':0}
 def test_projection_drops_secrets_and_rejects_arbitrary_nested_values(self):
  f=self.feed();f.update(headers={'authorization':'secret'},cfCacheStatus={'secret':1},httpAgeSeconds=True,providerPriceAt=42)
  e=project_entry({'id':'x','feedEvidence':f});self.assertNotIn('secret',str(e));self.assertIsNone(e['feedEvidence']['httpAgeSeconds']);self.assertIsNone(e['feedEvidence']['providerPriceAt']);self.assertEqual(project_outcome({'feedEvidence':f})['feedEvidence'],e['feedEvidence'])
 def test_old_evidence_remains_absent_not_zero_latency(self):
  self.assertNotIn('feedEvidence',project_entry({'id':'x'}));s=summarize({'entries':[{'data':{'id':'x'}}]});self.assertEqual(s['groups'][0]['states'],{'not-recorded':1});self.assertIsNone(s['groups'][0]['distributions']['queueMs']['median'])
 def test_binding_and_clocks_are_checked_before_summary(self):
  row={'pairAddress':'pool','priceUsd':1,'at':60,'sampleAt':45};f=project(self.feed());self.assertEqual(state(f,row,'outcomes'),'recorded-local-timing')
  row['sampleAt']=35;self.assertEqual(state(f,row,'outcomes'),'clock-after-event');row['priceUsd']=2;self.assertEqual(state(f,row,'entries'),'binding-mismatch');row['priceUsd']=1;f['bodyAt']=5;self.assertEqual(state(f,row,'entries'),'invalid-clock-order')
 def test_summary_uses_only_valid_timings(self):
  row={'at':60,'priceUsd':1,'pairAddress':'pool','feedEvidence':self.feed()};s=summarize({'entries':[{'data':row},{'data':{'at':10}}]})['groups'][0];self.assertEqual(s['states'],{'recorded-local-timing':1,'not-recorded':1});self.assertEqual(s['distributions']['applyDelayMs']['max'],10);self.assertEqual(s['recordsWithRepeatedPrice'],0)
if __name__=='__main__':unittest.main()
