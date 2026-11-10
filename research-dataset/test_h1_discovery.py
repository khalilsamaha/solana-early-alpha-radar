import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import h1_discovery as h1
from test_b1_design_audit import row as entry_row, report, START


def row(seq, liquidity, value, day=0, mint=None):
    r = entry_row(seq, mint or 'token-' + str(seq))
    r['signalAt'] += day * h1.b1.DAY
    r['utcDay'] = h1.b1.utc_day(r['signalAt'])
    r['predictors']['liquidityUsd'] = liquidity
    r['supplementalEntryContext']['predictors']['liquidityUsd'] = liquidity
    r['buyQuoteState'] = 'validated-buy-quote'
    r['targets'] = {'30000': {'state': 'validated-sell-quote', 'returnPct': value,
        'sellQuoteReturned': 1, 'onTime': True, 'availableAt': r['signalAt'] + 32000}}
    r['exitAvailability'] = {'30000': 'on-time-validated-quote'}
    return r


def pair(rows):
    r = report(rows)
    r['capturedAt'] = START + 4 * h1.b1.DAY
    return [r, copy.deepcopy(r)]


class DiscoveryTests(unittest.TestCase):
    def test_hand_calculated_overlap_comparator_and_all_costs(self):
        inputs = pair([row(1, 10, -5), row(2, 20, 0), row(3, 30, 10), row(4, 40, 30)])
        before = copy.deepcopy(inputs)
        r = h1.analyze(inputs)
        self.assertEqual(r['rule']['medianUsd'], 25)
        c = r['comparison']; g = c['groups']
        self.assertEqual((g['selected']['meanPct'], g['comparator']['meanPct']), (20, 8.75))
        self.assertEqual(c['selectedMinusComparatorPp'], 11.25)
        self.assertEqual([s['meanPct'] for s in g['selected']['illustrativeExtraCost']], [20, 18, 14])
        self.assertEqual([s['contrastPp'] for s in c['contrastAtEachFixedCostPp']], [11.25] * 3)
        self.assertEqual(g['selected']['breakEvenAdditionalUsdcAtMean'], 2)
        self.assertEqual(g['selected']['quantilesPct']['0.25'], 15)
        self.assertEqual(r['coverage']['uniqueEligibleRecords'], 4)
        self.assertEqual(inputs, before)
        self.assertEqual(h1.analyze(list(reversed(inputs))), r)
        self.assertFalse(r['rawReplayVerified'])
        for key in ('gatePassed', 'promotionAllowed', 'liveUseAllowed', 'modelTrained', 'studyRegistered'):
            self.assertFalse(r[key])

    def test_median_keeps_missing_labels_and_late_returns_are_not_zero(self):
        rows = [row(1, 10, 2), row(2, 20, 4), row(3, 30, 8), row(4, 40, 16)]
        rows[2]['targets']['30000'].update(state='sell-quote-failed', returnPct=None,
                                           sellQuoteReturned=None, availableAt=None, onTime=None)
        rows[2]['exitAvailability']['30000'] = 'transport-failure'
        rows[3]['targets']['30000']['onTime'] = False
        rows[3]['exitAvailability']['30000'] = 'late-validated-quote'
        r = h1.analyze(pair(rows)); g = r['comparison']['groups']['selected']
        self.assertEqual(r['rule']['medianUsd'], 25)
        self.assertEqual((g['admissions'], g['labelled'], g['unlabelled']), (2, 0, 2))
        self.assertIsNone(g['meanPct']); self.assertIsNone(r['comparison']['selectedMinusComparatorPp'])
        self.assertIsNone(r['sensitivities']['removeBestSelectedToken']['comparison'])

    def test_first_admission_excluded_before_later_good_feature_or_outcome(self):
        first = row(1, 0, -99, mint='repeat')
        later = row(2, 100, 1000, mint='repeat')
        r = h1.analyze(pair([first, later, row(3, 10, -3), row(4, 20, 2)]))
        self.assertEqual(r['rule']['medianUsd'], 15)
        self.assertEqual([x['reason'] for x in r['excludedAdmissions']],
                         ['missing-invalid-or-zero-liquidity', 'repeat-token'])
        self.assertNotIn('repeat', [r['mint'] for r in r['rows']])
        first = row(1, 30, -5, mint='repeat'); first['targets']['30000']['onTime'] = False
        r = h1.analyze(pair([first, later, row(3, 10, 1)]))
        self.assertEqual(r['comparison']['groups']['selected']['labelled'], 0)

    def test_full_duplicate_outcome_and_unused_field_conflicts_fail(self):
        for field in ('targets', 'extra-field'):
            reports = pair([row(1, 10, 1), row(2, 20, 2)])
            if field == 'targets': reports[1]['rows'][0]['targets']['30000']['returnPct'] = 9
            else: reports[1]['rows'][0][field] = 'changed'
            with self.assertRaisesRegex(ValueError, 'full duplicate'):
                h1.analyze(reports)

    def test_ties_retained_and_degenerate_stops_before_outcomes(self):
        r = h1.analyze(pair([row(1, 10, 0), row(2, 20, 1), row(3, 20, 2), row(4, 20, 3)]))
        self.assertEqual(r['rule']['selectedFraction'], .75)
        rows = [row(1, 20, 0), row(2, 20, 1)]
        for x in rows: x.pop('targets')
        r = h1.analyze(pair(rows))
        self.assertEqual(r['state'], 'uninformative-stop'); self.assertIsNone(r['comparison'])
        self.assertEqual(h1.analyze(pair([]))['state'], 'uninformative-stop')

    def test_sensitivity_removes_same_units_without_refitting(self):
        r = h1.analyze(pair([row(1, 10, 0, day=1), row(2, 20, -10),
                            row(3, 30, 5), row(4, 40, 25, day=1)]))
        s = r['sensitivities']; token = s['removeBestSelectedToken']
        self.assertEqual(token['removedMint'], 'token-4')
        self.assertEqual(token['comparison']['groups']['selected']['meanPct'], 5)
        self.assertEqual(token['comparison']['groups']['comparator']['admissions'], 3)
        day = s['removeBestSelectedMeanDay']
        self.assertEqual(day['removedUtcDay'], '2026-11-07')
        self.assertEqual(day['comparison']['groups']['comparator']['admissions'], 2)
        self.assertEqual(day['comparison']['groups']['selected']['admissions'], 1)
        self.assertFalse(s['thresholdRefitted'])

    def test_negative_economics_and_tail_not_clipped(self):
        r = h1.analyze(pair([row(1, 10, -100), row(2, 20, -50)]))
        g = r['comparison']['groups']['selected']
        self.assertEqual(g['breakEvenAdditionalUsdcAtMean'], -5)
        self.assertEqual(g['lossAtLeast50'], 1)
        self.assertIsNone(g['bestTokenShareOfPositiveReturns'])
        self.assertEqual(g['illustrativeExtraCost'][-1]['meanPct'], -56)

    def test_invalid_labels_fail_closed(self):
        mutators = [lambda t:t.update(returnPct=float('nan')), lambda t:t.update(returnPct=True),
                    lambda t:t.update(returnPct=-101), lambda t:t.update(availableAt=START-1),
                    lambda t:t.update(availableAt=START+5*h1.b1.DAY), lambda t:t.update(onTime=1),
                    lambda t:t.update(state='sell-quote-failed')]
        for mutate in mutators:
            rows = [row(1, 10, 1), row(2, 20, 2)]; mutate(rows[1]['targets']['30000'])
            with self.assertRaises(ValueError): h1.analyze(pair(rows))

    def test_other_cohorts_and_skips_stay_in_coverage_not_rule(self):
        a, b = row(3, 1000, 100), row(4, 2000, 200)
        a['cohort'] = 'early-activity'; b['decision'] = 'hour-budget'
        r = h1.analyze(pair([row(1, 10, 0), row(2, 20, 5), a, b]))
        self.assertEqual(r['rule']['medianUsd'], 15)
        self.assertEqual(r['coverage']['uniqueEligibleRecords'], 4)
        self.assertEqual(r['comparison']['groups']['comparator']['admissions'], 2)

    def test_selection_is_unchanged_when_outcomes_change(self):
        rows = [row(1, 10, -5), row(2, 20, 0), row(3, 30, 5)]
        first = h1.analyze(pair(rows))
        rows[0]['targets']['30000']['returnPct'] = 500
        rows[2]['targets']['30000']['returnPct'] = -99
        second = h1.analyze(pair(rows))
        self.assertEqual(first['rule'], second['rule'])
        self.assertEqual([r['id'] for r in first['rows'] if r['selected']],
                         [r['id'] for r in second['rows'] if r['selected']])

    def test_missing_original_observation_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Missing original'):
            h1.analyze(pair([row(1, 10, 0), row(2, 20, 5)]), {})


