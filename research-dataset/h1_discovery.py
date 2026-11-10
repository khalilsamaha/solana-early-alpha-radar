#!/usr/bin/env python3
"""One pinned, exploratory liquidity comparison. Saved evidence only; never trades."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics

import b1_design_audit as b1
from build import build, merge, review
from history import load_capture

HORIZON = '30000'
COSTS = (0, 0.20, 0.60)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def replay(directory, expected):
    chunks, inputs, index = load_capture(directory)
    # The existing loader verifies each indexed chunk; equality binds its entire
    # replay, including original index identity, to the accepted derived report.
    result = build(chunks)
    result.update(inputs=inputs, historyCapture=index)
    b1.require(result == expected, 'Original replay differs from accepted report')
    merged, _ = merge(chunks)
    cases = {c['seq']: c for c in review(merged)['cases']}
    probes = {p['signal']['seq']: p for p in merged['probes']}
    observations = {}
    for row in result['rows']:
        if row['decision'] != 'admitted':
            continue
        case, probe = cases[row['seq']], probes.get(row['seq'])
        buy = case['buy']
        exit_quote = case['exits'][HORIZON]
        original = (probe or {}).get('observations', [])
        raw_buy = next((o for o in original if o['leg'] == 'buy'), {})
        raw_sell = next((o for o in original if o['leg'] == 'sell' and o.get('targetOffsetMs') == 30000), {})
        if buy['state'] == 'validated-buy-quote':
            b1.require(buy['inputAtomic'] == '10000000', 'Unexpected notional')
        observations[row['id']] = {
            'probeSha256': digest(probe),
            'buyState': buy['state'],
            'buyRequestAt': buy.get('requestAt'), 'buyResponseAt': buy.get('responseAt'),
            'signalToBuyRequestMs': buy.get('signalToRequestMs'),
            'signalToBuyResponseMs': buy.get('signalToResponseMs'),
            'buyInputAtomic': buy.get('inputAtomic'),
            'tokenQuantityAtomic': buy.get('tokenQuantityAtomic'),
            'sellRequestAt': exit_quote.get('requestAt'),
            'sellResponseAt': exit_quote.get('responseAt'),
            'sellInputAtomic': exit_quote.get('inputAtomic'),
            'sellOutputAtomic': exit_quote.get('outputAtomic'),
            'scheduleDelayMs': exit_quote.get('scheduleDelayMs'),
            'responseAfterBuyMs': exit_quote.get('actualResponseAfterBuyMs'),
            'rawBuyClocks': {k: raw_buy.get(k) for k in ('startedAt', 'receivedAt', 'status')},
            'rawSellClocks': {k: raw_sell.get(k) for k in ('startedAt', 'receivedAt', 'status')},
        }
    return observations


def combine(reports):
    coverage = b1.audit(reports)
    rows, cutoffs = {}, {}
    for report in reports:
        for row in report['rows']:
            key = row['id']
            b1.require(key not in rows or rows[key] == row, 'Conflicting full duplicate row')
            rows[key] = row
            cutoffs[key] = min(cutoffs.get(key, report['capturedAt']), report['capturedAt'])
    return coverage, sorted(rows.values(), key=lambda r: (r['signalAt'], r['seq'])), cutoffs


def population(rows, source):
    first, seen, excluded = [], set(), []
    for row in rows:
        if row['cohort'] != 'baseline' or row['decision'] != 'admitted':
            continue
        reason = 'repeat-token' if row['mint'] in seen else b1.exclusion(b1.entry(row, source))
        seen.add(row['mint'])
        if reason:
            excluded.append({'id': row['id'], 'mint': row['mint'], 'reason': reason})
        else:
            first.append(row)
    threshold = statistics.median(r['predictors']['liquidityUsd'] for r in first) if first else None
    selected = {r['id'] for r in first if r['predictors']['liquidityUsd'] >= threshold}
    return first, selected, threshold, excluded


def outcome(row, cutoff):
    t = row['targets'][HORIZON]
    value = t['returnPct']
    if t['state'] != 'validated-sell-quote':
        b1.require(value is None, 'Return attached to invalid quote')
        return None, t['state']
    b1.require(row['buyQuoteState'] == 'validated-buy-quote' and finite(value) and value >= -100,
               'Invalid validated return')
    b1.require(type(t['availableAt']) is int and row['signalAt'] <= t['availableAt'] <= cutoff,
               'Invalid label availability clock')
    b1.require(t['sellQuoteReturned'] == 1 and type(t['onTime']) is bool,
               'Invalid validated target metadata')
    if t['onTime'] is not True:
        return None, 'late-validated-quote'
    b1.require(row['exitAvailability'][HORIZON] == 'on-time-validated-quote',
               'Target and availability disagree')
    return value, 'on-time-validated-quote'


def quantile(values, fraction):
    pos = (len(values) - 1) * fraction
    lo, hi = math.floor(pos), math.ceil(pos)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def describe(items):
    values = sorted(r['returnPct'] for r in items if r['returnPct'] is not None)
    positives = sorted((max(v, 0) for v in values), reverse=True)
    total_positive = math.fsum(positives)
    days = sorted({r['utcDay'] for r in items})
    by_day = {}
    for day in days:
        group = [r for r in items if r['utcDay'] == day]
        valid = [r['returnPct'] for r in group if r['returnPct'] is not None]
        by_day[day] = {'admissions': len(group), 'labelled': len(valid),
                       'meanPct': statistics.mean(valid) if valid else None,
                       'outcomeStates': dict(sorted(Counter(r['outcomeState'] for r in group).items()))}
    mean = statistics.mean(values) if values else None
    return {
        'admissions': len(items), 'labelled': len(values), 'unlabelled': len(items) - len(values),
        'labelCoverage': len(values) / len(items) if items else None,
        'uniqueTokens': len({r['mint'] for r in items}),
        'meanPct': mean, 'medianPct': statistics.median(values) if values else None,
        'worstPct': min(values) if values else None, 'bestPct': max(values) if values else None,
        'quantilesPct': {str(p): quantile(values, p) if values else None for p in (.05, .25, .5, .75, .95)},
        'positive': sum(v > 0 for v in values), 'lossAtLeast50': sum(v <= -50 for v in values),
        'bestTokenShareOfPositiveReturns': positives[0] / total_positive if total_positive else None,
        'topFiveShareOfPositiveReturns': math.fsum(positives[:5]) / total_positive if total_positive else None,
        'maxDayAdmissionShare': max((v['admissions'] for v in by_day.values()), default=0) / len(items) if items else None,
        'maxDayLabelShare': max((v['labelled'] for v in by_day.values()), default=0) / len(values) if values else None,
        'bySignalUtcDay': by_day,
        'buyStates': dict(sorted(Counter(r['buyQuoteState'] for r in items).items())),
        'outcomeStates': dict(sorted(Counter(r['outcomeState'] for r in items).items())),
        'breakEvenAdditionalUsdcAtMean': mean * .1 if mean is not None else None,
        'illustrativeExtraCost': [
            {'additionalUsdc': c, 'meanPct': mean - 10 * c if mean is not None else None,
             'medianPct': statistics.median(values) - 10 * c if values else None,
             'worstPct': min(values) - 10 * c if values else None,
             'positive': sum(v - 10 * c > 0 for v in values),
             'lossAtLeast50': sum(v - 10 * c <= -50 for v in values)} for c in COSTS],
    }


def comparison(items):
    groups = {name: describe(group) for name, group in (
        ('comparator', items), ('selected', [r for r in items if r['selected']]),
        ('rejected', [r for r in items if not r['selected']]))}
    a, b = groups['selected']['meanPct'], groups['comparator']['meanPct']
    contrast = a - b if a is not None and b is not None else None
    return {'groups': groups, 'selectedMinusComparatorPp': contrast,
            'contrastAtEachFixedCostPp': [{'additionalUsdc': c, 'contrastPp': contrast} for c in COSTS]}


def analyze(reports, observations=None):
    coverage, rows, cutoffs = combine(reports)
    eligible, selected, threshold, excluded = population(rows, reports[0]['sourceIdentity'])
    result = {
        'format': 'h1-offline-discovery-1', 'state': 'exploratory-only',
        'sourceIdentity': reports[0]['sourceIdentity'],
        'coverage': coverage, 'inputCompressedSha256': b1.HASHES,
        'rule': {'feature': 'entry-liquidity-usd', 'operator': '>=', 'medianUsd': threshold,
                 'fitPopulation': len(eligible), 'selected': len(selected),
                 'selectedFraction': len(selected) / len(eligible) if eligible else None,
                 'fitUsesOutcomes': False, 'horizonMs': 30000, 'notionalUsdc': 10},
        'excludedAdmissions': excluded, 'rawReplayVerified': observations is not None,
        'modelTrained': False, 'studyRegistered': False, 'gatePassed': False,
        'promotionAllowed': False, 'liveUseAllowed': False,
        'limitations': [
            'Already inspected discovery evidence; no untouched holdout, confidence or power claim.',
            'Nonrandom admissions; no inference to quota-skipped opportunities.',
            'Selected group overlaps comparator; their observations are not independent.',
            'Returns condition on valid on-time quotes; unlabelled exposure is economically unknown.',
            'Quotes are not fills; cost stresses are illustrative, not measured execution costs.',
            'Two complete requested UTC days do not establish continuous operation or independent samples.',
        ],
    }
    if not selected or len(selected) == len(eligible):
        result.update(state='uninformative-stop', comparison=None, sensitivities=None, rows=[])
        return result
    items = []
    for row in eligible:
        value, state = outcome(row, cutoffs[row['id']])
        if observations is not None:
            b1.require(row['id'] in observations, 'Missing original observation')
        items.append({k: row[k] for k in ('id', 'seq', 'mint', 'signalAt', 'utcDay', 'buyQuoteState')})
        items[-1].update(liquidityUsd=row['predictors']['liquidityUsd'], selected=row['id'] in selected,
                         returnPct=value, outcomeState=state, originalTarget=row['targets'][HORIZON],
                         quoteEvidence=observations[row['id']] if observations is not None else None)
    primary = comparison(items)
    admissions = [r for r in rows if r['cohort'] == 'baseline' and r['decision'] == 'admitted']
    result['allBaselineAdmissionStates'] = {
        'admissions': len(admissions),
        'buyStates': dict(sorted(Counter(r['buyQuoteState'] for r in admissions).items())),
        'quoteStates30s': dict(sorted(Counter(r['targets'][HORIZON]['state'] for r in admissions).items())),
        'availabilityStates30s': dict(sorted(Counter(r['exitAvailability'][HORIZON] for r in admissions).items())),
    }
    labelled_selected = [r for r in items if r['selected'] and r['returnPct'] is not None]
    best = min(labelled_selected, key=lambda r: (-r['returnPct'], r['signalAt'], r['seq'])) if labelled_selected else None
    daily = primary['groups']['selected']['bySignalUtcDay']
    labelled_days = [d for d in daily if daily[d]['meanPct'] is not None]
    day = min(labelled_days, key=lambda d: (-daily[d]['meanPct'], d)) if labelled_days else None
    result.update(comparison=primary, rows=items, sensitivities={
        'removeBestSelectedToken': {'removedMint': best['mint'] if best else None,
            'comparison': comparison([r for r in items if r['mint'] != best['mint']]) if best else None},
        'removeBestSelectedMeanDay': {'removedUtcDay': day,
            'comparison': comparison([r for r in items if r['utcDay'] != day]) if day else None},
        'thresholdRefitted': False,
    })
    result['disposition'] = ('uninformative-no-labels' if primary['selectedMinusComparatorPp'] is None
                             else 'descriptive-result-requires-review')
    return result


def run(live, backup, live_history, backup_history, output):
    reports = [b1.read_pinned(live, 'live'), b1.read_pinned(backup, 'backup')]
    observations = {}
    for directory, expected in zip((live_history, backup_history), reports):
        for key, value in replay(directory, expected).items():
            b1.require(key not in observations or observations[key] == value, 'Conflicting original observation')
            observations[key] = value
    result = analyze(reports, observations)
    result['originalIndexesSha256'] = [r['historyCapture']['indexSha256'] for r in reports]
    b1.publish(output, result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('live', 'backup', 'live-history', 'backup-history', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    result = run(**vars(args))
    print('H1:', result['state'], '; raw replay verified:', result['rawReplayVerified'])
    print('Report JSON SHA-256:', digest(result))
    print('Exploratory only; no gate, registration, model promotion or live-use authority.')
    print('Upload:', args.output.absolute())


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('H1 discovery stopped (' + type(exc).__name__ + '); no replacement report published.')
