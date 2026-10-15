import copy
import sys
import unittest
from unittest.mock import patch

import numpy as np
import benchmark as b


BOUNDARY = 1791880363912


def row(i, test=False, cohort='baseline'):
    at = BOUNDARY + (i + 1) * 600000 if test else BOUNDARY - (i + 1) * 600000
    value = 10.0 if i % 3 == 0 else -5.0
    return {'id': str(i) + str(test) + cohort, 'seq': i + 1, 'mint': str(i) + str(test) + cohort,
        'signalAt': at, 'utcDay': '2026-10-14' if test else '2026-10-12', 'cohort': cohort,
        'samplingPolicy': b.POLICY, 'featureCaptureVersion': b.SCHEMAS[cohort],
        'entrySchemaVerified': True, 'qualificationVersion': 'qualification-1',
        'disposition': 'retain' if i % 2 else 'defer', 'decision': 'admitted',
        'predictors': {'liquidityUsd': None if i % 7 == 0 else 5000 + i * 100,
                       'organicScore': i % 10, 'top10Pct': i % 30, 'return30sPct': i % 5,
                       'return60sPct': i % 7, 'lastIntervalReturnPct': i % 4,
                       'averageReportedTradeUsd': 5 + i % 6},
        'targets': {'30000': {'state': 'validated-sell-quote', 'returnPct': value,
            'positiveQuotedReturn': int(value > 0), 'sellQuoteReturned': 1, 'availableAt': at + 40000, 'onTime': True}}}


def sample():
    return [row(i) for i in range(80)] + [row(i, True) for i in range(30)]


