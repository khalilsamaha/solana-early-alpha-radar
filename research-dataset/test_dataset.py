import copy
import gzip
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from build import build, merge, entry_conditions, entry_features, NUMERIC, ROOT

sys.path.insert(0, str(ROOT / 'qualification-review'))
from test_review import sample


def fixture():
    q = sample(version=True)
    for s in [q['signals'][0], q['probes'][0]['signal']]:
        s['featureCapture'] = {'version': 'entry-features-1', 'signalAt': s['signalAt']}
        s['features'].update(return30sPct=2, return60sPct=4, drawdownPct=0, lastIntervalReturnPct=1,
                             liquidityChange30sPct=0, unchangedForMs=0)
    return q


def shift(q, millis, seq, mint=None):
    q = copy.deepcopy(q)
    def walk(x):
        if isinstance(x, dict):
            for k, v in list(x.items()):
                if k.endswith('At') and type(v) is int:
                    x[k] += millis
                elif k == 'seq':
                    x[k] = seq
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    old = q['signals'][0]['mint']
    walk(q)
    if mint:
        def replace(x):
            if isinstance(x, dict):
                for k,v in x.items():
                    if v == old:
                        x[k] = mint
                    else:
                        replace(v)
            elif isinstance(x, list):
                for v in x:
                    replace(v)
        replace(q)
    return q


