"""Offline timing diagnostics. Never fill missing observations or infer execution."""
import collections
import math
import statistics

HORIZONS = {'30s': 30000, '60s': 60000, '120s': 120000, '300s': 300000}


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def distribution(values):
    values = sorted(values)
    return {'count': len(values), 'mean': statistics.mean(values) if values else None,
            'median': statistics.median(values) if values else None,
            'meanWithoutBest': statistics.mean(values[:-1]) if len(values) > 1 else None,
            'positive': sum(x > 0 for x in values), 'zero': sum(x == 0 for x in values),
            'lossAtLeast50': sum(x <= -50 for x in values)}


def timing_distribution(values):
    return {'count':len(values),'mean':statistics.mean(values) if values else None,
            'median':statistics.median(values) if values else None,
            'min':min(values) if values else None,'max':max(values) if values else None}


def analyze_timing(data):
    entries = {e['id']: e for e in data['fast-shadow-entries']}
    if len(entries) != len(data['fast-shadow-entries']):
        raise ValueError('Duplicate entry')
    outcomes = {}
    for o in data['fast-shadow-outcomes']:
        key = (o['entryId'], o['horizon'])
        if key in outcomes:
            raise ValueError('Duplicate outcome')
        outcomes[key] = o

    def state(e, h):
        o = outcomes.get((e['id'], h))
        if not o:
            return 'pending' if data['cutoffAt'] <= e['at'] + HORIZONS[h] + 30000 else 'overdue'
        if o.get('status') != 'observed':
            return 'missing'
        if o.get('coverage') != 'sampled':
            return 'gapped'
        if not (finite(o.get('returnPct')) and finite(o.get('sampleAt')) and
                e['at'] + HORIZONS[h] <= o['sampleAt'] <= e['at'] + HORIZONS[h] + 30000 and
                o.get('pairAddress') == e.get('pairAddress') and finite(o.get('priceUsd')) and
                o['priceUsd'] > 0 and finite(e.get('priceUsd')) and e['priceUsd'] > 0 and
                math.isclose(o['returnPct'], (o['priceUsd'] / e['priceUsd'] - 1) * 100, abs_tol=1e-8)):
            return 'invalid'
        return 'observed'

    def summarize(rows):
        result = {}
        for h, ms in HORIZONS.items():
            counts = collections.Counter(state(e, h) for e in rows)
            valid = [e for e in rows if state(e, h) == 'observed']
            result[h] = {'states': dict(counts),
                'grossPriceReturnPct': distribution([outcomes[e['id'], h]['returnPct'] for e in valid]),
                'sampleDelayAfterTargetMs': timing_distribution([outcomes[e['id'], h]['sampleAt'] - e['at'] - ms for e in valid])}
        return {'entries': len(rows), 'horizons': result}

    links = []; seen = set()
    for link in data['fast-shadow-links']:
        if link['entryId'] not in entries:
            continue
        key = (link['entryId'], link['cohort'])
        if key in seen:
            raise ValueError('Duplicate cohort link')
        seen.add(key)
        e = entries[link['entryId']]
        if (not finite(link.get('leadMs')) or link['leadMs'] < 0 or
                link.get('at') != e['at'] + link['leadMs'] or link.get('pairAddress') != e.get('pairAddress')):
            raise ValueError('Invalid link identity or timing')
        links.append(link)

    comparisons = []
    for link in links:
        e = entries[link['entryId']]
        for h in HORIZONS:
            item = {'entryId': e['id'], 'cohort': link['cohort'], 'horizon': h, 'state': 'unavailable',
                    'followup':e.get('followup') or {'policy':'legacy-unprioritized','admitted':False}}
            price, observed = link.get('comparisonPriceUsd'), link.get('comparisonObservedAt')
            if not (finite(price) and price > 0 and finite(observed) and 0 <= link['at'] - observed <= 45000):
                item['reason'] = 'comparison entry price or receipt time unavailable'
            elif state(e, h) != 'observed':
                item['reason'] = 'original-pool endpoint unavailable or gapped'
            elif outcomes[e['id'], h]['sampleAt'] < link['at']:
                item['reason'] = 'endpoint precedes comparison signal'
            else:
                o = outcomes[e['id'], h]
                fast = (o['priceUsd'] / e['priceUsd'] - 1) * 100
                later = (o['priceUsd'] / price - 1) * 100
                item.update(state='same-endpoint-price-comparison', sampleAt=o['sampleAt'],
                            fastGrossReturnPct=fast, comparisonGrossReturnPct=later,
                            differencePercentagePoints=fast-later)
            comparisons.append(item)

    policy = collections.defaultdict(list)
    for e in entries.values():
        followup = e.get('followup') or {}
        label = followup.get('policy', 'legacy-unprioritized')
        admission = 'admitted' if followup.get('admitted') else 'not-admitted'
        policy[label + '/' + admission].append(e)
    early_ids = {l['entryId'] for l in links if l['cohort'] == 'early-activity'}
    same = [e for e in entries.values() if all(state(e, h) == 'observed' for h in HORIZONS)]
    lead = {}
    for cohort in ['baseline', 'early-activity']:
        vals = [l['leadMs'] for l in links if l['cohort'] == cohort]
        lead[cohort] = {'linked': len(vals), 'simultaneous': vals.count(0), 'earlier': sum(x > 0 for x in vals),
                        'medianLeadMs': statistics.median(vals) if vals else None,
                        'medianPositiveLeadMs': statistics.median([x for x in vals if x > 0]) if any(vals) else None}
    return {'version': 'fast-timing-analysis-1', 'all': summarize(list(entries.values())),
            'lead': lead, 'byFollowupPolicy': {k: summarize(v) for k, v in policy.items()},
            'commonCompleteCohort': summarize(same), 'matchedEndpoints': comparisons,
            'eventualEarlyLinkCoverage': {
                'linked': summarize([e for e in entries.values() if e['id'] in early_ids]),
                'notLinked': summarize([e for e in entries.values() if e['id'] not in early_ids])},
            'limitations': ['Price observations only; no fees, execution delay or fills.',
                           'Eventual links and complete-path groups are hindsight diagnostics, not entry filters.',
                           'Receipt timestamps do not establish exchange freshness. Policies must be compared separately.']}
