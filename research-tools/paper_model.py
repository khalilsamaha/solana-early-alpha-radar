"""Fixed hypothetical policies; provider prices are observations, never claimed fills."""
import collections
import hashlib
from pathlib import Path
import math
import statistics

MODEL = 'sampled-policy-1'
# Fixed before collecting the next validation block; not tuned to historical winners.
POLICIES = (
    {'id': 'time-60', 'holdMs': 60000, 'targetPct': None, 'stopPct': None},
    {'id': 'time-120', 'holdMs': 120000, 'targetPct': None, 'stopPct': None},
    {'id': 'target20-stop15-time120', 'holdMs': 120000, 'targetPct': 20, 'stopPct': -15},
)
DELAYS = (0, 10000, 30000)
COSTS_BPS = (0, 100, 300)  # Each side, not total round trip. Sensitivity assumptions only.
MAX_GAP = 45000
OBSERVATION_WAIT = 30000
EXIT_DELAY = 10000


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def valid(row):
    return finite(row.get('at')) and finite(row.get('price')) and row['price'] > 0


def run_policy(entry, policy, delay_ms, cutoff, cost_bps=0):
    """No interpolation. A trigger is acted on only at a later eligible observation."""
    result = {'entryId': entry['id'], 'policy': policy['id'], 'delayMs': delay_ms,
              'costBpsPerSide': cost_bps, 'status': 'unresolved', 'reason': None}
    def finish(status, reason):
        return result | {'status': status, 'reason': reason}
    if entry.get('pathTruncated'):
        return finish('invalid', 'path-truncated')
    if not finite(entry.get('at')) or not entry.get('pairAddress') or not finite(cutoff):
        return finish('invalid', 'invalid-entry')
    if not finite(delay_ms) or delay_ms < 0 or not finite(cost_bps) or not 0 <= cost_bps < 10000:
        return finish('invalid', 'invalid-scenario')
    # Observations are grouped by exact time. Conflicting prices at one time are unresolved.
    by_time = {}
    conflicts = set()
    for p in entry.get('path', []):
        if not valid(p) or p['at'] < entry['at'] or p['at'] > cutoff:
            continue
        if p.get('pairAddress') != entry['pairAddress']:
            continue
        if p['at'] in by_time and by_time[p['at']]['price'] != p['price']:
            conflicts.add(p['at'])
        by_time[p['at']] = p
    path = [by_time[t] for t in sorted(by_time)]
    not_before = entry['at'] + delay_ms
    buy = next((p for p in path if p['at'] >= not_before), None)
    if not buy or buy['at'] > not_before + OBSERVATION_WAIT:
        return finish('pending' if cutoff <= not_before + OBSERVATION_WAIT else 'unresolved', 'no-timely-entry-observation')
    if buy['at'] in conflicts:
        return finish('invalid', 'conflicting-observations')
    result.update({'simulatedEntryAt': buy['at'], 'simulatedEntryPrice': buy['price'],
                   'entryDelayActualMs': buy['at'] - entry['at']})
    deadline = buy['at'] + policy['holdMs']
    trigger = None
    trigger_reason = None
    previous = buy
    for p in path:
        if p['at'] <= buy['at']:
            continue
        if p['at'] in conflicts:
            return finish('invalid', 'conflicting-observations')
        if p['at'] - previous['at'] > MAX_GAP:
            return finish('unresolved', 'observation-gap-before-exit')
        # Time limit has priority at/after deadline: no hindsight target after intended exit.
        ret = (p['price'] / buy['price'] - 1) * 100
        if trigger is None:
            if p['at'] >= deadline:
                trigger, trigger_reason = deadline, 'time-limit'
            elif policy.get('stopPct') is not None and ret <= policy['stopPct']:
                trigger, trigger_reason = p['at'], 'stop-observed'
            elif policy.get('targetPct') is not None and ret >= policy['targetPct']:
                trigger, trigger_reason = p['at'], 'target-observed'
        if trigger is not None and p['at'] >= trigger + EXIT_DELAY:
            if p['at'] > trigger + EXIT_DELAY + OBSERVATION_WAIT:
                return finish('unresolved', 'no-timely-exit-observation')
            factor = p['price'] / buy['price']
            cost = cost_bps / 10000
            result.update({'triggerAt': trigger, 'exitReason': trigger_reason,
                'simulatedExitAt': p['at'], 'simulatedExitPrice': p['price'],
                'holdingMs': p['at'] - buy['at'], 'grossReturnPct': (factor - 1) * 100,
                'netReturnPct': (factor * (1 - cost) / (1 + cost) - 1) * 100})
            return finish('observed-model', 'hypothetical-not-executed')
        previous = p
    due = (trigger if trigger is not None else deadline) + EXIT_DELAY + OBSERVATION_WAIT
    return finish('pending' if cutoff <= due else 'unresolved', 'no-timely-exit-observation')


