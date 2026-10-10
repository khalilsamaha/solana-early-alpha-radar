#!/usr/bin/env python3
"""Bounded read-only cohort capture and local paper research. No keys, HTTP or trades."""
import argparse
import collections
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import pwd
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from paper_model import evaluate, finite
from research_analysis import analyze, features, checkpoint

VERSION = 'radar-research-tools-1.1.0'
ROOT = Path('/var/backups/solana-radar')
REPORT_ROOT = Path('/var/lib/solana-radar-research')
PATH_MS = 600000
ENTRY_CAP = 3000
SCAN_CAP = 300000
PATH_CAP = 240
OUTPUT_CAP = 48*1024*1024
WAL_GROWTH_CAP = 64*1024*1024


def iso(ms):
    return dt.datetime.fromtimestamp(ms/1000, dt.timezone.utc).isoformat()


def text_value(v, maximum=128):
    return v[:maximum] if isinstance(v, str) else None


def compact_entry(row, cohort):
    c = row.get('candidate', {})
    at = row.get('at')
    mint = c.get('mint') if cohort == 'baseline' else row.get('mint')
    price = c.get('priceUsd') if cohort == 'baseline' else row.get('priceUsd')
    pool = c.get('pairAddress') if cohort == 'baseline' else row.get('pairAddress')
    if not isinstance(mint, str) or not isinstance(pool, str) or not finite(at) or not finite(price) or price <= 0:
        raise ValueError('Malformed eligible entry: refusing an incomplete cohort')
    q = row.get('qualification', {})
    metrics = q.get('metrics', {})
    return {'id': text_value(row.get('id'), 256), 'at': at, 'mint': text_value(mint),
        'pairAddress': text_value(pool), 'price': price, 'symbol': text_value(c.get('symbol'), 48),
        'cohort': cohort, 'score': row.get('scoring', {}).get('score') if cohort == 'baseline' else row.get('baselineScore'),
        'qualification': {k: q.get(k) for k in ['version', 'state', 'disposition', 'historyReady']},
        'averageReportedTradeUsd': metrics.get('averageReportedTradeUsd'),
        'entryFeatures': features(row), 'checkpoints': [],
        'path': [{'at': at, 'price': price, 'pairAddress': pool, 'basis': 'decision-quote'}],
        'pathTruncated': False}


