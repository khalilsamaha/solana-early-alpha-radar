#!/usr/bin/env python3
"""Read-only launch feature availability, with explicit bounded coverage."""
import argparse, collections, datetime, json, os, sqlite3, subprocess, time
from contextlib import closing
from pathlib import Path
FIELDS=['signature','creatorReported','traderReported','bondingCurveKey','slotReported','decimalsReported','initialBuyReported','solAmountReported','virtualSolReservesReported','virtualTokenReservesReported','marketCapSolReported','metadataUriSha256']

def database(project):
    def run(args):return subprocess.run(args,cwd=project,check=True,text=True,capture_output=True,timeout=10).stdout.strip()
    cid=run(['docker','compose','ps','-q','radar'])
    if not cid or '\n' in cid:raise ValueError('Expected one running radar container')
    obj=json.loads(run(['docker','inspect',cid]))[0]
    mounts=[m for m in obj['Mounts'] if m['Destination']=='/app/data']
    if not obj['State']['Running'] or len(mounts)!=1:raise ValueError('Running scanner data mount unavailable')
    return Path(mounts[0]['Source'])/'radar.sqlite'

def audit(file,hours=24):
    file=file.resolve(strict=True);started=time.monotonic();end=started+10;now=int(time.time()*1000)
    identity=(file.stat().st_dev,file.stat().st_ino);counts=collections.Counter();actors=collections.Counter();traders=collections.Counter();n=0;first=None;last=None;conflict=0;total_bytes=0
    wal=Path(str(file)+'-wal');wal_size=wal.stat().st_size if wal.exists() else 0
    def guard():
        if time.monotonic()>end:raise TimeoutError('Read deadline exceeded')
        if wal.exists() and wal.stat().st_size-wal_size>64*1024*1024:raise ValueError('WAL growth limit reached')
    with closing(sqlite3.connect(file.as_uri()+'?mode=ro',uri=True,timeout=1)) as db, db:
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-4096');db.execute('PRAGMA mmap_size=0')
        db.set_progress_handler(lambda:int(time.monotonic()>end),1000);db.execute('BEGIN')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='launch_registry'").fetchone():raise ValueError('Launch registry not installed')
        registration=db.execute("SELECT data FROM kv WHERE key='launch-registry-registration'").fetchone()
        health=db.execute("SELECT data FROM kv WHERE key='health'").fetchone()
        retained=db.execute('SELECT count(*) FROM launch_registry').fetchone()[0]
        for at,raw,size in db.execute('SELECT received_at,CASE WHEN length(CAST(data AS BLOB))<=4096 THEN data END,length(CAST(data AS BLOB)) FROM launch_registry WHERE received_at>=? AND received_at<=? ORDER BY received_at LIMIT 100001',(now-hours*3600000,now)):
            guard();n+=1;total_bytes+=size
            if n>100000 or size>4096 or total_bytes>128*1024*1024:raise ValueError('Launch audit cap reached; no partial report')
            row=json.loads(raw)
            if row.get('version')!='launch-registry-1' or row.get('receivedAt')!=at or row.get('availableAt')!=at:raise ValueError('Invalid launch record')
            fields=row['fields'];first=at if first is None else first;last=at
            counts.update(f for f in FIELDS if fields.get(f) is not None)
            # Creator role is explicit; do not silently substitute a migration actor or trader.
            actor=fields.get('creatorReported')
            if actor:actors[actor]+=1
            if fields.get('traderReported'):traders[fields['traderReported']]+=1
            conflict+=bool(actor and fields.get('traderReported') and actor!=fields['traderReported'])
        guard()
        state=json.loads(health[0]) if health else {}
    if identity!=(file.stat().st_dev,file.stat().st_ino):raise ValueError('Source changed during capture')
    return {'format':'launch-feature-audit-2','capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'sourceIdentity':f'{identity[0]}:{identity[1]}','windowHours':hours,'registration':json.loads(registration[0]) if registration else None,
        'retainedTotal':retained,'receivedCreationsInWindow':n,'firstReceiptAt':first,'lastReceiptAt':last,
        'availability':{f:{'present':counts[f],'unknown':n-counts[f]} for f in FIELDS},
        'creatorRoleConflicts':conflict,'distinctReportedCreators':len(actors),'reportedCreatorsWithMultipleCreationsInWindow':sum(c>1 for c in actors.values()),
        'distinctReportedTraders':len(traders),'reportedTradersWithMultipleCreationsInWindow':sum(c>1 for c in traders.values()),
        'scannerHealthSnapshot':{'snapshotAt':None,'readAt':now,'timestampState':'not-stored-by-scanner',
            'lastMarketAt':state.get('lastMarketAt'),'lastLoopAt':state.get('lastLoopAt'),'launchRegistry':state.get('launchRegistry')},
        'readSeconds':round(time.monotonic()-started,3),
        'limitations':['Received creation events only; not all launches or the active candidate queue.',
            'No historical backfill, performance outcomes, creator verification or trading eligibility changes.',
            'Receipt timestamps are availability timestamps, not on-chain creation times.',
            'URI hash is equality evidence only; content is neither fetched nor authenticated.',
            'Thirty-day retention and a hard row cap bound stored evidence; health counters reset at restart.',
            'Creator/trader repetition is descriptive within this retained window; not a prior-history feature or a risk verdict.']}

