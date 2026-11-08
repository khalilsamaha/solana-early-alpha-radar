#!/usr/bin/env python3
"""Bounded SQLite ledger snapshot, isolated restore verification, optional B2 round trip."""
import argparse, contextlib, datetime, fcntl, gzip, hashlib, json, os, re, shutil, signal, sqlite3, subprocess, tempfile, time
from pathlib import Path

VERSION='quote-ledger-backup-1'
REMOTE='radar-b2:solana-radar-backups-redeye-2026/quote-ledger/'
TABLES={'meta':'k','signals':'seq','probes':'seq','incidents':'at,kind,detail'}
MAX_BYTES=512*1024*1024

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def atomic_json(path,obj):
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.status-')
    try:
        with os.fdopen(fd,'w') as f:json.dump(obj,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,path)
    finally:Path(tmp).unlink(missing_ok=True)

@contextlib.contextmanager
def deadline(seconds):
    def expired(*_):raise TimeoutError('Backup operation exceeded its time budget')
    previous=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,seconds)
    try:yield
    finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

def logical_summary(path):
    with contextlib.closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as db, db:
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-4096')
        end=time.monotonic()+45;db.set_progress_handler(lambda:int(time.monotonic()>end),1000)
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:raise ValueError('SQLite integrity failed')
        counts={};hashes={}
        for table,order in TABLES.items():
            h=hashlib.sha256();n=0
            for row in db.execute(f'SELECT * FROM {table} ORDER BY {order}'):
                raw=json.dumps(row,separators=(',',':'),ensure_ascii=True).encode()
                if len(raw)>2*1024*1024:raise ValueError('Oversized ledger record')
                h.update(raw);h.update(b'\n');n+=1
            counts[table]=n;hashes[table]=h.hexdigest()
        meta={}
        for key in ['sourceIdentity','cursor','samplingRegistration','previousSamplingRegistration','featureCaptureRegistration','registeredAt','version']:
            row=db.execute('SELECT v FROM meta WHERE k=?',(key,)).fetchone()
            if row:
                if len(row[0])>65536:raise ValueError('Oversized ledger metadata')
                meta[key]=json.loads(row[0])
        if not meta.get('sourceIdentity') or not isinstance(meta.get('cursor'),dict):raise ValueError('Missing source identity or cursor')
        return {'counts':counts,'tableHashes':hashes,'metadata':meta}

def snapshot(source,target):
    source=source.resolve(strict=True)
    if source.stat().st_size>MAX_BYTES:raise ValueError('Ledger exceeds 512 MiB backup budget')
    identity=(source.stat().st_dev,source.stat().st_ino)
    wal=Path(str(source)+'-wal');start_wal=wal.stat().st_size if wal.exists() else 0;end=time.monotonic()+45
    def guard(*_):
        if time.monotonic()>end:raise TimeoutError('SQLite snapshot deadline')
        if wal.exists() and wal.stat().st_size-start_wal>64*1024*1024:raise ValueError('WAL growth budget exceeded')
        if target.exists() and target.stat().st_size>MAX_BYTES:raise ValueError('Snapshot size budget exceeded')
    with contextlib.closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=1)) as src, \
         contextlib.closing(sqlite3.connect(target)) as dst, src, dst:
        src.execute('PRAGMA query_only=ON');src.execute('PRAGMA cache_size=-4096')
        # Pin one read snapshot; ongoing writes cannot repeatedly restart the copy.
        src.execute('BEGIN');src.execute('SELECT count(*) FROM meta').fetchone()
        src.backup(dst,pages=256,progress=guard,sleep=0.01);guard();src.rollback()
    if identity!=(source.stat().st_dev,source.stat().st_ino):raise ValueError('Source replaced during snapshot')
    os.chmod(target,0o600)

def verify_archive(archive,manifest):
    if manifest.get('format')!=VERSION or sha(archive)!=manifest.get('sha256'):raise ValueError('Archive checksum or format mismatch')
    with tempfile.TemporaryDirectory(prefix='radar-quote-restore-') as d:
        restored=Path(d)/'restored.sqlite';size=0
        with gzip.open(archive,'rb') as src, open(restored,'xb') as dst:
            while chunk:=src.read(1024*1024):
                size+=len(chunk)
                if size>MAX_BYTES:raise ValueError('Restored size budget exceeded')
                dst.write(chunk)
        summary=logical_summary(restored)
        if size!=manifest['databaseBytes'] or summary!=manifest['ledger']:raise ValueError('Restored ledger evidence differs')
    return summary

