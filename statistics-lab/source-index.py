#!/usr/bin/env python3
"""Inspect or explicitly install one bounded partial statistics identity index."""
import argparse
from contextlib import closing
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import time

NAME = 'events_statistics_identity'
KINDS = ('alerts', 'outcomes', 'research-entries', 'research-outcomes')
DDL = "CREATE INDEX events_statistics_identity ON events(kind,seq,id,at) WHERE kind IN ('alerts','outcomes','research-entries','research-outcomes')"
DEADLINE_SECONDS = 30
MAX_WAL_GROWTH = 64 * 1024 * 1024
MIN_FREE = 1024 * 1024 * 1024

class Refused(Exception):
    pass

def identity(file):
    s = file.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or file.resolve(strict=True) != file:
        raise Refused('source-path-refused')
    return s.st_dev, s.st_ino

def normalized(sql):
    return re.sub(r'\s+', '', sql or '').rstrip(';')

def check_schema(db):
    columns = [(r[1], r[2], r[3], r[5]) for r in db.execute('PRAGMA table_info(events)')]
    if columns != [('seq','INTEGER',0,1),('kind','TEXT',1,0),('id','TEXT',1,0),('at','INTEGER',1,0),('data','TEXT',1,0)]:
        raise Refused('source-schema-refused')
    indexes = {r[1]: r for r in db.execute('PRAGMA index_list(events)')}
    if 'events_kind_seq' not in indexes or [r[2] for r in db.execute('PRAGMA index_info(events_kind_seq)')] != ['kind','seq']:
        raise Refused('source-schema-refused')
    obj = db.execute('SELECT type,sql FROM sqlite_master WHERE name=?', (NAME,)).fetchone()
    if obj and (obj[0] != 'index' or normalized(obj[1]) != normalized(DDL)):
        raise Refused('source-index-mismatch')
    return bool(obj)

def run_index(file, apply=False, *, clock=time.monotonic, free_bytes=None, deadline_seconds=DEADLINE_SECONDS):
    """No arbitrary SQL, record edits, retries, index removal or checkpointing."""
    started = clock()
    report = {'format':'statistics-source-index-1', 'capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'state':'stopped', 'error':None, 'index':NAME, 'applied':False,
              'eventPayloadWrites':0, 'networkRequests':0, 'deadlineSeconds':deadline_seconds}
    db = None
    lock_started = None
    interrupted = None
    try:
        if deadline_seconds not in (DEADLINE_SECONDS,180):
            raise Refused('deadline-refused')
        before = identity(file)
        with closing(sqlite3.connect(file.as_uri()+'?mode=ro', uri=True, timeout=0.25)) as inspect:
            inspect.execute('PRAGMA query_only=ON')
            exists = check_schema(inspect)
            if inspect.execute('PRAGMA journal_mode').fetchone()[0] != 'wal':
                raise Refused('wal-required')
        if exists:
            report['state'] = 'already-present'
            return report
        if not apply:
            report['state'] = 'index-absent'
            return report
        if (free_bytes() if free_bytes else shutil.disk_usage(file.parent).free) < MIN_FREE:
            raise Refused('disk-reserve-required')
        # Root is required for Docker volume parents; ownership is repaired by the launcher.
        if os.geteuid() not in (0,file.stat().st_uid):
            raise Refused('database-owner-required')
        wal = Path(str(file)+'-wal')
        initial_wal = wal.stat().st_size if wal.exists() else 0
        def guard():
            nonlocal interrupted
            if clock()-started > deadline_seconds:
                interrupted = 'index-build-timeout'
            elif wal.exists() and wal.stat().st_size-initial_wal > MAX_WAL_GROWTH:
                interrupted = 'wal-growth-limit'
            return int(interrupted is not None)
        db = sqlite3.connect(file.as_uri()+'?mode=rw', uri=True, timeout=0.25, isolation_level=None)
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA cache_size=-4096')
        db.execute('PRAGMA mmap_size=0')
        db.execute('PRAGMA temp_store=FILE')
        db.execute('PRAGMA wal_autocheckpoint=0')
        db.set_progress_handler(guard, 1000)
        db.execute('BEGIN IMMEDIATE')
        lock_started = clock()
        if identity(file) != before:
            raise Refused('source-replaced')
        if check_schema(db):
            db.execute('ROLLBACK')
            report['state'] = 'already-present'
            return report
        counts = {k: db.execute('SELECT count(*) FROM events INDEXED BY events_kind_seq WHERE kind=?', (k,)).fetchone()[0] for k in KINDS}
        if any(n > 100000 for n in counts.values()):
            raise Refused('row-limit')
        report['indexedRows'] = sum(counts.values())
        if guard():
            raise Refused(interrupted)
        db.execute(DDL)
        if not check_schema(db) or identity(file) != before:
            raise Refused('source-replaced')
        if guard():
            raise Refused(interrupted)
        db.execute('COMMIT')
        report['applied'] = True
        report['state'] = 'index-installed'
        return report
    except Refused as e:
        report['error'] = str(e)
    except sqlite3.Error as e:
        report['error'] = interrupted or ('source-busy' if getattr(e, 'sqlite_errorcode', None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) else 'index-operation-failed')
    except OSError:
        report['error'] = 'source-unavailable'
    finally:
        if db is not None:
            db.set_progress_handler(None, 0)
            if db.in_transaction:
                db.execute('ROLLBACK')
            db.close()
        if lock_started is not None:
            report['writerLockMs'] = round((clock()-lock_started)*1000, 3)
        report['elapsedMs'] = round((clock()-started)*1000, 3)
    return report

