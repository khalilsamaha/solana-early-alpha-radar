#!/usr/bin/env python3
"""Offline, bounded evidence export from an already completed Radar backup."""
import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import sqlite3
import statistics
import sys
import time

VERSION = 'evidence-check-1'
ENGINE = '0.2.9'
ROOT = Path('/var/backups/solana-radar')
DAY = 86400000
LIMIT = 40000
SCAN_LIMIT = 1000000


def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def pick(obj, keys):
    if not isinstance(obj, dict):
        return {}
    return {k: obj[k] for k in keys.split() if k in obj}


def numeric_tree(obj, depth=0):
    if depth > 5:
        return None
    if number(obj) or isinstance(obj, bool) or obj is None:
        return obj
    if isinstance(obj, dict):
        return {k: numeric_tree(v, depth+1) for k, v in obj.items()
                if isinstance(v, (dict, int, float, bool)) or v is None}
    return None


def clean_history(value):
    result = pick(value, 'version basis poolAddress resetReason maxSamples')
    result['samples'] = [pick(row, 'at price volume buys sells liquidity changed')
                         for row in (value.get('samples', []) if isinstance(value, dict) else [])[:24]]
    result['inputs'] = pick(value.get('inputs') if isinstance(value, dict) else None,
                           'priceUsd pairAddress liquidityUsd volume5mUsd transactions5m providerPriceChange5mPct marketCap marketObservedAt securityCheckedAt jupiterCheckedAt holderCount')
    result['scoringMetrics'] = numeric_tree(value.get('scoringMetrics')) if isinstance(value, dict) else None
    return result


def clean(kind, r):
    common = 'id mint at version horizon status coverage dueAt lagMs sampleAt priceUsd pairAddress'
    fields = {
        'alerts': 'level engineVersion',
        'outcomes': 'symbol alertAt score entryMarketCap multiple maxMultiple drawdownFromEntryPct maxGapMs reason',
        'research-entries': 'cohort baselineScore experimentalScore security',
        'research-outcomes': 'entryId cohort entryAt returnPct reasonCode reason observationBasis',
        'snapshots': 'symbol dexId marketCap liquidityUsd score band observedAt archiveTier',
        'research-events': 'entryId cohort event stage baselineScore experimentalScore security fromPair toPair fromPool toPool migrationVerified',
        'decisions': 'source score liquidity marketFresh securityFresh securityComplete status marketObservedAt securityCheckedAt metadataReason',
        'exit-alerts': 'type',
    }
    out = pick(r, common + ' ' + fields.get(kind, ''))
    if isinstance(r.get('candidate'), dict):
        out['candidate'] = pick(r['candidate'], 'mint symbol priceUsd pairAddress liquidityUsd marketCap organicScore holderCount top10Pct dexId')
    for key in ('decisionTimeline', 'timeline', 'features', 'txns', 'volume', 'priceChange'):
        if key in r:
            out[key] = numeric_tree(r[key])
    if 'scoring' in r:
        out['scoring'] = pick(r['scoring'], 'score band reasons risks')
    if 'reasons' in r:
        out['reasons'] = r['reasons']
    if 'scoreRisks' in r:
        out['scoreRisks'] = r['scoreRisks']
    if isinstance(r.get('poolChange'), dict):
        out['poolChange'] = pick(r['poolChange'], 'at from to migrationVerified')
    if isinstance(r.get('evidence'), dict):
        out['evidence'] = pick(r['evidence'], 'entryPool lastSamePoolAt')
        out['evidence']['lastAttempt'] = pick(r['evidence'].get('lastAttempt'), 'at status pairAddress sampleAt')
    if isinstance(r.get('tokenFollowup'), dict):
        f = r['tokenFollowup']
        out['tokenFollowup'] = pick(f, 'version status basis sampleAt pairAddress quoteMint priceUsd returnPct coverage reason migrationVerified executionVerified')
        out['tokenFollowup']['evidence'] = numeric_tree(f.get('evidence'))
    if isinstance(r.get('qualification'), dict):
        q = r['qualification']
        out['qualification'] = pick(q, 'version mode at state disposition historyReady reasons flags')
        out['qualification']['metrics'] = numeric_tree(q.get('metrics'))
    if isinstance(r.get('evidence'), dict) and 'samples' in r['evidence']:
        out['evidence'] = clean_history(r['evidence'])
    if isinstance(r.get('evidenceHistory'), dict):
        out['evidenceHistory'] = clean_history(r['evidenceHistory'])
    return out


def iso(ms):
    return dt.datetime.fromtimestamp(ms/1000, dt.timezone.utc).isoformat()


def summary(rows, key):
    values = [r[key] for r in rows if r.get('status') == 'observed'
              and r.get('coverage') != 'gapped' and number(r.get(key))]
    return {'rows': len(rows), 'statusCounts': dict(collections.Counter(r.get('status', 'unknown') for r in rows)),
            'gapped': sum(r.get('coverage') == 'gapped' for r in rows),
            'validObserved': len(values), 'median': statistics.median(values) if values else None,
            'aboveEntry': sum(v > (1 if key == 'multiple' else 0) for v in values),
            'lossAtLeast50Pct': sum(v <= (.5 if key == 'multiple' else -50) for v in values)}