class BenchmarkTests(unittest.TestCase):
    def test_test_labels_cannot_change_fit_or_predictions(self):
        rows = sample(); before = copy.deepcopy(rows)
        a = b.fit_cohort(rows, 'baseline', BOUNDARY)
        self.assertEqual(rows, before)
        for r in rows:
            if r['signalAt'] > BOUNDARY:
                r['targets']['30000']['returnPct'] *= -1
        c = b.fit_cohort(rows, 'baseline', BOUNDARY)
        self.assertEqual(a['fitAudit'], c['fitAudit'])
        self.assertEqual([p['probability'] for p in a['predictions']], [p['probability'] for p in c['predictions']])
        self.assertNotEqual(a['logistic']['brier'], c['logistic']['brier'])

    def test_test_extremes_never_change_imputation_scaling_or_weights(self):
        rows = sample(); a = b.fit_cohort(rows, 'baseline', BOUNDARY)
        for r in rows:
            if r['signalAt'] > BOUNDARY:
                r['predictors']['liquidityUsd'] = 1e15
        c = b.fit_cohort(rows, 'baseline', BOUNDARY)
        self.assertEqual(a['fitAudit'], c['fitAudit'])

    def test_cross_cohort_mint_purge_and_label_time_guard(self):
        rows = [row(1), row(2), row(3, True, 'early-activity')]
        rows[0]['mint'] = rows[2]['mint']
        rows[1]['targets']['30000']['availableAt'] = BOUNDARY + 1
        train, _, excluded = b.partition(rows, 'baseline', BOUNDARY)
        self.assertFalse(train)
        self.assertEqual(excluded['mint-present-in-test'], 1)
        self.assertEqual(excluded['training-target-not-available-before-boundary'], 1)

    def test_embargo_both_sides_and_incompatible_policy_schema(self):
        rows = [row(i) for i in range(4)]
        rows[0]['signalAt'] = BOUNDARY - 1
        rows[1]['signalAt'] = BOUNDARY + 1
        rows[2]['samplingPolicy'] = 'cohort-budgets-v2'
        rows[3]['entrySchemaVerified'] = False
        train, test, excluded = b.partition(rows, 'baseline', BOUNDARY)
        self.assertFalse(train or test)
        self.assertEqual(excluded['five-minute-each-side-embargo'], 2)
        self.assertEqual(excluded['different-sampling-policy'], 1)
        self.assertEqual(excluded['unverified-or-different-feature-schema'], 1)

    def test_failures_stay_in_selected_test_denominator(self):
        rows = [row(0, True), row(1, True)]
        rows[1]['targets']['30000'].update(state='sell-quote-failed', returnPct=None, onTime=None)
        _, test, _ = b.partition(rows, 'baseline', BOUNDARY)
        result = b.metrics(test, [.8, .9])
        self.assertEqual(result['validLabelCount'], 1)
        self.assertEqual(result['selectedAtHalf']['selected'], 2)
        self.assertEqual(result['selectedAtHalf']['onTimeValidatedReturns'], 1)
        self.assertEqual(result['selectedAtHalf']['targetStates']['sell-quote-failed'], 1)
        self.assertEqual(result['selectedAtHalf']['meanQuotedReturnPct'], 10)

    def test_failure_predictions_survive_full_fit(self):
        rows = sample(); rows[-1]['targets']['30000'].update(state='sell-quote-failed', returnPct=None, onTime=None)
        result = b.fit_cohort(rows, 'baseline', BOUNDARY)
        self.assertTrue(result['modelTrained'])
        self.assertEqual(len(result['predictions']), 30)
        self.assertEqual(result['logistic']['validLabelCount'], 29)

    def test_malformed_predictor_rejected_and_missing_not_zero(self):
        r = row(0); r['predictors']['liquidityUsd'] = 0
        matrix = b.matrix([r], 'baseline')
        self.assertEqual(matrix[0, 0], 0)
        r['predictors']['liquidityUsd'] = None
        self.assertTrue(np.isnan(b.matrix([r], 'baseline')[0, 0]))
        for value in (float('inf'), True, '100'):
            r['predictors']['liquidityUsd'] = value
            with self.assertRaises(ValueError): b.matrix([r], 'baseline')

    def test_no_identity_target_or_pricing_columns_used(self):
        r = row(0); before = b.matrix([r], 'baseline')
        r['mint'] = 'changed'; r['id'] = 'changed'; r['signalAt'] += 30000
        r['predictors']['inUsdValue'] = 999999
        r['targets']['30000']['returnPct'] = -999
        np.testing.assert_equal(b.matrix([r], 'baseline'), before)

    def test_small_or_single_class_samples_do_not_fit(self):
        self.assertFalse(b.fit_cohort([row(1)], 'baseline', BOUNDARY)['modelTrained'])
        rows = sample()
        for r in rows: r['targets']['30000']['returnPct'] = 10
        self.assertFalse(b.fit_cohort(rows, 'baseline', BOUNDARY)['modelTrained'])

    def test_repeat_fit_deterministic_and_no_live_activation(self):
        rows = sample(); provenance = {'coveredEntryIntervals': [[BOUNDARY - 1e9, BOUNDARY + 1e9]]}
        a = b.benchmark(rows, BOUNDARY, provenance); c = b.benchmark(rows, BOUNDARY, provenance)
        self.assertEqual(a, c)
        self.assertTrue(a['modelTrained']); self.assertFalse(a['liveUseAllowed'])
        with self.assertRaisesRegex(ValueError, 'boundary'): b.benchmark(rows, 1, provenance)

    def test_duplicate_inputs_do_not_inflate_and_conflicts_fail(self):
        index = {'sourceIdentity': 'same', 'indexSha256': 'hash', 'source': {},
                 'requestedStartAt': 1, 'entryWindowEndAt': 100, 'capturedAt': 200,
                 'counts': {}, 'requestedStartPrecedesEarliestRetained': False}
        fake = ([], [{'bytes': 1}], index)
        with patch.object(b, 'load_capture', return_value=fake), patch.object(b, 'dataset', return_value={'rows': [row(0)]}):
            rows, provenance = b.load_inputs(['a', 'b'])
            self.assertEqual(len(rows), 1); self.assertEqual(provenance['duplicateRowsRemoved'], 1)
        changed = row(0); changed['predictors']['organicScore'] = 99
        with patch.object(b, 'load_capture', return_value=fake), patch.object(b, 'dataset', side_effect=[{'rows': [row(0)]}, {'rows': [changed]}]):
            with self.assertRaisesRegex(ValueError, 'differs'): b.load_inputs(['a', 'b'])

    def test_source_and_total_input_caps(self):
        with self.assertRaises(ValueError): b.load_inputs(['a', 'b', 'c'])
        index = {'sourceIdentity': 'same', 'indexSha256': 'hash', 'source': {},
                 'requestedStartAt': 1, 'entryWindowEndAt': 100, 'capturedAt': 200,
                 'counts': {}, 'requestedStartPrecedesEarliestRetained': False}
        with patch.object(b, 'load_capture', return_value=([], [{'bytes': b.MAX_TOTAL_BYTES + 1}], index)):
            with self.assertRaisesRegex(ValueError, '128 MiB'): b.load_inputs(['a'])
        other = {**index, 'sourceIdentity': 'other'}
        with patch.object(b, 'load_capture', side_effect=[([], [], index), ([], [], other)]), patch.object(b, 'dataset', return_value={'rows': []}):
            with self.assertRaisesRegex(ValueError, 'identities'): b.load_inputs(['a', 'b'])


if __name__ == '__main__':
    unittest.main()