RETENTION_SQL='''SELECT count(*),min(received_at),max(received_at),
    sum(CASE WHEN received_at<? THEN 1 ELSE 0 END),
    sum(CASE WHEN received_at>=? AND received_at<=? THEN 1 ELSE 0 END),
    min(CASE WHEN received_at>=? AND received_at<=? THEN received_at END),
    max(CASE WHEN received_at>=? AND received_at<=? THEN received_at END),
    sum(CASE WHEN typeof(received_at)!='integer' OR received_at<=0 OR received_at>? THEN 1 ELSE 0 END)
    FROM (SELECT received_at FROM launch_registry INDEXED BY launch_registry_received
          ORDER BY received_at LIMIT 100001)'''

def retention_audit(file,hours=720):
    """Receipt-index inventory only; never read or validate launch payloads."""
    if type(hours) is not int or not 1<=hours<=720:raise ValueError('Hours must be 1..720')
    file=file.resolve(strict=True);started=time.monotonic();end=started+10;now=int(time.time()*1000)
    start=now-hours*3600000;identity=(file.stat().st_dev,file.stat().st_ino)
    wal=Path(str(file)+'-wal');wal_size=wal.stat().st_size if wal.exists() else 0
    def guard():
        if time.monotonic()>end:raise TimeoutError('Read deadline exceeded')
        if wal.exists() and wal.stat().st_size-wal_size>64*1024*1024:raise ValueError('WAL growth limit reached')
    with closing(sqlite3.connect(file.as_uri()+'?mode=ro',uri=True,timeout=1)) as db, db:
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-4096');db.execute('PRAGMA mmap_size=0')
        db.set_progress_handler(lambda:int(time.monotonic()>end),1000);db.execute('BEGIN')
        guard()
        if [r[2] for r in db.execute("PRAGMA index_info('launch_registry_received')")]!=['received_at']:
            raise ValueError('Receipt index missing or incompatible')
        total,first,last,older,within,window_first,window_last,invalid=db.execute(
            RETENTION_SQL,(start,start,now,start,now,start,now,now)).fetchone()
        guard()
        if total>100000:raise ValueError('Launch audit cap reached; no partial report')
        if invalid:raise ValueError('Invalid or future receipt timestamp; no partial report')
    if identity!=(file.stat().st_dev,file.stat().st_ino):raise ValueError('Source changed during capture')
    guard()
    return {'format':'launch-retention-audit-1','capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'sourceIdentity':f'{identity[0]}:{identity[1]}','readAt':now,'windowHours':hours,'windowStartAt':start,
        'retainedTotal':total,'earliestRetainedReceiptAt':first,'latestRetainedReceiptAt':last,
        'rowsBeforeWindow':older or 0,'receivedCreationsInWindow':within or 0,
        'firstReceiptAt':window_first,'lastReceiptAt':window_last,
        'payloadsRead':False,'payloadsValidated':False,'featureAvailabilityEvaluated':False,
        'readSeconds':round(time.monotonic()-started,3),
        'limits':{'readSeconds':10,'maxRows':100000,'walGrowthBytes':64*1024*1024},
        'limitations':['Receipt-index inventory only; not a completed launch-feature audit.',
            'No launch payloads, actors, metadata, health counters or performance outcomes read.',
            'Rows before the requested window are not a deletion authorization.',
            'Receipt timestamps do not establish on-chain creation time or uninterrupted coverage.',
            'No database changes, historical backfill, preservation copy or restart performed.']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path);p.add_argument('--database',type=Path);p.add_argument('--hours',type=int,default=24)
    p.add_argument('--retention-only',action='store_true',help='Read receipt index only; do not evaluate launch fields');a=p.parse_args()
    if not 1<=a.hours<=720 or bool(a.project)==bool(a.database):p.error('Specify exactly one of --project/--database and hours 1..720')
    reader=retention_audit if a.retention_only else audit
    print(json.dumps(reader(a.database or database(a.project),a.hours),indent=2))
if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit('Launch audit stopped: '+str(e))