def rclone(args):
    return subprocess.run(['/usr/local/bin/rclone','--config','/etc/solana-radar/rclone.conf',
        '--transfers','1','--checkers','1','--buffer-size','1Mi','--b2-chunk-size','8Mi','--b2-upload-concurrency','1',
        '--retries','1','--low-level-retries','1','--contimeout','10s','--timeout','45s','--max-transfer','513Mi',*args],
        check=True,capture_output=True,timeout=90)

def backup(source,output,cloud=False):
    os.umask(0o077);output.mkdir(parents=True,exist_ok=True,mode=0o700)
    if output.is_symlink():raise ValueError('Symlink output refused')
    os.chmod(output,0o700)
    with open(output/'.backup.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        status={'format':VERSION,'startedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'success':False,'state':'running'}
        atomic_json(output/'last-run.json',status)
        try:
            with deadline(240),tempfile.TemporaryDirectory(dir=output,prefix='.quote-snapshot-') as d:
                temp=Path(d);copy=temp/'snapshot.sqlite';snapshot(source,copy)
                name='quote-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+os.urandom(4).hex()+'.sqlite.gz'
                archive=temp/name
                with open(copy,'rb') as src,gzip.open(archive,'wb',compresslevel=6) as dst:shutil.copyfileobj(src,dst,1024*1024)
                manifest={'format':VERSION,'archive':name,'sha256':sha(archive),'databaseBytes':copy.stat().st_size,
                    'archiveBytes':archive.stat().st_size,'ledger':logical_summary(copy),'snapshotCompletedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'restoreScope':'isolated SQLite integrity, all table contents, identity, cursor and registrations; observer never started'}
                verify_archive(archive,manifest)
                saved=output/name;os.replace(archive,saved);atomic_json(output/(name+'.json'),manifest)
                status.update(localVerified=True,archive=str(saved),counts=manifest['ledger']['counts'],cloudVerified=False)
                if cloud:
                    remote=REMOTE+name;rclone(['copyto',str(saved),remote]);download=temp/'download.sqlite.gz'
                    rclone(['copyto',remote,str(download)]);verify_archive(download,manifest)
                    # Publish the manifest only after the archive round trip succeeds; verify it too.
                    rclone(['copyto',str(output/(name+'.json')),remote+'.json'])
                    remote_manifest=temp/'remote.json';rclone(['copyto',remote+'.json',str(remote_manifest)])
                    if json.loads(remote_manifest.read_text())!=manifest:raise ValueError('Cloud manifest differs')
                    status.update(cloudVerified=True,remote=remote)
                status.update(success=True,state='complete',finishedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
                atomic_json(output/'last-run.json',status)
                # Local retention only, after required verification succeeds. Exact owned names only.
                archives=sorted(p for p in output.iterdir() if re.fullmatch(r'quote-\d{8}T\d{6}Z-[0-9a-f]{8}\.sqlite\.gz',p.name) and not p.is_symlink())
                for old in archives[:-14]:
                    old.unlink();old.with_name(old.name+'.json').unlink(missing_ok=True)
                return status
        except Exception as error:
            status.update(state='failed',success=False,errorType=type(error).__name__,finishedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())
            atomic_json(output/'last-run.json',status)
            raise RuntimeError('Quote backup failed; see last-run.json (credentials and raw provider errors withheld)') from None

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,default=Path('/etc/solana-radar-quotes.json'))
    p.add_argument('--output',type=Path,default=Path('/var/backups/solana-radar-quotes'));p.add_argument('--cloud',action='store_true')
    p.add_argument('--verify',type=Path);a=p.parse_args()
    if a.verify:
        with deadline(60):result=verify_archive(a.verify,json.loads(a.verify.with_name(a.verify.name+'.json').read_text()))
        print(json.dumps({'restoreVerified':True,'counts':result['counts']},indent=2));return
    config=json.loads(a.config.read_text());source=Path(config['reports'])/'observer.sqlite'
    if source.is_symlink():raise ValueError('Symlink source refused')
    print(json.dumps(backup(source,a.output,a.cloud),indent=2))
if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit(str(e))