class DatasetTests(unittest.TestCase):
    def test_input_unchanged_and_no_outcome_or_identity_predictors(self):
        q = fixture(); before = copy.deepcopy(q); r = build([q]); row = r['rows'][0]
        self.assertEqual(q, before)
        self.assertNotIn('mint', row['predictors'])
        self.assertNotIn('seq', row['predictors'])
        self.assertNotIn('inUsdValue', row['predictors'])
        self.assertNotIn('returnPct', row['predictors'])
        self.assertEqual(row['targets']['30000']['returnPct'], 10)
        self.assertFalse(r['mlReadiness']['modelTrained'])

    def test_exact_overlap_deduplicates_and_conflicting_entry_fails(self):
        q = fixture(); r = build([q, copy.deepcopy(q)])
        self.assertEqual(r['summary']['admitted'], 1)
        self.assertEqual(r['merge']['duplicateProbesRemoved'], 1)
        changed = copy.deepcopy(q)
        for s in [changed['signals'][0], changed['probes'][0]['signal']]:
            s['features']['liquidityUsd'] = 99
        with self.assertRaisesRegex(ValueError, 'immutable'):
            build([q, changed])

    def test_append_only_probe_progress_and_completed_evidence_cannot_change(self):
        q = fixture(); early = copy.deepcopy(q)
        early['capturedAt'] = q['signals'][0]['signalAt'] + 20000
        early['probes'][0]['observations'] = early['probes'][0]['observations'][:2]
        early['probes'][0].pop('finishedAt'); early['probes'][0]['state'] = 'watching'
        r = build([q, early]); self.assertEqual(r['summary']['admitted'], 1)
        self.assertEqual(r['rows'][0]['targets']['120000']['returnPct'], 10)
        changed = copy.deepcopy(q)
        changed['probes'][0]['observations'][2]['priceImpactPercentagePoints'] = 3
        with self.assertRaisesRegex(ValueError, 'revised'):
            build([q, changed])

    def test_different_source_identities_are_never_joined(self):
        q = fixture(); other = copy.deepcopy(q); other['sourceIdentity'] = 'other'
        with self.assertRaisesRegex(ValueError, 'source'):
            merge([q, other])

    def test_history_and_adverse_flags_overlap_without_claiming_actual_reason(self):
        a = entry_conditions({'historyReady': False, 'return30sPct': -11}, 'defer')
        self.assertEqual(a['bucket'], 'incomplete-history-and-adverse-metrics')
        self.assertEqual(a['exactDecisionReason'], 'not-captured')
        self.assertEqual(entry_conditions({'historyReady': True}, 'defer')['bucket'], 'other-defer-condition-not-recorded')
        self.assertEqual(entry_conditions({'historyReady': True, 'return60sPct': -1}, 'defer')['bucket'], 'adverse-metrics-with-ready-history')

    def test_zero_and_missing_and_future_qualification_are_distinct(self):
        q = fixture(); s = q['signals'][0]
        f, valid, _ = entry_features(s)
        self.assertTrue(valid); self.assertEqual(f['liquidityUsd'], 0); self.assertIsNone(f['organicScore'])
        s['features']['qualificationAt'] = s['signalAt'] + 1
        s['features']['securityCheckedAt'] = s['signalAt'] + 1
        f, _, future = entry_features(s)
        self.assertTrue(future); self.assertIsNone(f['return30sPct']); self.assertIsNone(f['historyReady'])
        self.assertIsNone(f['securityCheckedAtAgeMs'])

    def test_unverified_feature_schema_cannot_produce_predictors(self):
        q = fixture(); q['signals'][0]['featureCapture']['signalAt'] += 1
        f, valid, _ = entry_features(q['signals'][0])
        self.assertFalse(valid); self.assertTrue(all(v is None for v in f.values()))

    def test_provider_failure_transport_failure_and_skipped_are_not_zero_return(self):
        for status, code, expected in [('http-error', 400, 0), ('http-error', 503, None), ('timeout', None, None)]:
            q = fixture(); o = q['probes'][0]['observations'][2]
            o.update(status=status, httpStatus=code, providerCategory='quote-generation-failure-reported')
            t = build([q])['rows'][0]['targets']['30000']
            self.assertEqual(t['sellQuoteReturned'], expected); self.assertIsNone(t['returnPct'])
        q = fixture(); q['probes'] = []; q['signals'][0]['decision'] = 'observer-busy'
        t = build([q])['rows'][0]['targets']['30000']
        self.assertEqual(t['state'], 'not-admitted'); self.assertIsNone(t['sellQuoteReturned'])

    def test_pricing_identity_is_descriptive_and_never_changes_returns(self):
        q = fixture(); obs = q['probes'][0]['observations']
        obs[0].update(pricingEvidenceVersion='quote-pricing-1', inUsdValue=10, outUsdValue=9)
        for o in obs[1:]:
            o.update(pricingEvidenceVersion='quote-pricing-1', inUsdValue=8, outUsdValue=7,
                     platformFee={'amountAtomic': None})
        r = build([q]); a = r['pricingAudit'][0]['exits'][1]
        self.assertAlmostEqual(a['providerUsdValueChangePct'], -30)
        self.assertAlmostEqual(a['identityResidual'], 0)
        self.assertEqual(a['quotedUsdcChangePct'], 10)
        self.assertFalse(a['providerPlatformFeeAmountKnown'])
        obs[0]['outUsdValue'] = 0
        self.assertEqual(build([q])['pricingAudit'][0]['exits'][1]['state'], 'unavailable')

    def test_day_boundary_and_cross_cohort_mint_purge(self):
        q = fixture(); boundary = q['signals'][0]['signalAt'] + 86400000
        future = shift(q, 86400000, 901)
        other = shift(q, 0, 902, 'D' * 32)
        r = build([q, future, other], boundary)
        f = r['splitAudit']['folds'][0]
        self.assertEqual(f['trainRows'], 1); self.assertEqual(f['testRows'], 1)
        self.assertEqual(f['mintOverlap'], 0); self.assertEqual(f['excluded']['mint-present-in-test'], 1)
        future['signals'][0]['cohort'] = future['probes'][0]['signal']['cohort'] = 'early-activity'
        r = build([q, future], boundary)
        baseline = next(f for f in r['splitAudit']['folds'] if f['cohort'] == 'baseline')
        self.assertEqual(baseline['trainRows'], 0)

    def test_embargo_late_and_not_available_labels_are_excluded(self):
        q = fixture(); t = q['signals'][0]['signalAt']
        r = build([q], t + 200000)
        self.assertEqual(r['rows'][0]['split'], 'five-minute-boundary-embargo')
        o = q['probes'][0]['observations'][2]; o['startedAt'] += 6000; o['receivedAt'] += 6000
        r = build([q], t + 86400000)
        self.assertEqual(r['rows'][0]['split'], 'no-on-time-validated-return')
        q = fixture(); p = q['probes'][0]
        for o in p['observations']:
            o['startedAt'] += 400000; o['receivedAt'] += 400000
        p['finishedAt'] += 400000; q['capturedAt'] += 400000
        r = build([q], t + 350000)
        self.assertEqual(r['rows'][0]['split'], 'training-label-not-yet-available')

    def test_gaps_between_export_windows_remain_visible(self):
        q = fixture(); other = shift(q, 86400000 * 10, 901, 'D' * 32)
        r = build([q, other]); self.assertTrue(r['merge']['gapBetweenExports'])
        self.assertEqual(len(r['merge']['coveredIntervals']), 2)

    def test_cli_private_atomic_output_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d); src = path / 'in.json.gz'; out = path / 'out.json.gz'
            with gzip.open(src, 'wt') as f:
                json.dump(fixture(), f)
            cmd = [sys.executable, str(ROOT / 'research-dataset/build.py'), '--input', str(src), '--output', str(out)]
            first = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)
            old = out.read_bytes()
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(out.read_bytes(), old)

    def test_cli_refuses_naive_split_timestamp_without_output(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d); src = path / 'in.json'; out = path / 'out.json.gz'
            src.write_text(json.dumps(fixture()))
            result = subprocess.run([sys.executable, str(ROOT / 'research-dataset/build.py'), '--input', str(src),
                                     '--output', str(out), '--test-start', '2026-10-15T00:00:00'], capture_output=True)
            self.assertNotEqual(result.returncode, 0); self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
