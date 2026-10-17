#!/usr/bin/env python3
"""Descriptive review of validated local captures; no fitting or protocol changes."""
import argparse
import collections
import gzip
import json
import math
import statistics
from pathlib import Path

from audit import PROTOCOL, assess, eligibility, features, load_capture, publish, build
from build import merge


def distribution(values, total):
    values = sorted(v for v in values if type(v) in (int, float) and math.isfinite(v))
    n = len(values)
    return {'recorded': n, 'unavailable': total - n,
            'median': statistics.median(values) if n else None,
            'p95': values[math.ceil(.95 * n) - 1] if n else None,
            'min': values[0] if n else None, 'max': values[-1] if n else None}


def returns(rows, horizon):
    states = collections.Counter(r['exitAvailability'][str(horizon)] for r in rows)
    values = [r['targets'][str(horizon)]['returnPct'] for r in rows
              if r['exitAvailability'][str(horizon)] == 'on-time-validated-quote']
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError('Invalid return evidence')
    return {'admitted': len(rows), 'states': dict(states), 'quotedChangePct': {
        **distribution(values, len(rows)),
        'mean': statistics.mean(values) if values else None,
        'positive': sum(v > 0 for v in values), 'lossAtLeast50Pct': sum(v <= -50 for v in values),
        'meanWithoutSingleBest': statistics.mean(sorted(values)[:-1]) if len(values) > 1 else None}}


def elapsed(start, end):
    return end - start if type(start) is int and type(end) is int and 0 < start <= end else None


def timing(probe, signal_at):
    obs = probe.get('observations', []) if probe else []
    buy = next((o for o in obs if o.get('leg') == 'buy'), {})
    sells = [o for o in obs if o.get('leg') == 'sell']
    first = min(sells, key=lambda o: o.get('startedAt', float('inf')), default={})
    out = {'signalToBuyRequestMs': elapsed(signal_at, buy.get('startedAt')),
           'signalToBuyResponseMs': elapsed(signal_at, buy.get('receivedAt')),
           'buyResponseToFirstReverseRequestMs': elapsed(buy.get('receivedAt'), first.get('startedAt'))}
    for h in (30000, 120000):
        sell = next((o for o in sells if o.get('targetOffsetMs') == h), {})
        age = elapsed(buy.get('receivedAt'), sell.get('startedAt'))
        out[f'exit{h}SchedulingLatenessMs'] = age - h if age is not None and age >= h else None
    return out


def review(reports, registration):
    data = build(reports)  # All existing identity, quote and capture checks remain authoritative.
    raw, merge_info = merge(reports)
    probes = {p['signal']['seq']: p for p in raw['probes']}
    readiness = assess(data, registration)
    cohorts = []
    for guard in readiness['cohorts']:
        signals = [r for r in data['rows'] if r['cohort'] == guard['cohort']]
        compatible = [r for r in signals if eligibility(r) == 'compatible']
        rows = [r for r in compatible if r['decision'] == 'admitted']
        fv = [features(r) for r in rows]
        clocks = [timing(probes.get(r['seq']), r['signalAt']) for r in rows]
        first = min((r['signalAt'] for r in compatible), default=None)
        deficits = {}
        for name, target in guard['targets'].items():
            counts = target['classes']
            deficits[name] = {
                'labelledWatches': max(0, PROTOCOL['minimumTrainingRowsPerTargetCohort'] - target['labelled']),
                'examplesByClass': {str(c): max(0, PROTOCOL['minimumTrainingPerClass'] - counts.get(c, 0)) for c in (0, 1)},
                'distinctUtcDays': max(0, PROTOCOL['minimumTrainingUtcDays'] - target['utcDays']),
                'fitGuardsPassed': target['fitGuardsPassed']}
        cohorts.append({
            'cohort': guard['cohort'], 'compatibleAdmitted': len(rows),
            'uniqueMints': len({r['mint'] for r in rows}),
            'admittedByUtcDay': dict(collections.Counter(r['utcDay'] for r in rows)),
            'firstCompatibleSignalAt': first,
            'incompatibleSignalsSinceFirstCompatible': dict(collections.Counter(
                eligibility(r) for r in signals if first is not None and r['signalAt'] >= first and eligibility(r) != 'compatible')),
            'horizons': {str(h): returns(rows, h) for h in (30000, 120000)},
            'dailyHorizons': {day: {str(h): returns([r for r in rows if r['utcDay'] == day], h)
                                 for h in (30000, 120000)} for day in sorted({r['utcDay'] for r in rows})},
            'exitStateTransitions30To120s': dict(collections.Counter(
                r['exitAvailability']['30000'] + ' -> ' + r['exitAvailability']['120000'] for r in rows)),
            'features': {k: distribution([f[k] for f in fv], len(rows)) for k in PROTOCOL['features']},
            'timing': {k: distribution([c[k] for c in clocks], len(rows)) for k in timing(None, 1)},
            'guardDeficits': deficits})
    return {'format': 'readiness-details-1', 'readiness': readiness, 'merge': merge_info, 'cohorts': cohorts,
            'modelTrained': False, 'liveUseAllowed': False, 'networkRequests': 0,
            'limitations': [
                'Descriptive development evidence, not a held-out performance result or permission to trade.',
                'Quoted changes exclude unavailable or late quotes; every admitted watch remains in state denominators.',
                'Quotes are not fills or net profit. Receipt ages do not establish provider measurement freshness.',
                'Signal-to-request timing is observer latency, not token-launch-to-detection latency.',
                'The first reverse request uses its actual clock; a target offset of zero does not mean an instantaneous round trip.',
                'Timing and outcomes are audit-only and never added to entry model features.',
                'Fit guard deficits do not estimate a completion date or establish statistical sufficiency.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--history-dir', type=Path, required=True)
    p.add_argument('--registration', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    with gzip.open(a.registration, 'rb') as f:
        reg = f.read(16385)
    if len(reg) > 16384:
        raise ValueError('Registration byte cap exceeded')
    reports, provenance, index = load_capture(a.history_dir)
    result = review(reports, json.loads(reg))
    result.update(inputs=provenance, historyCapture=index)
    publish(a.output, result)
    for c in result['cohorts']:
        q = c['horizons']['30000']['quotedChangePct']
        print(c['cohort'], 'watches:', c['compatibleAdmitted'], '30s returned:', q['recorded'],
              'mean:', q['mean'], 'median:', q['median'])
    print('No model trained or activated. Upload:', a.output.resolve())


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        raise SystemExit('Readiness review stopped: ' + type(e).__name__ + ': ' + str(e))
