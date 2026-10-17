import copy
import unittest
from readiness_details import review, returns, distribution, timing
from audit import PROTOCOL, digest, build
from test_audit import sample


class DetailsTests(unittest.TestCase):
    def test_existing_readiness_protocol_and_features_unchanged(self):
        before = digest(PROTOCOL)
        result = review([sample()], None)
        self.assertEqual(result['readiness']['protocolSha256'], before)
        self.assertFalse(result['modelTrained'])
        c = result['cohorts'][0]
        self.assertEqual(c['guardDeficits']['positiveReturnedQuote']['labelledWatches'], 99)
        self.assertEqual(c['guardDeficits']['exitQuoteAvailable']['examplesByClass'], {'0': 20, '1': 19})
        self.assertEqual(c['features']['liquidityUsd']['median'], 0)
        self.assertIsNone(c['features']['organicScore']['median'])
        self.assertEqual(digest(PROTOCOL), before)

    def test_duplicates_do_not_inflate_admissions_or_returns(self):
        q = sample()
        r = review([q, copy.deepcopy(q)], None)
        self.assertEqual(r['cohorts'][0]['compatibleAdmitted'], 1)
        self.assertEqual(r['merge']['duplicateProbesRemoved'], 1)

    def test_missing_failed_and_late_returns_never_become_zero(self):
        r = build([sample()])['rows'][0]
        rows = [copy.deepcopy(r) for _ in range(4)]
        rows[0]['targets']['30000']['returnPct'] = -60
        rows[1]['exitAvailability']['30000'] = 'provider-reported-quote-failure'
        rows[2]['exitAvailability']['30000'] = 'late-validated-quote'
        rows[3]['exitAvailability']['30000'] = 'missing-observation'
        x = returns(rows, 30000)
        self.assertEqual(x['admitted'], 4)
        self.assertEqual(x['quotedChangePct']['recorded'], 1)
        self.assertEqual(x['quotedChangePct']['mean'], -60)
        self.assertEqual(x['quotedChangePct']['lossAtLeast50Pct'], 1)
        self.assertIsNone(x['quotedChangePct']['meanWithoutSingleBest'])

    def test_timing_uses_actual_first_reverse_not_zero_label(self):
        q = sample(); p = q['probes'][0]
        t = timing(p, p['signal']['signalAt'])
        self.assertEqual(t['buyResponseToFirstReverseRequestMs'], 10000)
        self.assertEqual(t['exit30000SchedulingLatenessMs'], 0)
        self.assertTrue(all(v is None for v in timing(None, 100).values()))

    def test_provider_failure_recovery_is_visible(self):
        q = sample()
        q['probes'][0]['observations'][2] = {'leg': 'sell', 'targetOffsetMs': 30000,
            'status': 'http-error', 'httpStatus': 400, 'providerCategory': 'quote-generation-failure-reported',
            'startedAt': 1800000031000, 'receivedAt': 1800000031300}
        q['probes'][0]['state'] = 'complete-with-failures'
        result = review([q], None)['cohorts'][0]
        self.assertEqual(sum(result['exitStateTransitions30To120s'].values()), 1)
        self.assertEqual(result['horizons']['30000']['quotedChangePct']['recorded'], 0)
        self.assertEqual(result['horizons']['120000']['quotedChangePct']['recorded'], 1)

    def test_empty_distribution_has_no_invented_performance(self):
        d = distribution([None, float('nan'), True], 3)
        self.assertEqual(d['recorded'], 0)
        self.assertEqual(d['unavailable'], 3)
        self.assertIsNone(d['median'])


if __name__ == '__main__':
    unittest.main()
