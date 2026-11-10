import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import b1_design_audit as b1


START = 1793923200000  # 2026-11-06 00:00 UTC


def row(seq=1, mint='token-a', age=100):
    at = START + seq * 1000
    return {'id': 'source:' + str(seq), 'seq': seq, 'mint': mint, 'signalAt': at,
            'utcDay': b1.utc_day(at), 'cohort': 'baseline', 'decision': 'admitted',
            'samplingPolicy': 'three-cohort-budgets-v3', 'featureCaptureVersion': 'entry-features-1',
            'entrySchemaVerified': True, 'predictors': {'liquidityUsd': 10000, 'marketObservedAtAgeMs': age},
            'supplementalEntryContext': {'state': 'recorded', 'version': 'entry-context-1',
                'predictors': {'liquidityUsd': 10000, 'marketObservedAtAgeMs': age},
                'valueStates': {'liquidityUsd': 'recorded'}, 'clockStates': {'marketObservedAt': 'within-ttl'}}}


def report(rows, start=START, end=START + 2 * b1.DAY):
    return {'format': 'research-dataset-1', 'sourceIdentity': 'source', 'rows': rows,
            'merge': {'coveredIntervals': [[start, end]]},
            'historyCapture': {'complete': True, 'sourceIdentity': 'source',
                'requestedStartPrecedesEarliestRetained': False, 'windowClock': 'observer-detected-time',
                'requestedStartAt': start, 'entryWindowEndAt': end}}


class EntryOnly(dict):
    def __getitem__(self, key):
        if key in ('targets', 'exitAvailability', 'buyQuoteState', 'pricingAudit'):
            raise AssertionError('Outcome access')
        return super().__getitem__(key)

    def get(self, key, default=None):
        if key in ('targets', 'exitAvailability', 'buyQuoteState', 'pricingAudit'):
            raise AssertionError('Outcome access')
        return super().get(key, default)