def capture(path, hours=2, engine='0.2.9', live=False, cutoff=None, scan_cap=SCAN_CAP, budget=None):
    """A single consistent read transaction, released before evaluation/compression."""
    path = Path(path).resolve(strict=True)
    budget = budget if budget is not None else (15 if live else 90)
    started = time.monotonic()
    deadline = started + budget
    wal = Path(str(path)+'-wal')
    wal_start = wal.stat().st_size if wal.exists() else 0
    def guard():
        if time.monotonic() >= deadline:
            raise TimeoutError('Read budget exceeded; no partial research report published')
        if live and wal.exists() and wal.stat().st_size - wal_start > WAL_GROWTH_CAP:
            raise RuntimeError('WAL grew by more than 64 MiB during read; capture stopped')
    def progress():
        try:
            guard()
            return 0
        except (TimeoutError, RuntimeError):
            return 1
    if not live and any(Path(str(path)+s).exists() for s in ['-wal', '-journal']):
        raise RuntimeError('Closed backup has SQLite sidecars')
    before = path.stat()
    db = sqlite3.connect(path.as_uri()+'?mode=ro'+('' if live else '&immutable=1'), uri=True, timeout=1)
    budgets = {}
    entries = {}
    excluded_later = 0
    old_handler = None
    if hasattr(signal, 'SIGALRM'):
        def expired(*_):
            raise TimeoutError('Read wall-clock limit reached; transaction released')
        old_handler = signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, budget + 2)
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA cache_size=-4096')
        db.execute('PRAGMA mmap_size=0')
        db.set_progress_handler(progress, 1000)
        db.execute('BEGIN')
        db.execute('SELECT seq FROM events ORDER BY seq DESC LIMIT 1').fetchone()
        cutoff = cutoff if cutoff is not None else int(time.time()*1000)
        start = cutoff-hours*3600000
        def rows(kind, low=None, high=None):
            count = 0
            sql = 'SELECT data FROM events INDEXED BY events_at WHERE kind=? AND at>=? AND at<=? ORDER BY at LIMIT ?'
            for (raw,) in db.execute(sql, (kind, start if low is None else low, cutoff if high is None else high, scan_cap+1)):
                guard()
                count += 1
                if count > scan_cap:
                    raise RuntimeError(f'{kind} row limit reached; no partial report published')
                if len(raw) > 256*1024:
                    raise RuntimeError('Event too large for bounded export')
                yield json.loads(raw)
            budgets[kind] = count
        for a in rows('alerts'):
            if a.get('engineVersion') != engine:
                continue
            parts = str(a.get('id', '')).split(':')
            if len(parts) != 3 or not parts[1].isdigit() or int(parts[1]) != a.get('at'):
                excluded_later += 1
                continue
            entry = compact_entry(a, 'baseline')
            if entry['id'] in entries:
                raise RuntimeError('Duplicate entry identifier')
            entries[entry['id']] = entry
            if len(entries) > ENTRY_CAP:
                raise RuntimeError('Entry cap reached; narrow the time window')
        for r in rows('research-entries'):
            if r.get('version') != 'research-'+engine or r.get('cohort') != 'early-activity':
                continue
            entry = compact_entry(r, 'early-activity')
            if entry['id'] in entries:
                raise RuntimeError('Duplicate entry identifier')
            entries[entry['id']] = entry
            if len(entries) > ENTRY_CAP:
                raise RuntimeError('Entry cap reached; narrow the time window')
        by_mint = collections.defaultdict(list)
        for entry in entries.values():
            by_mint[entry['mint']].append(entry)
        path_start = min((e['at'] for e in entries.values()), default=cutoff)
        path_end = min(cutoff, max((e['at']+PATH_MS for e in entries.values()), default=cutoff))
        for row in rows('snapshots', path_start, path_end):
            if row.get('mint') not in by_mint:
                continue
            observed = row.get('observedAt', row.get('at'))
            if not finite(observed) or not finite(row.get('priceUsd')) or row['priceUsd'] <= 0:
                continue
            for entry in by_mint[row['mint']]:
                if not entry['at'] <= observed <= min(cutoff, entry['at']+PATH_MS):
                    continue
                if len(entry['path']) >= PATH_CAP:
                    entry['pathTruncated'] = True
                    continue
                entry['path'].append({'at': observed, 'price': row['priceUsd'],
                    'pairAddress': text_value(row.get('pairAddress')), 'basis': 'provider-response-time',
                    'liquidityUsd':row.get('liquidityUsd') if finite(row.get('liquidityUsd')) else None})
        # Full-cadence samples in event evidence recover some observations not archived routinely.
        # They must already exist by the cutoff. They never create interpolated ticks.
        ids = {e['id']:e for e in entries.values() if e['cohort']=='early-activity'}
        baseline_by_key = {(e['mint'],e['at']):e for e in entries.values() if e['cohort']=='baseline'}
        for row in rows('research-outcomes', path_start, path_end):
            entry = ids.get(row.get('entryId')) if row.get('cohort')=='early-activity' else baseline_by_key.get((row.get('mint'),row.get('entryAt')))
            if not entry:
                continue
            if row.get('horizon') in ('30s','1m','2m','5m') and len(entry['checkpoints'])<4:
                entry['checkpoints'].append(checkpoint(row))
            evidence = row.get('evidenceHistory', {})
            samples = evidence.get('samples', [])
            pool = evidence.get('poolAddress')
            for p in samples[:24]:
                if finite(p.get('at')) and finite(p.get('price')) and p['price']>0 and entry['at']<=p['at']<=min(cutoff,entry['at']+PATH_MS):
                    if len(entry['path']) >= PATH_CAP:
                        entry['pathTruncated'] = True
                        break
                    entry['path'].append({'at':p['at'],'price':p['price'],'pairAddress':text_value(pool),'basis':'provider-response-time',
                        'liquidityUsd':p.get('liquidity') if finite(p.get('liquidity')) else None})
            # Exact original-pool checkpoint, when recorded, can also support the path.
            if row.get('status')=='observed' and finite(row.get('sampleAt')) and finite(row.get('priceUsd')) and row['priceUsd']>0 and entry['at']<=row['sampleAt']<=min(cutoff,entry['at']+PATH_MS):
                if len(entry['path'])<PATH_CAP:
                    entry['path'].append({'at':row['sampleAt'],'price':row['priceUsd'],'pairAddress':entry['pairAddress'],'basis':'provider-response-time'})
                else:
                    entry['pathTruncated']=True
        guard()
    finally:
        db.set_progress_handler(None, 0)
        db.close()
        if old_handler is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
    if not live and (path.stat().st_size, path.stat().st_mtime_ns)!=(before.st_size,before.st_mtime_ns):
        raise RuntimeError('Backup changed during read')
    for entry in entries.values():
        # Remove exact duplicates, retaining conflicting prices for evaluator invalidation.
        dedup={}
        for p in entry['path']:
            key=(p['at'],p['price'],p['pairAddress'])
            if key not in dedup:dedup[key]=dict(p);continue
            prior=dedup[key];liq=p.get('liquidityUsd')
            if finite(liq) and not prior.get('liquidityConflict'):
                if finite(prior.get('liquidityUsd')) and prior['liquidityUsd']!=liq:
                    prior['liquidityUsd']=None;prior['liquidityConflict']=True
                else:prior['liquidityUsd']=liq
        entry['path'] = sorted(dedup.values(),key=lambda p:p['at'])
        times = [p['at'] for p in entry['path'] if p['pairAddress']==entry['pairAddress']]
        entry['pathCoverage'] = {'samples':len(times),'largestGapMs':max((b-a for a,b in zip(times,times[1:])),default=None),
            'lastSamePoolAt':max(times,default=None),'endedBeforeTenMinutes':cutoff<entry['at']+PATH_MS}
    return {'format':VERSION, 'engineVersion':engine, 'capturedAt':iso(int(time.time()*1000)),
        'window':{'start':iso(start),'end':iso(cutoff)}, 'cutoffMs':cutoff,
        'source':{'mode':'live-readonly' if live else 'completed-backup', 'databaseBytes':before.st_size,
            'readSeconds':round(time.monotonic()-started,3), 'readBudgetSeconds':budget},
        'completeCohortWithinWindow':True, 'rowsRead':budgets,'pathQueryWindow':{'start':iso(path_start),'end':iso(path_end)},'excludedLaterAlerts':excluded_later,
        'entries':list(entries.values()), 'notes':[
            'All eligible first baseline and early-activity entries in the window; no outcome-based selection.',
            'Complete cohort does not mean complete price paths: gaps and missing prices remain explicit.',
            'Early-activity path gaps may reflect sparse archive evidence, not scanner downtime; later checkpoints may add older observations.',
            'Ten minutes of bounded archived path per entry; original pool only in policy evaluation.',
            'Decision quote is seeded at decision time for the zero-delay benchmark; not an executed fill.',
            'Receipt times do not prove last-trade time. No credentials or outbox payloads queried.',
            'Overlapping rolling reports are not independent observations; deduplicate by entryId before pooling.']}


