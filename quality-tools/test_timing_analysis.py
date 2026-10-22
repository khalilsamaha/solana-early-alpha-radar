import copy
import unittest
from timing_analysis import analyze_timing


class TimingTests(unittest.TestCase):
    def fixture(self):
        e = {'id': 'a', 'at': 100000, 'pairAddress': 'pool', 'priceUsd': 1}
        outcomes = [{'entryId': 'a', 'horizon': h, 'status': 'observed', 'coverage': 'sampled',
                     'pairAddress': 'pool', 'sampleAt': e['at']+ms+2000, 'priceUsd': 1.2, 'returnPct': 20}
                    for h, ms in [('30s', 30000), ('60s', 60000), ('120s', 120000), ('300s', 300000)]]
        link = {'entryId': 'a', 'cohort': 'early-activity', 'at': 115000, 'leadMs': 15000,
                'pairAddress': 'pool', 'comparisonPriceUsd': 1.1, 'comparisonObservedAt': 114999}
        return {'fast-shadow-entries': [e], 'fast-shadow-outcomes': outcomes, 'fast-shadow-links': [link], 'cutoffAt': 500000}

    def test_same_endpoint_comparison_and_observed_clock(self):
        d = self.fixture(); before = copy.deepcopy(d); result = analyze_timing(d)
        self.assertEqual(d, before)
        self.assertEqual(result['lead']['early-activity']['earlier'], 1)
        row = result['matchedEndpoints'][0]
        self.assertAlmostEqual(row['fastGrossReturnPct'], 20)
        self.assertAlmostEqual(row['comparisonGrossReturnPct'], (1.2/1.1-1)*100)
        self.assertEqual(result['all']['horizons']['30s']['sampleDelayAfterTargetMs']['median'], 2000)

    def test_simultaneous_link_is_not_early_and_legacy_price_is_unavailable(self):
        d = self.fixture(); link = d['fast-shadow-links'][0]; link.update(at=100000, leadMs=0)
        link.pop('comparisonPriceUsd'); r = analyze_timing(d)
        self.assertEqual(r['lead']['early-activity']['simultaneous'], 1)
        self.assertEqual(r['lead']['early-activity']['earlier'], 0)
        self.assertTrue(all(x['state']=='unavailable' for x in r['matchedEndpoints']))

    def test_gaps_invalid_prices_and_future_comparison_never_create_returns(self):
        for patch in [{'coverage':'gapped'}, {'sampleAt': 1}, {'returnPct': 99}, {'pairAddress':'other'}]:
            d=self.fixture();d['fast-shadow-outcomes'][0].update(patch)
            self.assertEqual(analyze_timing(d)['matchedEndpoints'][0]['state'],'unavailable')
        d=self.fixture();d['fast-shadow-links'][0]['comparisonObservedAt']=200000
        self.assertEqual(analyze_timing(d)['matchedEndpoints'][0]['state'],'unavailable')

    def test_mature_missing_retained_and_policies_not_combined(self):
        d=self.fixture();e={'id':'b','at':100000,'priceUsd':1,'pairAddress':'pool','followup':{'policy':'fast-followup-1','admitted':False}}
        d['fast-shadow-entries'].append(e);r=analyze_timing(d)
        self.assertEqual(r['all']['horizons']['300s']['states'],{'observed':1,'overdue':1})
        self.assertEqual(r['commonCompleteCohort']['entries'],1)
        self.assertEqual(len(r['byFollowupPolicy']),2)

    def test_duplicate_links_and_entries_fail_explicitly(self):
        for key in ['fast-shadow-links','fast-shadow-entries','fast-shadow-outcomes']:
            d=self.fixture();d[key].append(copy.deepcopy(d[key][0]))
            with self.assertRaises(ValueError):analyze_timing(d)


if __name__ == '__main__':
    unittest.main()
