import copy,unittest
import test_joined_analysis as fixtures
from joined_analysis import join_quotes
from path_analysis import path_analysis,VERSION
from fixed_exits import fixed_exits,PROTOCOL

class PathExitTests(unittest.TestCase):
    def fixture(self):
        d,q=fixtures.JoinedTests().fixture();q['capturedAt']=500000
        d['fixedExitRegistration']={**PROTOCOL,'registeredAt':90000}
        return d,q
    def points(self,d,rows):
        d['fast-shadow-outcomes'][0]['at']=140000
        d['fast-shadow-outcomes'][0]['pathEvidence']={'version':VERSION,'points':rows,'partialHistory':False}
    def point(self,at,price=2.1,pool='pool',recorded=None):
        return {'pairAddress':pool,'priceUsd':price,'sampleAt':at,'recordedAt':at if recorded is None else recorded}
    def test_alignment_uses_only_known_prior_response_and_preserves_original_comparison(self):
        d,q=self.fixture();self.points(d,[self.point(130000),self.point(132100,3)])
        j=join_quotes(d,q);before=copy.deepcopy(j);r=path_analysis(d,j)['alignmentCases'][0]
        self.assertEqual(r['state'],'prior-response-paired');self.assertEqual(r['priorObservation']['sampleAt'],130000)
        self.assertEqual(r['priorAgeAtQuoteRequestMs'],2000);self.assertAlmostEqual(r['priorPriceChangePct'],5);self.assertEqual(j,before)
    def test_future_recording_alternate_pool_and_stale_observations_not_paired(self):
        for point in [self.point(131000,recorded=133000),self.point(131000,pool='other'),self.point(110000)]:
            d,q=self.fixture();self.points(d,[point]);row=path_analysis(d,join_quotes(d,q))['alignmentCases'][0]
            self.assertEqual(row['state'],'no-recent-prior-original-pool-response')
    def test_legacy_missing_path_and_source_mismatch_stay_explicit(self):
        d,q=self.fixture();r=path_analysis(d,join_quotes(d,q));self.assertEqual(r['poolSummary']['states'],{'legacy-unavailable':1})
        self.assertEqual(r['alignmentCases'][0]['state'],'path-unavailable')
        q['sourceIdentity']='other';self.assertEqual(path_analysis(d,join_quotes(d,q))['alignmentCases'],[])
    def test_alternate_price_does_not_replace_missing_original_return(self):
        d,q=self.fixture();o=d['fast-shadow-outcomes'][0];o.update(status='missing');o.pop('returnPct');o.pop('priceUsd')
        alt=self.point(131000,pool='alternate');self.points(d,[alt]);o['pathEvidence']['alternateAtCheckpoint']=alt
        r=path_analysis(d,join_quotes(d,q));self.assertEqual(r['poolSummary']['missingOriginalWithAlternate'],1)
        self.assertFalse(r['poolCases'][0]['alternateCheckpoints'][0]['crossPoolReturnComputed']);self.assertNotIn('returnPct',o)
    def test_malformed_path_fails_without_partial_statistics(self):
        for points in [[self.point(130000)]*9,[self.point(130000,price=-1)],[self.point(130000,recorded=120000)],[self.point(130000),self.point(130000,price=3)]]:
            d,q=self.fixture();self.points(d,points)
            with self.assertRaises(ValueError):path_analysis(d,join_quotes(d,q))
    def test_prospective_registration_and_haircut_do_not_choose_best_exit(self):
        d,q=self.fixture();r=fixed_exits(d,q,join_quotes(d,q));self.assertTrue(r['registrationValid']);self.assertEqual(r['cases'][0]['period'],'forward')
        row=r['cases'][0]['outcomes'][0];self.assertEqual(row['state'],'on-time-quote');self.assertAlmostEqual(row['additionalProceedsHaircutPct']['100'],-10.9)
        self.assertEqual(r['protocol']['primaryOffsetMs'],30000);self.assertEqual(r['completeCaseComparisons'],{})
        d['fixedExitRegistration']['registeredAt']=110000;self.assertEqual(fixed_exits(d,q,join_quotes(d,q))['cases'][0]['period'],'exploratory')
    def test_changed_protocol_cannot_relabel_historical_results_forward(self):
        d,q=self.fixture();d['fixedExitRegistration']['primaryOffsetMs']=60000
        r=fixed_exits(d,q,join_quotes(d,q));self.assertFalse(r['registrationValid']);self.assertEqual(r['cases'][0]['period'],'exploratory')
    def test_pending_failed_late_and_missing_remain_separate(self):
        d,q=self.fixture();q['capturedAt']=132500
        r=fixed_exits(d,q,join_quotes(d,q));self.assertEqual(r['cases'][0]['outcomes'][1]['state'],'pending')
        q['capturedAt']=500000;q['probes'][0]['observations'][1]['status']='http-error'
        r=fixed_exits(d,q,join_quotes(d,q));self.assertEqual(r['cases'][0]['outcomes'][0]['state'],'failed-or-invalid-exit');self.assertEqual(r['cases'][0]['outcomes'][1]['state'],'missing-exit')
        d,q=self.fixture();q['probes'][0]['observations'][1].update(startedAt=138000,receivedAt=138300)
        r=fixed_exits(d,q,join_quotes(d,q));self.assertEqual(r['cases'][0]['outcomes'][0]['state'],'late-quote')
        self.assertEqual(next(iter(r['groups'].values()))['quotedChangePct']['count'],0)
    def test_buy_failure_and_identity_mismatch_never_enter_forward_success(self):
        d,q=self.fixture();q['probes'][0]['observations'][0]['status']='http-error'
        r=fixed_exits(d,q,join_quotes(d,q));self.assertEqual(r['cases'][0]['outcomes'][0]['state'],'buy-unavailable')
        d,q=self.fixture();q['sourceIdentity']='other';self.assertEqual(fixed_exits(d,q,join_quotes(d,q))['cases'][0]['period'],'unverified-source')

if __name__=='__main__':unittest.main()