def summary(rows):
    values = sorted(r['netReturnPct'] for r in rows if r['status'] == 'observed-model')
    status = dict(collections.Counter(r['status'] for r in rows))
    unresolved = sum(r['status'] in ('unresolved', 'invalid') for r in rows)
    mature = len(values) + unresolved
    # Explicit stress case, not an imputed result: every unresolved/invalid case loses all capital.
    return {'entries': len(rows), 'statusCounts': status,
        'reasonCounts': dict(collections.Counter(r['reason'] for r in rows if r['status'] != 'observed-model')),
        'observed': len(values), 'medianNetPct': statistics.median(values) if values else None,
        'meanNetPct': statistics.mean(values) if values else None,
        'aboveEntry': sum(v > 0 for v in values), 'loss50': sum(v <= -50 for v in values),
        'worstNetPct': min(values, default=None), 'bestNetPct': max(values, default=None),
        'meanExcludingBestPct': statistics.mean(values[:-1]) if len(values) > 1 else None,
        'unresolvedAsTotalLossStressMeanPct': (sum(values)-100*unresolved)/mature if mature else None,
        'stressNote': 'Explicit stress scenario, not an estimate of missing returns. Pending excluded.'}


def evaluate(entries, cutoff):
    results = []
    groups = {}
    for cohort in sorted({e['cohort'] for e in entries}):
        subset = [e for e in entries if e['cohort'] == cohort]
        for policy in POLICIES:
            for delay in DELAYS:
                gross = [run_policy(e, policy, delay, cutoff) for e in subset]
                for bps in COSTS_BPS:
                    adjusted = []
                    for row in gross:
                        row = dict(row, costBpsPerSide=bps)
                        if row['status'] == 'observed-model':
                            factor = row['simulatedExitPrice'] / row['simulatedEntryPrice']
                            cost = bps/10000
                            row['netReturnPct'] = (factor*(1-cost)/(1+cost)-1)*100
                        adjusted.append(row)
                    key = f'{cohort}/{policy["id"]}/delay{delay}/cost{bps}'
                    groups[key] = summary(adjusted)
                # Store per-entry no-cost outcomes once; other scenarios derive from these prices.
                results.extend(dict(r, cohort=cohort) for r in gross)
    return {'model': MODEL, 'codeSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'policies': list(POLICIES), 'entryDelaysMs': list(DELAYS),
            'exitDelayMs': EXIT_DELAY, 'costBpsPerSide': list(COSTS_BPS),
            'observationWaitMs': OBSERVATION_WAIT, 'maxObservationGapMs': MAX_GAP,
            'groups': groups, 'results': results,
            'limitations': ['Sampled provider prices, not fills; no order-book depth or route quotes.',
                'Costs are assumed proportional costs per side; fixed network fees and actual price impact unavailable.',
                'A zero-delay entry is a timing benchmark, not a claim of user execution speed.',
                'Missed intrainterval triggers remain unknowable even when observations are under 45 seconds apart.',
                'Baselines and early-activity cohorts overlap in mints; do not pool them as independent trades.',
                'No portfolio sizing, concurrency limit or capital reuse simulation; equal-weight episode results only.',
                'Scenarios are correlated sensitivity tests, not independent evidence of a winning strategy.']}