class B1DesignTests(unittest.TestCase):
    def test_overlap_counts_once_and_does_not_read_outcomes(self):
        a = EntryOnly(row())
        b = EntryOnly(row())
        a['targets'] = {'returnPct': -99}
        b['targets'] = {'returnPct': 500}
        out = b1.audit([report([a]), report([b, row(2, 'token-b')])])
        self.assertEqual(out['uniqueEligibleRecords'], 2)
        self.assertEqual(out['duplicateEntryProjectionsRemoved'], 1)
        self.assertEqual(out['baselineCandidate']['featureUsableFirstAdmissions'], 2)
        self.assertFalse(out['outcomesAnalyzed'])
        self.assertFalse(out['gatePassed'])

    def test_entry_conflict_rejected(self):
        for mutate in (lambda r: r.update(mint='other'),
                       lambda r: r['predictors'].update(liquidityUsd=5),
                       lambda r: r.update(decision='hour-budget')):
            changed = row()
            mutate(changed)
            with self.assertRaisesRegex(ValueError, 'Conflicting entry'):
                b1.audit([report([row()]), report([changed])])

    def test_first_missing_feature_is_not_replaced_by_later_usable_admission(self):
        first = row()
        first['supplementalEntryContext']['predictors']['liquidityUsd'] = None
        out = b1.audit([report([first]), report([row(2)])])['baselineCandidate']
        self.assertEqual(out['repeatAdmissionsExcluded'], 1)
        self.assertEqual(out['featureUsableFirstAdmissions'], 0)
        self.assertEqual(out['firstAdmissionExclusions'], {'missing-invalid-or-zero-liquidity': 1})

    def test_cohorts_skips_and_contract_versions_stay_separate(self):
        other, skipped, old = row(2, 'b'), row(3, 'c'), row(4, 'd')
        other['cohort'] = 'early-activity'
        skipped['decision'] = 'observer-busy'
        old['featureCaptureVersion'] = 'old'
        out = b1.audit([report([row(), other]), report([skipped, old])])
        self.assertEqual(out['cohorts']['baseline']['eligibleRecords'], 3)
        self.assertEqual(out['cohorts']['baseline']['admissions'], 2)
        self.assertEqual(out['baselineCandidate']['featureUsableFirstAdmissions'], 1)
        self.assertEqual(out['baselineCandidate']['firstAdmissionExclusions'], {'incompatible-entry-contract': 1})

    def test_partial_days_and_gaps_are_not_counted_as_complete(self):
        out = b1.audit([report([], START + 1, START + b1.DAY),
                        report([], START + 2 * b1.DAY, START + 3 * b1.DAY)])
        self.assertEqual(out['completeRequestedUtcDays'], ['2026-11-08'])
        self.assertEqual(len(out['requestedDetectionIntervals']), 2)

    def test_adjacent_intervals_combine_into_complete_day(self):
        out = b1.audit([report([], START, START + b1.DAY // 2),
                        report([], START + b1.DAY // 2, START + b1.DAY)])
        self.assertEqual(out['completeRequestedUtcDays'], ['2026-11-06'])

    def test_bad_identity_or_capture_fails(self):
        for mutate in (lambda r: r.update(sourceIdentity='other'),
                       lambda r: r['historyCapture'].update(complete=False),
                       lambda r: r['historyCapture'].update(requestedStartPrecedesEarliestRetained=True),
                       lambda r: r['rows'][0].update(utcDay='2020-01-01'),
                       lambda r: r['rows'][0].update(id='other:1')):
            changed = report([row()])
            mutate(changed)
            with self.assertRaises(ValueError):
                b1.audit([report([row()]), changed])

    def test_missing_stale_disagreeing_or_invalid_context_is_excluded(self):
        variants = [None, 0, -1, True, float('nan')]
        for value in variants:
            r = b1.entry(row(), 'source')
            r['liquidity'] = value
            self.assertEqual(b1.exclusion(r), 'missing-invalid-or-zero-liquidity')
        for age, state in ((-1, 'within-ttl'), (101, 'within-ttl'), (100, 'stale')):
            r = b1.entry(row(), 'source')
            r.update(marketAge=age, marketClockState=state)
            self.assertEqual(b1.exclusion(r), 'market-clock-unusable')
        r = b1.entry(row(), 'source')
        r['legacyLiquidity'] = 1
        self.assertEqual(b1.exclusion(r), 'liquidity-contract-disagreement')

    def test_pin_and_caps_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'report.gz'
            raw = gzip.compress(json.dumps(report([row()])).encode())
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                b1.read_pinned(path, 'live')
            with patch.dict(b1.HASHES, live=hashlib.sha256(raw).hexdigest()):
                self.assertEqual(b1.read_pinned(path, 'live')['format'], 'research-dataset-1')
                with patch.object(b1, 'MAX_BYTES', len(raw) + 1):
                    with self.assertRaisesRegex(ValueError, 'Decompressed'):
                        b1.read_pinned(path, 'live')
            with patch.object(b1, 'MAX_BYTES', 1):
                with self.assertRaisesRegex(ValueError, 'Compressed'):
                    b1.read_pinned(path, 'live')
        with patch.object(b1, 'MAX_ROWS', 1):
            with self.assertRaisesRegex(ValueError, 'Union row cap'):
                b1.audit([report([row()]), report([row(2, 'b')])])

    def test_publication_preserves_existing_output_and_private_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.json.gz'
            b1.publish(path, {'state': 'first'})
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                b1.publish(path, {'state': 'second'})
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_order_independence_and_inputs_unchanged(self):
        inputs = [report([row(2, 'b'), row()]), report([row(3, 'c'), row()])]
        before = copy.deepcopy(inputs)
        self.assertEqual(b1.audit(inputs), b1.audit(list(reversed(inputs))))
        self.assertEqual(inputs, before)


if __name__ == '__main__':
    unittest.main()