def completed_backup():
    s = json.loads((ROOT/'last-run.json').read_text())
    if s.get('success') is not True or s.get('state')!='complete':
        raise RuntimeError('Latest backup is not marked complete')
    p = Path(s['backup']).resolve(strict=True)
    if p.parent!=ROOT.resolve() or not p.name.startswith('auto-') or p.suffix!='.sqlite' or p.stat().st_size!=s.get('bytes'):
        raise RuntimeError('Completed backup validation failed')
    return p, int(dt.datetime.fromisoformat(s['snapshot_at']).timestamp()*1000)


def live_database(project):
    def command(args):
        return subprocess.run(args,cwd=project,check=True,capture_output=True,text=True,timeout=10).stdout.strip()
    cid = command(['docker','compose','ps','-q','radar'])
    if not cid or '\n' in cid:
        raise RuntimeError('Expected one running radar container')
    info = json.loads(command(['docker','inspect',cid]))[0]
    if not info.get('State',{}).get('Running'):
        raise RuntimeError('Radar container is not running')
    mounts = [m for m in info.get('Mounts',[]) if m.get('Destination')=='/app/data']
    if len(mounts)!=1 or mounts[0].get('Type') not in ('volume','bind'):
        raise RuntimeError('Cannot locate the radar data mount')
    return Path(mounts[0]['Source']).resolve(strict=True)/'radar.sqlite'


