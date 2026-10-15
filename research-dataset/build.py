#!/usr/bin/env python3
"""Bounded offline evidence audit and entry-only dataset. Never trains or trades."""
import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'qualification-review'))
from review import build as review, number, stamp, qualification, describe
from join_quotes import COHORTS, OFFSETS, IDENTITY_FIELDS
from report import publish

VERSION = 'research-dataset-1'
MAX_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
NUMERIC = ('liquidityUsd', 'organicScore', 'top10Pct', 'marketCap', 'holderCount',
           'return30sPct', 'return60sPct', 'drawdownPct', 'liquidityChange30sPct',
           'lastIntervalReturnPct', 'unchangedForMs', 'averageReportedTradeUsd',
           'transactions5m', 'volume5mUsd', 'baselineScore', 'experimentalScore')
SIGNED = {'return30sPct', 'return60sPct', 'drawdownPct', 'liquidityChange30sPct', 'lastIntervalReturnPct'}
AGES = ('securityCheckedAt', 'marketObservedAt', 'jupiterCheckedAt')
QUAL_FIELDS = {'return30sPct', 'return60sPct', 'drawdownPct', 'liquidityChange30sPct',
               'lastIntervalReturnPct', 'unchangedForMs', 'averageReportedTradeUsd',
               'transactions5m', 'volume5mUsd'}
CAPTURES = {'entry-features-1', 'fast-entry-features-1'}