class RawReplayTests(unittest.TestCase):
    def setUp(self):
        from test_dataset import fixture, shift
        from test_entry_context import ContextTests
        from test_history import ledger
        import history
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.capture = self.root / 'capture'
        q = fixture(); context = ContextTests().signal()['entryContext']
        for s in (q['signals'][0], q['probes'][0]['signal']):
            s.update(cohort='baseline', samplingPolicy='three-cohort-budgets-v3')
            s['entryContext'] = copy.deepcopy(context)
            s['features'].update(liquidityUsd=10, marketObservedAt=s['signalAt']-1)
            s['entryContext']['data']['values']['liquidityUsd']['value'] = 10
        q['probes'][0]['samplingPolicy'] = 'three-cohort-budgets-v3'
        q2 = shift(q, 1000, 901, 'D' * 32)
        for s in (q2['signals'][0], q2['probes'][0]['signal']):
            s['features']['liquidityUsd'] = 20
            s['entryContext']['data']['values']['liquidityUsd']['value'] = 20
            for clock in s['entryContext']['data']['clocks'].values():
                if clock['at'] is not None:
                    clock['at'] += 1000
        self.original = [q, q2]
        db = self.root / 'source.sqlite'; ledger(db, self.original)
        end = q['signals'][0]['detectedAt'] + 3600000
        history.capture(db, self.capture, hours=1, chunk_hours=1, end_at=end, evidence_cutoff=end)
        chunks, inputs, index = history.load_capture(self.capture)
        self.expected = h1.build(chunks); self.expected.update(inputs=inputs, historyCapture=index)
        self.source = self.root / 'accepted.json.gz'
        self.source.write_bytes(gzip.compress(json.dumps(self.expected).encode()))
        self.hashes = dict.fromkeys(('live', 'backup'), hashlib.sha256(self.source.read_bytes()).hexdigest())

    def test_end_to_end_pinned_raw_replay_and_no_overwrite(self):
        with patch.dict(h1.b1.HASHES, self.hashes):
            output = self.root / 'result.json.gz'
            result = h1.run(self.source, self.source, self.capture, self.capture, output)
            self.assertTrue(result['rawReplayVerified']); self.assertEqual(result['rule']['medianUsd'], 15)
            self.assertEqual(result['comparison']['groups']['selected']['labelled'], 1)
            evidence = result['rows'][0]['quoteEvidence']
            self.assertEqual(evidence['buyInputAtomic'], '10000000')
            self.assertEqual(evidence['sellInputAtomic'], evidence['tokenQuantityAtomic'])
            self.assertGreaterEqual(evidence['sellRequestAt'] - evidence['buyResponseAt'], 30000)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            before = output.read_bytes()
            with self.assertRaises(FileExistsError):
                h1.run(self.source, self.source, self.capture, self.capture, output)
            self.assertEqual(output.read_bytes(), before)
            self.assertEqual(json.loads(gzip.decompress(before)), result)

    def test_wrong_raw_capture_or_report_never_publishes(self):
        altered = copy.deepcopy(self.expected); altered['rows'][0]['targets']['30000']['returnPct'] += 1
        with self.assertRaisesRegex(ValueError, 'replay differs'):
            h1.replay(self.capture, altered)
        output = self.root / 'no-report.gz'
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            h1.run(self.source, self.source, self.capture, self.capture, output)
        self.assertFalse(output.exists())
        chunk = self.capture / 'part-00.json.gz'; chunk.write_bytes(b'bad')
        with patch.dict(h1.b1.HASHES, self.hashes):
            with self.assertRaisesRegex(ValueError, 'checksum'):
                h1.run(self.source, self.source, self.capture, self.capture, output)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