def analyze(db, cutoff, limit=LIMIT, scan_limit=SCAN_LIMIT):
    start = cutoff-DAY
    warnings, budgets = [], {}
    deadline = time.monotonic()+110
    db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)

    def events(kind, low=start, high=cutoff, cap=limit):
        count = 0
        truncated = False
        for (raw,) in db.execute('SELECT data FROM events INDEXED BY events_at WHERE kind=? AND at>=? AND at<=? ORDER BY at LIMIT ?',
                                 (kind, low, high, cap+1)):
            if time.monotonic() > deadline:
                raise RuntimeError('Analysis time budget exceeded; no complete report produced')
            if count == cap:
                truncated = True
                warnings.append(f'{kind}: row cap {cap} reached; this section is incomplete')
                break
            count += 1
            yield json.loads(raw)
        budgets[kind] = {'rowsRead': count, 'rowLimit': cap, 'truncated': truncated}

    alerts = []
    excluded = 0
    for a in events('alerts'):
        if a.get('engineVersion') != ENGINE:
            continue
        parts = str(a.get('id', '')).split(':')
        # Later score-level alerts must not redefine the original paper entry.
        if len(parts) != 3 or not parts[1].isdigit() or int(parts[1]) != a.get('at'):
            excluded += 1
            continue
        alerts.append(clean('alerts', a))
    entries = {(a['candidate']['mint'], a['at']): a for a in alerts}
    for a in entries.values():
        delivery = db.execute('SELECT status,at,delivered_at,attempts FROM outbox WHERE id=?', (a['id'],)).fetchone()
        a['notification'] = ({'status': delivery[0], 'queuedAt': delivery[1], 'deliveredAt': delivery[2],
                              'attempts': delivery[3], 'deliveryDelayMs': delivery[2]-a['at'] if delivery[2] else None}
                             if delivery else {'status': 'no-retained-outbox-row'})
    outcomes = [clean('outcomes', o) for o in events('outcomes')
                if (o.get('mint'), o.get('alertAt')) in entries]
    research = [clean('research-entries', r) for r in events('research-entries')
                if r.get('version') == 'research-'+ENGINE]
    ids = {r['id'] for r in research}
    research_outcomes = [clean('research-outcomes', o) for o in events('research-outcomes') if o.get('entryId') in ids]
    arithmetic_checks = []
    for o in outcomes:
        a = entries[(o['mint'], o['alertAt'])]
        price = a['candidate'].get('priceUsd')
        if o.get('status') == 'observed' and number(price) and price > 0 and number(o.get('priceUsd')) and number(o.get('multiple')):
            expected = o['priceUsd']/price
            if not math.isclose(expected, o['multiple'], rel_tol=1e-8, abs_tol=1e-10):
                arithmetic_checks.append({'mint': o['mint'], 'entryAt': o['alertAt'], 'horizon': o.get('horizon'),
                                          'storedMultiple': o['multiple'], 'recomputedMultiple': expected})
    selected = {}

    def select(mint, at, reason, duration=3600000):
        key = (mint, at)
        if key not in selected:
            selected[key] = {'mint': mint, 'entryAt': at, 'selectionReasons': [],
                             'windowStart': at-300000, 'windowEnd': min(cutoff, at+duration+120000),
                             'snapshots': [], 'decisions': [], 'researchEvents': [], 'exitAlerts': []}
        selected[key]['selectionReasons'].append(reason)

    eligible = [o for o in outcomes if o.get('horizon') == '60m' and o.get('status') == 'observed'
                and o.get('coverage') != 'gapped' and number(o.get('multiple'))]
    ranked = sorted(eligible, key=lambda o: (o['multiple'], o['mint'], o['alertAt']))
    for label, rows in [('lowest-60m-returns', ranked[:4]), ('highest-60m-returns', ranked[-4:])]:
        for o in rows:
            select(o['mint'], o['alertAt'], label)
    controls = sorted(entries, key=lambda x: hashlib.sha256(f'{x[0]}:{x[1]}'.encode()).hexdigest())[:4]
    for mint, at in controls:
        select(mint, at, 'deterministic-control-not-selected-by-return')
    alt_ids = sorted({o['entryId'] for o in research_outcomes
                      if o.get('tokenFollowup', {}).get('basis') == 'alternate-pool'})
    alternate = sorted((r for r in research if r['id'] in set(alt_ids)),
                       key=lambda r: hashlib.sha256(r['id'].encode()).hexdigest())[:4]
    for r in alternate:
        select(r['mint'], r['at'], 'alternate-pool-followup', 300000)
    by_mint = collections.defaultdict(list)
    for c in selected.values():
        by_mint[c['mint']].append(c)
    if selected:
        low = min(c['windowStart'] for c in selected.values())
        high = max(c['windowEnd'] for c in selected.values())
        for kind, target, cap in [('snapshots', 'snapshots', scan_limit), ('decisions', 'decisions', scan_limit),
                                  ('research-events', 'researchEvents', limit), ('exit-alerts', 'exitAlerts', limit)]:
            for r in events(kind, low, high, cap):
                mint = r.get('mint') or r.get('candidate', {}).get('mint')
                for c in by_mint.get(mint, []):
                    if c['windowStart'] <= r.get('at', 0) <= c['windowEnd']:
                        if len(c[target]) < 2000:
                            c[target].append(clean(kind, r))
                        else:
                            c.setdefault('truncatedSections', {})[target] = True
    for c in selected.values():
        rows = c['snapshots']
        gaps = [b['at']-a['at'] for a,b in zip(rows, rows[1:])]
        c['snapshotEvidence'] = {'samples': len(rows), 'largestArchivedGapMs': max(gaps, default=None),
                                'pairAddresses': sorted({r['pairAddress'] for r in rows if r.get('pairAddress')}),
                                'note': 'Archive gaps are not necessarily scanner gaps. Prices are provider observations, not fills.'}
        if c.get('truncatedSections'):
            warnings.append('Per-case row cap reached; inspect truncatedSections')
    if not entries:
        warnings.append('No first baseline entries for requested version in backup window')
    return {'format': VERSION, 'engineVersion': ENGINE, 'window': {'start': iso(start), 'end': iso(cutoff)},
            'completeWithinDeclaredWindow': not warnings, 'warnings': warnings, 'queryBudgets': budgets,
            'cohort': {'baselineEntries': len(entries), 'researchEntries': len(research),
                       'researchUniqueMints': len({r['mint'] for r in research}), 'excludedLaterOrUnrecognizedAlerts': excluded,
                       'baselineByHorizon': {h: summary([o for o in outcomes if o.get('horizon') == h], 'multiple')
                                             for h in ['5m','15m','60m']}},
            'baselineEntries': list(entries.values()), 'baselineOutcomes': outcomes,
            'baselineReturnArithmeticMismatches': arithmetic_checks,
            'researchEntries': research, 'researchOutcomes': research_outcomes, 'cases': list(selected.values()),
            'limitations': ['Latest completed backup only; later live observations are excluded.',
                           'Case histories are selected examples, not an unbiased performance estimate.',
                           'Unrecorded outcomes are not automatically losses or zero returns; maturity must be checked against cutoff.',
                           'No executed trades, slippage, fees, independent historical quotes or on-chain migration verification.',
                           'Receipt timestamps do not prove when the underlying market last traded.',
                           'Notification delivery time is sender acknowledgement time, not when the user saw the message.',
                           'Only allowlisted event fields and delivery metadata; no settings, credentials, outbox payloads or wallet data queried.']}