def discover(project, runner=subprocess.run, *, with_container=False):
    def command(args):
        r = runner(args, cwd=project, capture_output=True, text=True, check=True, timeout=10)
        if len(r.stdout) > 1024*1024:
            raise Refused('docker-response-cap')
        return r.stdout.strip()
    if project.resolve(strict=True) != project or not project.is_dir():
        raise Refused('project-path-refused')
    cid = command(['docker','compose','ps','-q','radar'])
    if not re.fullmatch(r'[0-9a-f]{12,64}', cid):
        raise Refused('scanner-unavailable')
    info = json.loads(command(['docker','inspect',cid]))
    if len(info) != 1 or info[0].get('State',{}).get('Running') is not True:
        raise Refused('scanner-unavailable')
    mounts = [m for m in info[0].get('Mounts',[]) if m.get('Destination') == '/app/data' and m.get('RW') is True]
    if len(mounts) != 1:
        raise Refused('source-mount-refused')
    file = Path(mounts[0]['Source'])/'radar.sqlite'
    identity(file)
    return (file,cid) if with_container else file

def restore_sidecar_ownership(file, expected_identity):
    if identity(file)!=expected_identity:
        raise Refused('source-replaced')
    owner=file.stat()
    for suffix in ('-wal','-shm','-journal'):
        sidecar=Path(str(file)+suffix)
        try:fd=os.open(sidecar,os.O_RDONLY|os.O_NOFOLLOW)
        except FileNotFoundError:continue
        try:
            s=os.fstat(fd)
            if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1:
                raise Refused('sidecar-path-refused')
            if (s.st_uid,s.st_gid)!=(owner.st_uid,owner.st_gid):
                os.fchown(fd,owner.st_uid,owner.st_gid)
        finally:os.close(fd)

def worker(file, apply, runner=subprocess.run, *, extended=False):
    before=identity(file)
    command = [sys.executable,'-E','-s','-','--worker',str(file)] + (['--apply'] if apply else [])
    if extended and apply:command += ['--extended-maintenance']
    # Docker volume ancestors may be root-only. Never change directory permissions.
    try:
        child = runner(command, input=Path(__file__).read_bytes(), stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, timeout=210 if extended and apply else 45, user=0,
                       group=0, extra_groups=[])
    finally:
        restore_sidecar_ownership(file,before)
    if len(child.stdout)>16384:
        raise Refused('worker-response-cap')
    result = json.loads(child.stdout)
    if result.get('format') != 'statistics-source-index-1':
        raise Refused('worker-response-invalid')
    return result

