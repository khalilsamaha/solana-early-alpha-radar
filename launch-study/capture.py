"""Bounded, pinned read-only capture. Never reads current candidates or snapshots."""
import hashlib, json, signal, sqlite3, time
from pathlib import Path

ENTRY_KINDS=('fast-shadow-entries','research-entries')
ENTRY_KEYS=('id','at','mint','cohort','version','priceUsd','pairAddress','liquidityUsd')
OUTCOME_KEYS=('id','entryId','mint','cohort','at','entryAt','dueAt','horizon','status','coverage','sampleAt','priceUsd','returnPct','pairAddress','reasonCode')


def project_entry(row):
    value={k:row[k] for k in ENTRY_KEYS if k in row}
    if isinstance(row.get('candidate'),dict):value['candidate']={k:row['candidate'][k] for k in ('mint','pairAddress','priceUsd','liquidityUsd') if k in row['candidate']}
    if isinstance(row.get('followup'),dict):value['followup']={k:row['followup'][k] for k in ('policy','admitted') if k in row['followup']}
    return value


def project_outcome(row):
    value={k:row[k] for k in OUTCOME_KEYS if k in row}
    if isinstance(row.get('evidence'),dict):value['entryPool']=row['evidence'].get('entryPool')
    return value


def capture(path,hours=6,budget=10,max_entries=6000,now=None):
    if type(hours) is not int or not 1<=hours<=24:raise ValueError('hours must be 1..24')
    path=Path(path).resolve(strict=True);identity=path.stat();now=int(time.time()*1000) if now is None else now
    start=time.monotonic();end=start+budget;wal=Path(str(path)+'-wal');wal_start=wal.stat().st_size if wal.exists() else 0
    raw_bytes=0;launch_count=0;source_hash=hashlib.sha256();db=None
    def guard():
        if time.monotonic()>end:raise TimeoutError('Read budget exceeded; narrow --hours')
        if wal.exists() and wal.stat().st_size-wal_start>64*1024*1024:raise ValueError('WAL growth budget exceeded')
    def parse(raw,size,limit):
        nonlocal raw_bytes
        guard();raw_bytes+=size or 0
        if not isinstance(size,int) or size>limit or raw_bytes>128*1024*1024 or raw is None:raise ValueError('Record/read byte cap reached; no partial report')
        source_hash.update(raw.encode());source_hash.update(b'\n');row=json.loads(raw)
        if not isinstance(row,dict):raise ValueError('Malformed source record')
        return row
    def alarm(*_):raise TimeoutError('Read deadline exceeded')
    previous=signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,budget+1)
    try:
        db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1)
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-4096');db.execute('PRAGMA mmap_size=0')
        db.set_progress_handler(lambda:int(time.monotonic()>end),1000);db.execute('BEGIN')
        regrow=db.execute("SELECT CASE WHEN length(CAST(data AS BLOB))<=4096 THEN data END,length(CAST(data AS BLOB)) FROM kv WHERE key='launch-registry-registration'").fetchone()
        if not regrow:raise ValueError('No launch registration yet; wait for a creation event')
        registration=parse(*regrow,4096)
        if registration.get('version')!='launch-registry-1' or type(registration.get('registeredAt')) is not int or not 0<registration['registeredAt']<=now:raise ValueError('Invalid launch registration')
        lower=max(now-hours*3600000,registration['registeredAt']);entries=[];outcomes=[];launches=[];contexts=[]
        for kind in ENTRY_KINDS:
            sql='SELECT seq,id,at,CASE WHEN length(CAST(data AS BLOB))<=262144 THEN data END,length(CAST(data AS BLOB)) FROM events INDEXED BY events_at WHERE kind=? AND at>=? AND at<=? ORDER BY at,seq LIMIT ?'
            for seq,key,at,raw,size in db.execute(sql,(kind,lower,now,max_entries+1)):
                if len(entries)>=max_entries:raise ValueError('Entry cap reached; narrow --hours')
                entries.append({'seq':seq,'kind':kind,'eventId':key,'eventAt':at,'data':project_entry(parse(raw,size,262144))})
        entries.sort(key=lambda r:(r['eventAt'],r['seq']))
        mints={r['data'].get('mint') for r in entries if isinstance(r['data'].get('mint'),str)}
        for mint in sorted(mints):
            guard();row=db.execute('SELECT received_at,CASE WHEN length(CAST(data AS BLOB))<=4096 THEN data END,length(CAST(data AS BLOB)) FROM launch_registry WHERE mint=?',(mint,)).fetchone()
            if row:
                at,raw,size=row;item=parse(raw,size,4096)
                if item.get('mint')!=mint or item.get('receivedAt')!=at:raise ValueError('Launch table identity mismatch')
                launches.append(item)
        actors={l.get('fields',{}).get('traderReported') for l in launches};actors.discard(None)
        hashes={l.get('fields',{}).get('metadataUriSha256') for l in launches};hashes.discard(None)
        # One stream of all retained launch rows, keeping only minimal context for selected actors/hashes.
        # Query spans the earliest entry's 24h lookback and current window, not a current-candidate snapshot.
        context_start=lower-86400000
        sql='SELECT mint,received_at,CASE WHEN length(CAST(data AS BLOB))<=4096 THEN data END,length(CAST(data AS BLOB)) FROM launch_registry WHERE received_at>=? AND received_at<=? ORDER BY received_at,mint LIMIT 100001'
        earliest=db.execute('SELECT min(received_at) FROM launch_registry').fetchone()[0]
        for mint,at,raw,size in db.execute(sql,(context_start,now)):
            launch_count+=1
            if launch_count>100000:raise ValueError('Registry row cap reached')
            row=parse(raw,size,4096)
            if row.get('mint')!=mint or row.get('receivedAt')!=at or row.get('availableAt')!=at or row.get('version')!='launch-registry-1':raise ValueError('Invalid registry context')
            f=row.get('fields',{})
            if f.get('traderReported') in actors or f.get('metadataUriSha256') in hashes:
                contexts.append({'mint':mint,'availableAt':at,'traderReported':f.get('traderReported'),'metadataUriSha256':f.get('metadataUriSha256')})
        for entry in entries:
            kind='fast-shadow-outcomes' if entry['kind']=='fast-shadow-entries' else 'research-outcomes'
            hs=('30s','60s','120s','300s') if kind=='fast-shadow-outcomes' else ('30s','1m','2m','5m')
            ids=[str(entry['eventId'])+':'+h for h in hs]
            sql='SELECT seq,id,at,CASE WHEN length(CAST(data AS BLOB))<=262144 THEN data END,length(CAST(data AS BLOB)) FROM events WHERE kind=? AND id IN (?,?,?,?) AND at<=? ORDER BY seq'
            for seq,key,at,raw,size in db.execute(sql,(kind,*ids,now)):
                outcomes.append({'seq':seq,'kind':kind,'eventId':key,'eventAt':at,'data':project_outcome(parse(raw,size,262144))})
        hrow=db.execute("SELECT CASE WHEN length(CAST(data AS BLOB))<=65536 THEN data END,length(CAST(data AS BLOB)) FROM kv WHERE key='health'").fetchone()
        health=parse(*hrow,65536) if hrow else {}
        health_summary={'snapshotAt':None,'readAt':now,'timestampState':'not-stored-by-scanner',
            'lastMarketAt':health.get('lastMarketAt'),'lastLoopAt':health.get('lastLoopAt'),'launchRegistry':health.get('launchRegistry')}
        guard()
    finally:
        if db:db.close()
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    current=path.stat()
    if (current.st_dev,current.st_ino)!=(identity.st_dev,identity.st_ino):raise ValueError('Scanner source replaced during capture')
    return {'format':'launch-study-capture-1','sourceIdentity':f'{identity.st_dev}:{identity.st_ino}',
        'cutoffAt':now,'requestedWindowStartAt':now-hours*3600000,'windowStartAt':lower,'registration':registration,
        'earliestRetainedReceiptAt':earliest,'contextWindowStartAt':context_start,'contextRowsScanned':launch_count,
        'entries':entries,'outcomes':outcomes,'matchedMintLaunchRecords':launches,'relatedLaunchContext':contexts,
        'healthSnapshot':health_summary,'rawReadBytes':raw_bytes,'sourceReadSha256':source_hash.hexdigest(),
        'readSeconds':round(time.monotonic()-start,3)}