def main():
    global ENGINE
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--engine', choices=['0.2.8','0.2.9'], default='0.2.9')
    args = parser.parse_args()
    ENGINE = args.engine
    status = json.loads((ROOT/'last-run.json').read_text())
    if status.get('success') is not True or status.get('state') != 'complete':
        raise RuntimeError('Latest local backup is not marked complete; wait for backup completion')
    path = Path(status['backup']).resolve(strict=True)
    if path.parent != ROOT.resolve() or not path.name.startswith('auto-') or path.suffix != '.sqlite':
        raise RuntimeError('Backup path failed validation')
    if path.stat().st_size != status.get('bytes'):
        raise RuntimeError('Backup size differs from completed status')
    if any(Path(str(path)+suffix).exists() for suffix in ('-wal', '-journal')):
        raise RuntimeError('Backup has SQLite sidecar files; refusing to read it as a closed snapshot')
    cutoff = int(dt.datetime.fromisoformat(status['snapshot_at']).timestamp()*1000)
    print('Reading completed backup; live scanner remains untouched...', file=sys.stderr)
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('Hard 150-second time limit reached')))
    signal.alarm(150)
    before = path.stat()
    with sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA cache_size=-8192')
        db.execute('PRAGMA mmap_size=0')
        report = analyze(db, cutoff)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError('Backup changed while reading; discard this run')
    now = dt.datetime.now(dt.timezone.utc)
    report['capturedAt'] = now.isoformat()
    report['backup'] = {'filename': path.name, 'snapshotAt': iso(cutoff), 'bytes': before.st_size,
                        'ageHours': round((now.timestamp()*1000-cutoff)/3600000, 2)}
    if report['backup']['ageHours'] > 36:
        report['warnings'].append('Backup is more than 36 hours old; evidence is historical')
    encoded = json.dumps(report, separators=(',', ':'), allow_nan=False).encode()
    if len(encoded) > 48*1024*1024:
        raise RuntimeError('Report exceeded 48 MiB safety limit; no report saved')
    with open(args.output, 'wb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as f:
            f.write(encoded)
    signal.alarm(0)
    print(f"Collected {len(report['baselineEntries'])} baseline entries, {len(report['researchEntries'])} research entries and {len(report['cases'])} case histories.", file=sys.stderr)
    print(f"Evidence cutoff: {iso(cutoff)}; warnings: {len(report['warnings'])}", file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Audit stopped: {exc}', file=sys.stderr)
        sys.exit(1)