def maintenance(file, cid, apply, *, runner=subprocess.run, run_worker=worker):
    result=run_worker(file,False)
    if not apply or result['state'] != 'index-absent':
        return result
    # Stop/start the exact existing container. No recreation, environment change or retry.
    # Always attempt restart, even if stop timed out or the worker failed.
    before=identity(file);started=time.monotonic();restart_ok=False
    try:
        runner(['docker','stop','--time','20',cid],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
        if identity(file)!=before:
            raise Refused('source-replaced')
        result=run_worker(file,True)
    except (Refused,OSError,ValueError,subprocess.SubprocessError):
        result={'format':'statistics-source-index-1','state':'stopped','error':'maintenance-step-failed',
                'networkRequests':0,'eventPayloadWrites':0,'indexState':'inspect-required'}
    finally:
        try:
            runner(['docker','start',cid],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
            r=runner(['docker','inspect','--format','{{.State.Running}}',cid],check=True,capture_output=True,text=True,timeout=10)
            restart_ok=r.stdout.strip()=='true'
        except (OSError,subprocess.SubprocessError):
            restart_ok=False
    result['maintenance']={'restartConfirmed':restart_ok,'elapsedMs':round((time.monotonic()-started)*1000,3),
                           'scope':'same-container-stop-start','readinessChecked':False}
    if not restart_ok:
        result['indexOperationState']=result['state']
        result['state']='stopped';result['error']='scanner-restart-unconfirmed'
    return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', type=Path)
    p.add_argument('--apply', action='store_true', help='Explicitly add the partial source index; may briefly block scanner writes.')
    p.add_argument('--maintenance', action='store_true', help='Permit a brief stop/start of the same scanner container for --apply.')
    p.add_argument('--extended-maintenance', action='store_true', help='After backup rehearsal, permit a 180-second index build with a 210-second worker limit.')
    p.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    a = p.parse_args()
    if a.extended_maintenance and (not a.apply or (not a.worker and not a.maintenance)):
        p.error('--extended-maintenance requires --apply --maintenance.')
    if a.worker:
        result = run_index(a.worker, a.apply, deadline_seconds=180 if a.extended_maintenance else DEADLINE_SECONDS)
    else:
        if os.geteuid() != 0 or not a.project:
            p.error('Use sudo and --project; inspection is the default. --apply permits the index write.')
        if a.apply and not a.maintenance:
            p.error('--apply requires --maintenance because the scanner write wait is shorter than the build deadline.')
        def interrupted(signum, frame):
            raise Refused('operator-interrupted')
        signal.signal(signal.SIGTERM,interrupted)
        signal.signal(signal.SIGINT,interrupted)
        fd=os.open('/run/lock/solana-radar-statistics-index.lock',os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            lock=os.fstat(fd)
            if not stat.S_ISREG(lock.st_mode) or lock.st_uid!=0 or lock.st_nlink!=1:
                raise Refused('maintenance-lock-refused')
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            file,cid = discover(a.project.absolute(), with_container=True)
            result = maintenance(file,cid,a.apply,run_worker=lambda f,apply:worker(f,apply,extended=a.extended_maintenance))
        finally:
            os.close(fd)
    print(json.dumps(result, indent=2))
    return 0 if result['state'] in ('already-present','index-installed','index-absent') else 1

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Refused, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print(json.dumps({'format':'statistics-source-index-1','state':'stopped','error':'index-launcher-failed',
                          'networkRequests':0,'eventPayloadWrites':0,'note':'No automatic retry. Inspect index state before another apply attempt.'}))
        sys.exit(1)