def summary_text(report):
    lines = [VERSION, f"Evidence cutoff: {report['window']['end']}",
             f"Source: {report['source']['mode']}; read {report['source']['readSeconds']} seconds",
             f"Cohort: {dict(collections.Counter(e['cohort'] for e in report['entries']))}",
             'Hypothetical sampled prices. Costs shown below: 1% EACH side; entry delay 10s; exit delay 10s.',
             'No live trades, route quotes or profitability claims.']
    for key, s in report['evaluation']['groups'].items():
        if '/delay10000/cost100' not in key:
            continue
        med = 'n/a' if s['medianNetPct'] is None else f"{s['medianNetPct']:.2f}%"
        mean = 'n/a' if s['meanNetPct'] is None else f"{s['meanNetPct']:.2f}%"
        lines.append(f"{key}: observed={s['observed']}/{s['entries']}; median={med}; mean={mean}; losses>=50%={s['loss50']}; states={s['statusCounts']}")
    if 'analysis' in report:
        a=report['analysis']
        lines.append('Evidence explanations (model outcomes above remain unchanged):')
        for key, counts in a['evidenceCoverage'].items(): lines.append(f'{key}: {counts}')
        lines.append(f"Severe-loss case records: {len(a['severeLossCases'])} (policies overlap)")
        reg=a.get('registration')
        lines.append('Shadow validation starts: '+(iso(reg['registeredAtMs']) if reg else 'not registered; exploratory only'))
        lines.append('Entry feature availability: '+json.dumps(a['featureAvailability']))
        lines.append('Shadow comparison tables are in analysis.shadowGroups; selected/excluded/unknown all retained.')
    lines.append('Upload the .json.gz report for complete scenarios, paths and unresolved cases.')
    return '\n'.join(lines)+'\n'


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.research-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600)
        os.replace(tmp,path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def publish(report, destination):
    encoded = json.dumps(report,separators=(',',':'),allow_nan=False).encode()
    if len(encoded)>OUTPUT_CAP:
        raise RuntimeError('Report exceeds 48 MiB uncompressed limit; narrow window')
    atomic_write(destination,gzip.compress(encoded,compresslevel=5,mtime=0))


def prune_reports(directory, keep=48, max_bytes=512*1024*1024):
    rows=sorted((p for p in directory.glob('research-*.json.gz') if p.is_file() and not p.is_symlink()), key=lambda p:p.name,reverse=True)
    used=0
    for i,p in enumerate(rows):
        used+=p.stat().st_size
        if i>=keep or (i>0 and used>max_bytes):
            p.unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--backup',action='store_true')
    mode.add_argument('--live',action='store_true')
    mode.add_argument('--replay',type=Path,help='Re-evaluate this tool\'s exported cohort, offline')
    parser.add_argument('--project',type=Path)
    parser.add_argument('--hours',type=int,choices=range(1,25),default=2)
    parser.add_argument('--engine',choices=['0.2.9'],default='0.2.9')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--scheduled',action='store_true')
    args=parser.parse_args()
    if args.scheduled and (not args.live or args.output):
        parser.error('--scheduled requires --live and uses its own report directory')
    if not args.scheduled and not args.output:
        parser.error('--output is required for a manual report')
    os.umask(0o077)
    lock_path=Path('/run/solana-radar-research.lock') if os.geteuid()==0 else Path(tempfile.gettempdir())/f'radar-research-{os.getuid()}.lock'
    with open(lock_path,'w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another research capture is running; retry later')
        try:
            if args.replay:
                with gzip.open(args.replay,'rt') as f:
                    raw=f.read(OUTPUT_CAP+1)
                if len(raw)>OUTPUT_CAP:raise RuntimeError('Replay input too large')
                report=json.loads(raw)
                if report.get('format') not in ('radar-research-tools-1.0.0','radar-research-tools-1.0.1',VERSION) or not report.get('completeCohortWithinWindow'):
                    raise RuntimeError('Replay requires a complete cohort export from this tool')
            elif args.backup:
                path,cutoff=completed_backup()
                report=capture(path,args.hours,args.engine,cutoff=cutoff)
                report['source']['snapshotAgeHours']=round((time.time()*1000-cutoff)/3600000,2)
            else:
                project=args.project
                if not project:
                    project=Path(json.loads(Path('/etc/solana-radar-research.json').read_text())['project'])
                report=capture(live_database(project),args.hours,args.engine,live=True)
            report['evaluation']=evaluate(report['entries'],report['cutoffMs'])
            if not args.replay:
                reg_path=REPORT_ROOT/'shadow-registration-v1.json'
                report['shadowRegistration']=json.loads(reg_path.read_text()) if reg_path.exists() else None
            report['analysis']=analyze(report)
            report['processedBy']=VERSION
            destination=args.output
            if args.scheduled:
                REPORT_ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
                destination=REPORT_ROOT/('research-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json.gz')
            publish(report,destination)
            message=summary_text(report)
            if args.scheduled:
                atomic_write(REPORT_ROOT/'latest-summary.txt',message.encode())
                atomic_write(REPORT_ROOT/'last-run.json',json.dumps({'success':True,'finishedAt':iso(int(time.time()*1000)),
                    'report':str(destination),'cutoff':report['window']['end'],'source':report['source']}).encode())
                prune_reports(REPORT_ROOT)
            print(message,end='')
            print('Report saved:',destination)
        except Exception as e:
            if args.scheduled:
                # Errors are deliberately sanitized: subprocess stderr may contain environment-specific data.
                atomic_write(REPORT_ROOT/'last-run.json',json.dumps({'success':False,'at':iso(int(time.time()*1000)),
                    'errorType':type(e).__name__,'message':str(e) if not isinstance(e,subprocess.CalledProcessError) else 'Docker inspection failed'}).encode())
            raise


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Research stopped:',str(exc) if not isinstance(exc,subprocess.CalledProcessError) else 'Docker inspection failed',file=sys.stderr)
        sys.exit(1)
