#!/usr/bin/env python3
"""Small, fixed offline benchmark. No network, model activation or trading."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
import warnings

import numpy as np
import scipy
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'research-dataset'))
from build import build as dataset, publish, MAX_TOTAL_BYTES
from history import load_capture, iso_ms

VERSION = 'offline-ml-baseline-1'
POLICY = 'three-cohort-budgets-v3'
FEATURES = {
    'baseline': ['liquidityUsd', 'organicScore', 'top10Pct', 'return30sPct'],
    'early-activity': ['return30sPct', 'return60sPct', 'lastIntervalReturnPct', 'averageReportedTradeUsd'],
    'fast30-shadow': ['return30sPct', 'lastIntervalReturnPct', 'liquidityUsd'],
}
LOG_FIELDS = {'liquidityUsd', 'averageReportedTradeUsd', 'return30sPct', 'return60sPct', 'lastIntervalReturnPct'}
SCHEMAS = {'baseline': 'entry-features-1', 'early-activity': 'entry-features-1', 'fast30-shadow': 'fast-entry-features-1'}
PROTOCOL = {
    'id': VERSION, 'mode': 'exploratory-retrospective', 'samplingPolicy': POLICY,
    'target': 'positive quoted USDC return at 30 seconds after buy response, conditional on an on-time validated sell quote',
    'features': FEATURES, 'signedLog1pFields': sorted(LOG_FIELDS), 'classifier': 'L2 logistic regression',
    'C': 0.1, 'solver': 'lbfgs', 'maxIterations': 1000, 'selectionThreshold': 0.5,
    'preprocessing': 'Train-only median imputation with missing indicators, then train-only standardization.',
    'boundaryEmbargoMs': 300000, 'purge': 'All training tokens appearing in any admitted test cohort.',
    'minimumTrainRows': 50, 'minimumTrainPerClass': 10, 'minimumValidTestRows': 20,
    'minimumNote': 'Engineering fit guards; not statistical sufficiency or a promotion criterion.',
    'hyperparameterSearch': False, 'netProfitTarget': False, 'liveActivation': False,
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def load_inputs(directories):
    if not 1 <= len(directories) <= 2:
        raise ValueError('Provide one or two verified capture directories')
    rows, inputs, source, total_bytes, duplicates = {}, [], None, 0, 0
    for directory in directories:
        reports, provenance, index = load_capture(directory)
        total_bytes += sum(p['bytes'] for p in provenance)
        if total_bytes > MAX_TOTAL_BYTES:
            raise ValueError('Combined decompressed input exceeds 128 MiB')
        if source is not None and source != index['sourceIdentity']:
            raise ValueError('Different source identities cannot be combined')
        source = index['sourceIdentity']
        # Each capture independently retains the existing raw row and validation caps.
        data = dataset(reports)
        for row in data['rows']:
            if row['id'] in rows:
                if rows[row['id']] != row:
                    raise ValueError('Overlapping capture evidence differs; choose nonoverlapping windows')
                duplicates += 1
            rows[row['id']] = row
            if len(rows) > 20000:
                raise ValueError('Combined eligible-row cap exceeded')
        inputs.append({'indexSha256': index['indexSha256'], 'source': index['source'],
                       'startAt': index['requestedStartAt'], 'endAt': index['entryWindowEndAt'],
                       'evidenceCutoffAt': index['capturedAt'], 'counts': index['counts'],
                       'startsBeforeRetained': index['requestedStartPrecedesEarliestRetained']})
        del reports, data
    windows = []
    for i in sorted(inputs, key=lambda x: x['startAt']):
        if windows and i['startAt'] <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], i['endAt'])
        else:
            windows.append([i['startAt'], i['endAt']])
    return sorted(rows.values(), key=lambda r: (r['signalAt'], r['seq'])), {
        'sourceIdentity': source, 'captures': inputs, 'duplicateRowsRemoved': duplicates,
        'coveredEntryIntervals': windows, 'hasWindowGap': len(windows) > 1,
        'bytes': total_bytes, 'eligibleSignals': len(rows),
    }


def valid_target(row):
    t = row['targets']['30000']
    return (t['state'] == 'validated-sell-quote' and t['onTime'] is True
            and type(t['availableAt']) is int and type(t['returnPct']) in (int, float)
            and math.isfinite(t['returnPct']))


def partition(rows, cohort, boundary):
    test_mints = {r['mint'] for r in rows if r['decision'] == 'admitted' and r['signalAt'] >= boundary}
    train, test, excluded = [], [], Counter()
    for r in rows:
        if r['cohort'] != cohort or r['decision'] != 'admitted':
            continue
        if r['samplingPolicy'] != POLICY:
            excluded['different-sampling-policy'] += 1
        elif not r['entrySchemaVerified'] or r['featureCaptureVersion'] != SCHEMAS[cohort]:
            excluded['unverified-or-different-feature-schema'] += 1
        elif boundary - 300000 <= r['signalAt'] < boundary + 300000:
            excluded['five-minute-each-side-embargo'] += 1
        elif r['signalAt'] < boundary:
            if r['mint'] in test_mints:
                excluded['mint-present-in-test'] += 1
            elif not valid_target(r):
                excluded['training-without-valid-on-time-target'] += 1
            elif r['targets']['30000']['availableAt'] >= boundary:
                excluded['training-target-not-available-before-boundary'] += 1
            else:
                train.append(r)
        else:
            # Preserve failed/missing test quotes, including when the model selects them.
            test.append(r)
    return train, test, dict(excluded)


def matrix(rows, cohort):
    data = []
    for r in rows:
        values = []
        for key in FEATURES[cohort]:
            v = r['predictors'].get(key)
            if v is None:
                values.append(np.nan)
            elif type(v) not in (int, float) or not math.isfinite(v):
                raise ValueError('Invalid numeric predictor')
            else:
                values.append(math.copysign(math.log1p(abs(v)), v) if key in LOG_FIELDS else v)
        data.append(values)
    return np.asarray(data, dtype=float)


def returns(rows):
    values = [r['targets']['30000']['returnPct'] for r in rows if valid_target(r)]
    return {'selected': len(rows), 'onTimeValidatedReturns': len(values),
            'targetStates': dict(Counter(r['targets']['30000']['state'] for r in rows)),
            'withoutOnTimeValidatedReturn': len(rows) - len(values),
            'meanQuotedReturnPct': float(np.mean(values)) if values else None,
            'medianQuotedReturnPct': float(np.median(values)) if values else None,
            'meanExcludingBestPct': float(np.mean(sorted(values)[:-1])) if len(values) > 1 else None,
            'lossAtLeast50': sum(v <= -50 for v in values), 'positive': sum(v > 0 for v in values)}


def metrics(rows, probabilities):
    valid = [(r, float(p)) for r, p in zip(rows, probabilities) if valid_target(r)]
    y = np.array([int(r['targets']['30000']['returnPct'] > 0) for r, _ in valid])
    p = np.array([p for _, p in valid])
    result = {'validLabelCount': len(y), 'positiveLabels': int(y.sum()),
              'brier': float(brier_score_loss(y, p)) if len(y) else None,
              'logLoss': float(log_loss(y, p, labels=[0, 1])) if len(y) else None,
              'rocAuc': float(roc_auc_score(y, p)) if len(set(y)) == 2 else None,
              'accuracyAtHalf': float(np.mean((p >= .5) == y)) if len(y) else None,
              'selectedAtHalf': returns([r for r, p in zip(rows, probabilities) if p >= .5])}
    result['calibrationBins'] = []
    for low, high in [(0, .25), (.25, .5), (.5, .75), (.75, 1.0000001)]:
        subset = (p >= low) & (p < high)
        result['calibrationBins'].append({'low': low, 'high': min(high, 1), 'n': int(subset.sum()),
            'meanProbability': float(np.mean(p[subset])) if subset.any() else None,
            'observedPositiveFraction': float(np.mean(y[subset])) if subset.any() else None})
    return result


def fit_cohort(rows, cohort, boundary):
    train, test, excluded = partition(rows, cohort, boundary)
    y = np.array([int(r['targets']['30000']['returnPct'] > 0) for r in train])
    counts = Counter(y.tolist())
    result = {'cohort': cohort, 'features': FEATURES[cohort], 'trainRows': len(train), 'testRows': len(test),
              'trainClassCounts': dict(counts), 'excluded': excluded, 'modelTrained': False,
              'testAllCompatible': returns(test),
              'trainIdsSha256': digest([r['id'] for r in train]),
              'mintOverlap': len({r['mint'] for r in train} & {r['mint'] for r in test}),
              'featureAvailability': {part: {f: sum(r['predictors'].get(f) is not None for r in items)
                                     for f in FEATURES[cohort]} for part, items in [('train', train), ('test', test)]}}
    if (len(train) < 50 or min(counts.get(0, 0), counts.get(1, 0)) < 10
            or sum(valid_target(r) for r in test) < 20):
        result['state'] = 'insufficient-rows-for-benchmark-guard'
        return result
    x = matrix(train, cohort)
    model = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True),
                          StandardScaler(), LogisticRegression(C=.1, solver='lbfgs', max_iter=1000, random_state=0))
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        model.fit(x, y)
    probability = model.predict_proba(matrix(test, cohort))[:, 1]
    prior = np.full(len(test), y.mean())
    result.update(state='exploratory-fit-complete', modelTrained=True,
                  logistic=metrics(test, probability), constantPrior=metrics(test, prior))
    # Qualification is a fixed label comparison, not a calibrated probability baseline.
    qualified = [r for r in test if r['qualificationVersion'] == 'qualification-1'
                 and r['disposition'] in ('retain', 'defer')]
    result['existingQualification'] = {'comparableRows': len(qualified),
        'unknownOrLegacyRows': len(test) - len(qualified),
        'retain': returns([r for r in qualified if r['disposition'] == 'retain']),
        'defer': returns([r for r in qualified if r['disposition'] == 'defer'])}
    result['predictions'] = [{'id': r['id'], 'signalAt': r['signalAt'], 'probability': float(p),
        'constantPrior': float(y.mean()), 'target': r['targets']['30000']} for r, p in zip(test, probability)]
    result['byUtcDay'] = {day: metrics([r for r in test if r['utcDay'] == day],
        [p for r, p in zip(test, probability) if r['utcDay'] == day]) for day in sorted({r['utcDay'] for r in test})}
    result['fitAudit'] = {'imputation': model[0].statistics_.tolist(), 'indicatorColumns': model[0].indicator_.features_.tolist(),
        'scalerMean': model[1].mean_.tolist(), 'scalerScale': model[1].scale_.tolist(),
        'coefficient': model[2].coef_.tolist(), 'intercept': model[2].intercept_.tolist()}
    result['fitAuditSha256'] = digest(result['fitAudit'])
    return result


def benchmark(rows, boundary, provenance):
    if not any(start < boundary < end for start, end in provenance['coveredEntryIntervals']):
        raise ValueError('Test boundary must fall inside captured entry coverage')
    cohorts = [fit_cohort(rows, cohort, boundary) for cohort in FEATURES]
    return {'format': VERSION, 'protocol': PROTOCOL, 'protocolSha256': digest(PROTOCOL),
            'testStartAt': boundary, 'inputs': provenance, 'cohorts': cohorts,
            'runtime': {'python': sys.version.split()[0], 'sklearn': sklearn.__version__,
                        'numpy': np.__version__, 'scipy': scipy.__version__},
            'modelTrained': any(c['modelTrained'] for c in cohorts), 'liveUseAllowed': False,
            'limitations': ['Exploratory retrospective evaluation: historical aggregate outcomes were already inspected.',
                'Fixed features, regularization and threshold; no search or refit on test outcomes.',
                'Target is conditional on a returned on-time quote; failures are reported separately, not predicted as losses.',
                'Quotes are not fills or net profit. No fee, slippage or execution-success model is fitted.',
                'Nonrandom quota-limited admissions do not represent all detected tokens.',
                'Few days and small cohorts: metrics and selected returns are uncertain; no live promotion criterion.',
                'Older sampling policies and unverified entry schemas are excluded from fitting.',
                'A forward evaluation requires a frozen model and previously untouched later evidence.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture-dir', type=Path, action='append', required=True)
    p.add_argument('--test-start', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    rows, provenance = load_inputs(a.capture_dir)
    report = benchmark(rows, iso_ms(a.test_start), provenance)
    publish(a.output, report)
    for c in report['cohorts']:
        print(c['cohort'], c['state'], 'train=', c['trainRows'], 'test=', c['testRows'])
        if c['modelTrained']:
            print('Brier: model=', round(c['logistic']['brier'], 4), 'constant=', round(c['constantPrior']['brier'], 4), '(lower is better)')
    print('Offline exploratory benchmark only. No model activated. Report:', a.output.resolve())


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Offline benchmark stopped (' + type(error).__name__ + '): ' + str(error))