def read(path):
    with (gzip.open(path, 'rb') if path.suffix == '.gz' else path.open('rb')) as f:
        raw = f.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Input byte cap exceeded')
    data = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    return data, {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def identity(signal):
    return {k: signal.get(k) for k in (*IDENTITY_FIELDS, 'features', 'featureCapture', 'followup')}


def merge(reports):
    """Deduplicate overlaps. Mutable watches may only append unchanged observations."""
    if not 1 <= len(reports) <= 16:
        raise ValueError('Provide 1..16 source exports')
    sources = {r.get('sourceIdentity') for r in reports}
    if len(sources) != 1 or not next(iter(sources)):
        raise ValueError('Different or absent source identities')
    signals, probes, windows = {}, {}, []
    duplicate_signals = duplicate_probes = 0
    for r in sorted(reports, key=lambda r: r['capturedAt']):
        review(r)  # Validate each export at its own cutoff before merging.
        start, end = r.get('windowStartAt'), r['capturedAt']
        if not stamp(start) or start > end:
            raise ValueError('Invalid export window')
        windows.append([start, end])
        for s in r['signals']:
            seq = s['seq']
            if seq in signals:
                if identity(s) != identity(signals[seq]) or s.get('decision') != signals[seq].get('decision'):
                    raise ValueError('Conflicting immutable signal')
                duplicate_signals += 1
            signals[seq] = s
        for p in r['probes']:
            seq = p['signal']['seq']
            if seq in probes:
                old = probes[seq]
                fixed = lambda x: {k: v for k, v in x.items() if k not in ('state', 'finishedAt', 'observations')}
                prefix = p.get('observations', [])[:len(old.get('observations', []))]
                if (fixed(old) != fixed(p) or prefix != old.get('observations', [])
                        or (old.get('finishedAt') is not None and old != p)):
                    raise ValueError('Conflicting or revised probe evidence')
                duplicate_probes += 1
            probes[seq] = p
        if len(signals) > 20000 or len(probes) > 20000:
            raise ValueError('Merged row cap exceeded; narrow input windows')
    merged = {'format': 'quote-observer-report-0.2.0', 'sourceIdentity': next(iter(sources)),
              'windowStartAt': min(w[0] for w in windows), 'capturedAt': max(w[1] for w in windows),
              'signals': list(signals.values()), 'probes': list(probes.values())}
    coverage = []
    for start, end in sorted(windows):
        if coverage and start <= coverage[-1][1]:
            coverage[-1][1] = max(end, coverage[-1][1])
        else:
            coverage.append([start, end])
    return merged, {'duplicateSignalsRemoved': duplicate_signals, 'duplicateProbesRemoved': duplicate_probes,
                    'exportWindows': windows, 'coveredIntervals': coverage,
                    'gapBetweenExports': len(coverage) > 1}


def entry_features(s):
    raw = s.get('features') or {}
    capture = s.get('featureCapture') or {}
    valid = capture.get('version') in CAPTURES and capture.get('signalAt') == s['signalAt']
    qtime = raw.get('qualificationAt')
    future_qualification = qtime is not None and (not stamp(qtime) or qtime > s['signalAt'])
    values = {}
    for key in NUMERIC:
        x = raw.get(key)
        good = valid and number(x) and (key in SIGNED or x >= 0)
        if key in QUAL_FIELDS and future_qualification:
            good = False
        values[key] = x if good else None
    for key in AGES:
        x = raw.get(key)
        values[key + 'AgeMs'] = s['signalAt'] - x if valid and stamp(x) and x <= s['signalAt'] else None
    values['historyReady'] = raw.get('historyReady') if valid and not future_qualification and type(raw.get('historyReady')) is bool else None
    values['disposition'] = raw.get('disposition') if valid and not future_qualification and raw.get('disposition') in ('retain', 'defer') else None
    values['security'] = raw.get('security') if valid and raw.get('security') in ('limited checks complete', 'expired or unavailable') else None
    return values, valid, future_qualification


def entry_conditions(features, disposition):
    """Metric flags only; never reconstruct the scanner's unrecorded decision state."""
    thresholds = {'lastIntervalReturnPct': -20, 'return30sPct': -10,
                  'drawdownPct': -15, 'liquidityChange30sPct': -30}
    severe = [k for k, limit in thresholds.items() if number(features.get(k)) and features[k] <= limit]
    negative = [k for k in ('return30sPct', 'return60sPct') if number(features.get(k)) and features[k] < 0]
    incomplete = features.get('historyReady') is not True
    unchanged = number(features.get('unchangedForMs')) and features['unchangedForMs'] > 45000
    flags = [*('adverse-' + k for k in severe), *('negative-' + k for k in negative)]
    if incomplete:
        flags.append('continuous-history-not-confirmed')
    if unchanged:
        flags.append('reported-fields-unchanged-over-45s')
    adverse = bool(severe or negative)
    if disposition != 'defer':
        bucket = 'not-deferred'
    elif incomplete and adverse:
        bucket = 'incomplete-history-and-adverse-metrics'
    elif adverse:
        bucket = 'adverse-metrics-with-ready-history'
    elif incomplete:
        bucket = 'incomplete-history-without-recorded-adverse-metrics'
    elif unchanged:
        bucket = 'ready-history-but-unchanged-fields'
    else:
        bucket = 'other-defer-condition-not-recorded'
    return {'bucket': bucket, 'flags': flags, 'exactDecisionReason': 'not-captured',
            'basis': 'Recorded entry metrics only; freshness and original decision precedence not reconstructed.'}


def pricing_audit(p, case):
    observations = p.get('observations', []) if p else []
    buy = next((o for o in observations if o.get('leg') == 'buy'), {})
    exits = []
    for h in OFFSETS:
        out = next((o for o in observations if o.get('leg') == 'sell' and o.get('targetOffsetMs') == h), {})
        evidence = case['exits'][str(h)]
        fields = (buy.get('inUsdValue'), buy.get('outUsdValue'), out.get('inUsdValue'), out.get('outUsdValue'))
        valid = (case['buy']['state'] == 'validated-buy-quote' and evidence['state'] == 'validated-sell-quote'
                 and buy.get('pricingEvidenceVersion') == out.get('pricingEvidenceVersion') == 'quote-pricing-1'
                 and all(number(x) and x > 0 for x in fields))
        row = {'offsetMs': h, 'quoteState': evidence['state'], 'state': 'available' if valid else 'unavailable',
               'actualResponseAfterBuyMs': evidence.get('actualResponseAfterBuyMs'),
               'quotedUsdcChangePct': evidence.get('quotedChangePct'),
               'tokenRouteChanged': evidence.get('tokenRouteChanged'),
               'providerPlatformFeeAmountKnown': out.get('platformFee', {}).get('amountAtomic') is not None,
               'factors': None}
        if valid:
            bi, bo, si, so = fields
            factors = {'buyOutputValueOverInputValue': bo / bi,
                       'laterTokenInputValueOverBuyOutputValue': si / bo,
                       'sellOutputValueOverInputValue': so / si}
            product = math.prod(factors.values())
            if not all(math.isfinite(v) for v in (*factors.values(), product, so / bi)):
                raise ValueError('Nonfinite pricing ratio')
            row.update(factors=factors, providerUsdValueChangePct=(so / bi - 1) * 100,
                       identityResidual=product - so / bi)
        exits.append(row)
    return {'seq': case['seq'], 'cohort': case['cohort'], 'exits': exits,
            'interpretation': 'Multiplicative identity in provider USD valuations, not causal price/fee/slippage attribution. No fees deducted again.'}


def target(case, p, h):
    if case is None:
        return {'state': 'not-admitted', 'returnPct': None, 'positiveQuotedReturn': None,
                'sellQuoteReturned': None, 'availableAt': None, 'onTime': None}
    e = case['exits'][str(h)]
    raw = next((o for o in (p or {}).get('observations', []) if o.get('leg') == 'sell' and o.get('targetOffsetMs') == h), {})
    valid = e['state'] == 'validated-sell-quote'
    # A transport failure is not evidence that a token has no quote route.
    provider_failure = (e['state'] == 'sell-quote-failed' and raw.get('httpStatus') == 400
                        and e.get('providerCategory') == 'quote-generation-failure-reported')
    availability = 1 if valid else 0 if provider_failure else None
    available_at = e.get('responseAt') if valid else raw.get('receivedAt') if provider_failure else None
    return {'state': e['state'], 'returnPct': e.get('quotedChangePct') if valid else None,
            'positiveQuotedReturn': int(e['quotedChangePct'] > 0) if valid else None,
            'sellQuoteReturned': availability, 'availableAt': available_at,
            'onTime': not e.get('lateBeyond5s') and not e.get('responseBeyond8s') if valid and h else None}


def summarize(rows):
    admitted = [r for r in rows if r['decision'] == 'admitted']
    result = {'signals': len(rows), 'admitted': len(admitted),
              'decisions': dict(collections.Counter(r['decision'] for r in rows)), 'horizons': {}}
    for h in OFFSETS:
        outcomes = [r['targets'][str(h)] for r in admitted]
        values = [o['returnPct'] for o in outcomes if o['returnPct'] is not None]
        result['horizons'][str(h)] = {**describe(values, len(admitted)),
                                     'states': dict(collections.Counter(o['state'] for o in outcomes))}
    return result


def split_audit(rows, test_start):
    if test_start is None:
        return {'state': 'not-requested', 'modelTrained': False, 'folds': []}
    if not stamp(test_start):
        raise ValueError('Invalid test boundary')
    groups = collections.defaultdict(list)
    for row in rows:
        if row['decision'] == 'admitted':
            groups[(row['cohort'], row['samplingPolicy'], row['featureCaptureVersion'])].append(row)
    # Purge a token from all training cohorts if it occurs in any test cohort.
    test_mints = {r['mint'] for r in rows if r['decision'] == 'admitted' and r['signalAt'] >= test_start}
    folds = []
    for key, items in sorted(groups.items()):
        train, test, excluded = [], [], collections.Counter()
        for row in items:
            t = row['targets']['30000']
            reason = None
            if not row['entrySchemaVerified']:
                reason = 'unverified-entry-schema'
            elif row['signalAt'] < test_start and row['mint'] in test_mints:
                reason = 'mint-present-in-test'
            elif row['signalAt'] < test_start and row['signalAt'] >= test_start - 300000:
                reason = 'five-minute-boundary-embargo'
            elif t['availableAt'] is None or t['onTime'] is not True:
                reason = 'no-on-time-validated-return'
            elif row['signalAt'] < test_start and t['availableAt'] >= test_start:
                reason = 'training-label-not-yet-available'
            if reason:
                excluded[reason] += 1
                row['split'] = reason
            elif row['signalAt'] < test_start:
                train.append(row)
                row['split'] = 'train'
            else:
                test.append(row)
                row['split'] = 'test'
        folds.append({'cohort': key[0], 'samplingPolicy': key[1], 'featureCaptureVersion': key[2],
                      'trainRows': len(train), 'testRows': len(test), 'excluded': dict(excluded),
                      'trainPositive': sum(r['targets']['30000']['positiveQuotedReturn'] for r in train),
                      'testPositive': sum(r['targets']['30000']['positiveQuotedReturn'] for r in test),
                      'trainUtcDays': len({r['utcDay'] for r in train}), 'testUtcDays': len({r['utcDay'] for r in test}),
                      'mintOverlap': len({r['mint'] for r in train} & {r['mint'] for r in test})})
    return {'state': 'audit-only', 'testStartAt': test_start, 'embargoMs': 300000,
            'modelTrained': False, 'primaryTarget': '30s positive quoted return, conditional on returned on-time quote',
            'folds': folds, 'note': 'A proposed split is not forward validation. No imputation, feature selection, fitting or threshold tuning performed.'}


def build(reports, test_start=None):
    merged, merge_info = merge(reports)
    validated = review(merged)
    cases = {c['seq']: c for c in validated['cases']}
    probes = {p['signal']['seq']: p for p in merged['probes']}
    signals = {s['seq']: s for s in merged['signals']}
    for seq, p in probes.items():
        signals.setdefault(seq, {**p['signal'], 'decision': 'admitted'})
    rows, audits, buckets = [], [], collections.defaultdict(list)
    for seq, s in sorted(signals.items(), key=lambda kv: (kv[1]['signalAt'] if kv[1].get('signalAt') else 0, kv[0])):
        if s.get('cohort') not in COHORTS:
            continue
        features, schema, future_q = entry_features(s)
        disposition, qversion = qualification(s)
        cond = entry_conditions(features, disposition)
        case, p = cases.get(seq), probes.get(seq)
        row = {'id': merged['sourceIdentity'] + ':' + str(seq), 'seq': seq, 'mint': s['mint'],
               'signalAt': s['signalAt'], 'utcDay': dt.datetime.fromtimestamp(s['signalAt'] / 1000, dt.timezone.utc).date().isoformat(),
               'cohort': s['cohort'], 'samplingPolicy': s.get('samplingPolicy', 'unrecorded'),
               'featureCaptureVersion': (s.get('featureCapture') or {}).get('version', 'unrecorded'),
               'qualificationVersion': qversion, 'disposition': disposition, 'decision': s.get('decision', 'unknown'),
               'entrySchemaVerified': schema, 'invalidQualificationTimestamp': future_q,
               'predictors': features, 'missingPredictors': [k for k, v in features.items() if v is None],
               'entryConditions': cond, 'targets': {str(h): target(case, p, h) for h in OFFSETS}, 'split': 'not-assigned'}
        rows.append(row)
        key = '/'.join((row['samplingPolicy'], row['cohort'], qversion, disposition, cond['bucket']))
        buckets[key].append(row)
        if case:
            audits.append(pricing_audit(p, case))
    split = split_audit(rows, test_start)
    missing = {}
    for cohort in COHORTS:
        sample = [r for r in rows if r['cohort'] == cohort and r['decision'] == 'admitted']
        missing[cohort] = {'admitted': len(sample), 'utcDays': len({r['utcDay'] for r in sample}),
                           'recorded': {k: sum(r['predictors'][k] is not None for r in sample) for k in (*NUMERIC, *(a + 'AgeMs' for a in AGES), 'historyReady', 'disposition', 'security')}}
    return {'format': VERSION, 'sourceIdentity': merged['sourceIdentity'], 'capturedAt': merged['capturedAt'],
            'merge': merge_info, 'summary': summarize(rows), 'deferBreakdown': {k: summarize(v) for k, v in sorted(buckets.items())},
            'featureAvailability': missing, 'pricingAudit': audits, 'splitAudit': split, 'rows': rows,
            'mlReadiness': {'state': 'dataset-and-validation-foundation', 'modelTrained': False, 'liveUseAllowed': False,
                            'newPricingWatches': sum(any(e['state'] == 'available' for e in a['exits']) for a in audits),
                            'requiredNext': ['Inspect feature missingness and quote failures by cohort and day.',
                                             'Freeze a small baseline model/protocol before future evaluation.',
                                             'Fit preprocessing only on training data; evaluate temporal and token-disjoint holdout.',
                                             'Compare with constant and existing-rule baselines; report failed quotes separately.']},
            'limitations': ['Predictors use entry fields only. Buy/sell valuations, routes and outcomes are audit/target fields, never predictors.',
                            'Do not feed metadata, row identities, target fields or pricingAudit into an entry-time model.',
                            'Entry capture provenance does not guarantee fresh, accurate provider measurements.',
                            'Metric buckets are descriptive; original qualification state/reasons were not captured and are not reconstructed.',
                            'Failures and skipped signals are retained. Missing returns are never replaced with zero or a loss.',
                            'SellQuoteReturned=0 means a reported HTTP 400 quote-generation failure, not proved unsellability; transport failures remain null.',
                            'Sampling is nonrandom; models trained on sampled watches cannot be assumed to generalize to skipped signals.',
                            'Any proposed split is exploratory unless a model/protocol was frozen before its test period.',
                            'Quotes and provider valuation ratios are not fills, net profitability or causal fee attribution.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--test-start', help='Explicit timezone-aware ISO timestamp; optional split audit only')
    args = parser.parse_args()
    if len(args.input) > 16:
        raise ValueError('Input count cap exceeded')
    reports, provenance, total = [], [], 0
    for path in args.input:
        data, meta = read(path)
        total += meta['bytes']
        if total > MAX_TOTAL_BYTES:
            raise ValueError('Total byte cap exceeded')
        reports.append(data)
        provenance.append(meta)
    boundary = None
    if args.test_start:
        value = dt.datetime.fromisoformat(args.test_start.replace('Z', '+00:00'))
        if value.utcoffset() is None:
            raise ValueError('Test boundary requires timezone')
        boundary = int(value.timestamp() * 1000)
    result = build(reports, boundary)
    result['inputs'] = provenance
    publish(args.output, result)
    print('Unique eligible signals:', result['summary']['signals'], '; watches:', result['summary']['admitted'])
    print('New pricing watches:', result['mlReadiness']['newPricingWatches'])
    print('ML: dataset prepared; no model trained or activated.')
    for f in result['splitAudit']['folds']:
        print(f['cohort'], 'train:', f['trainRows'], 'test:', f['testRows'], 'mint overlap:', f['mintOverlap'])
    print('Upload:', args.output.resolve())


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Research dataset stopped (' + type(error).__name__ + '): ' + str(error))
