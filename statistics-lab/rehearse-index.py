#!/usr/bin/env python3
"""Rehearse the identity index on a disposable copy of a completed local backup."""
import argparse
from contextlib import closing
import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

BACKUPS=Path('/var/backups/solana-radar')
MAX_BYTES=16*1024**3
STAGE_SECONDS=120
OUTER_SECONDS=540
TABLES=('candidates','events','outbox','kv')
spec=importlib.util.spec_from_file_location('source_index',Path(__file__).with_name('source-index.py'))
index=importlib.util.module_from_spec(spec);spec.loader.exec_module(index)

class Refused(Exception):pass

def stamp(file):
    s=file.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or file.resolve(strict=True)!=file:
        raise Refused('backup-path-refused')
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)

def select_backup(root, now=None):
    if root.resolve(strict=True)!=root:raise Refused('backup-path-refused')
    status=root/'last-run.json';signature=stamp(status)
    if signature[2]>65536:raise Refused('backup-status-size')
    obj=json.loads(status.read_bytes())
    if not isinstance(obj,dict):raise Refused('backup-status-invalid')
    if stamp(status)!=signature:raise Refused('backup-status-changed')
    if obj.get('success') is not True or obj.get('state')!='complete' or obj.get('method')!='host-snapshot-v1':
        raise Refused('completed-local-backup-required')
    finished=datetime.datetime.fromisoformat(obj['finished_at'].replace('Z','+00:00'))
    if finished.tzinfo is None:raise Refused('backup-date-invalid')
    now=now or datetime.datetime.now(datetime.timezone.utc)
    age=(now-finished).total_seconds()
    if not 0<=age<=36*3600:raise Refused('recent-local-backup-required')
    file=Path(obj['backup'])
    if file.parent!=root or not re.fullmatch(r'auto-\d{8}T\d{6}Z-[0-9a-f]{8}\.sqlite',file.name):raise Refused('backup-path-refused')
    original=stamp(file)
    if type(obj.get('bytes')) is not int or not 0<original[2]==obj['bytes']<=MAX_BYTES:raise Refused('backup-size-mismatch')
    if any(Path(str(file)+s).exists() or Path(str(file)+s).is_symlink() for s in ('-wal','-shm','-journal')):raise Refused('standalone-backup-required')
    counts=obj.get('counts')
    if not isinstance(counts,dict) or any(type(counts.get(t)) is not int or counts[t]<0 for t in TABLES):raise Refused('backup-counts-invalid')
    return file,original,{t:counts[t] for t in TABLES},age

def bounded_copy(source,destination,signature,clock=time.monotonic):
    started=clock();copied=0
    fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as src, destination.open('xb') as dst:
        os.chmod(destination,0o600)
        s=os.fstat(src.fileno())
        if (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)!=signature:raise Refused('backup-changed')
        while chunk:=src.read(1024*1024):
            if clock()-started>STAGE_SECONDS:raise Refused('copy-timeout')
            copied+=len(chunk)
            if copied>signature[2]:raise Refused('backup-changed')
            dst.write(chunk)
        dst.flush();os.fsync(dst.fileno())
    if copied!=signature[2] or stamp(source)!=signature:raise Refused('backup-changed')
    return copied

def verify(file, expected, clock=time.monotonic):
    started=clock()
    with closing(sqlite3.connect(file.as_uri()+'?mode=ro',uri=True,timeout=0.25)) as db:
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-4096');db.execute('PRAGMA mmap_size=0')
        db.set_progress_handler(lambda:int(clock()-started>STAGE_SECONDS),1000)
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:raise Refused('copy-integrity-failed')
        actual={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in TABLES}
        if actual!=expected:raise Refused('copy-counts-mismatch')
        index.check_schema(db)
    return actual

def advise_copy_cache(file):
    # Advisory eviction for this private copy only; never global cache controls.
    if not hasattr(os,'posix_fadvise'):return False
    try:
        with file.open('rb') as f:os.posix_fadvise(f.fileno(),0,0,os.POSIX_FADV_DONTNEED)
        return True
    except OSError:return False

def run_copy(root, directory, *, clock=time.monotonic, emit=None, free_bytes=None):
    started=clock();report={'format':'statistics-index-rehearsal-1','capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'state':'running','phase':'select-backup','error':None,'liveDatabaseOpened':False,'scannerStopped':False,
        'modelEvaluated':False,'networkRequests':0,'timingsMs':{},'copyCacheEvictionAdvisory':False}
    original=None;source=None
    def publish(phase):
        report['phase']=phase;report['elapsedMs']=round((clock()-started)*1000,3)
        if emit:emit(report)
    def stage(name,fn):
        publish(name);before=clock()
        try:return fn()
        finally:report['timingsMs'][name]=round((clock()-before)*1000,3)
    try:
        source,original,counts,age=select_backup(root)
        report.update(backupBytes=original[2],backupAgeSeconds=round(age))
        free=free_bytes() if free_bytes else shutil.disk_usage(directory).free
        if free<2*original[2]+1024**3:raise Refused('rehearsal-disk-reserve-required')
        copy=directory/'copy.sqlite'
        stage('copy-backup',lambda:bounded_copy(source,copy,original,clock))
        stage('verify-before',lambda:verify(copy,counts,clock))
        with closing(sqlite3.connect(copy)) as db:db.execute('PRAGMA journal_mode=WAL')
        report['copyCacheEvictionAdvisory']=advise_copy_cache(copy)
        report['installation']=stage('build-copy-index',lambda:index.run_index(copy,True,deadline_seconds=180))
        if report['installation']['state'] not in ('index-installed','already-present'):raise Refused('copy-index-not-installed')
        report['verifiedCounts']=stage('verify-after',lambda:verify(copy,counts,clock))
        report['state']='completed'
    except (Refused,index.Refused) as e:report['state']='stopped';report['error']=str(e)
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):report['state']='stopped';report['error']='rehearsal-step-failed'
    finally:
        if source is not None and original is not None:
            try:report['backupMetadataUnchanged']=stamp(source)==original
            except (OSError,Refused):report['backupMetadataUnchanged']=False
            if not report['backupMetadataUnchanged']:report.update(state='stopped',error='backup-changed')
        publish(report['phase'])
    return report

def write_status(file,report):
    temp=file.with_suffix('.tmp');temp.write_text(json.dumps(report));os.chmod(temp,0o600);os.replace(temp,file)

def orchestrate(*, runner=subprocess.run):
    report={'format':'statistics-index-rehearsal-1','state':'stopped','error':'rehearsal-launcher-failed',
        'liveDatabaseOpened':False,'scannerStopped':False,'modelEvaluated':False,'networkRequests':0}
    with tempfile.TemporaryDirectory(prefix='radar-index-rehearsal-',dir='/var/tmp') as name:
        directory=Path(name);os.chmod(directory,0o700);status=directory/'status.json'
        try:
            runner([sys.executable,'-E','-s',str(Path(__file__).resolve()),'--worker',str(directory)],
                   stdout=subprocess.DEVNULL,timeout=OUTER_SECONDS,check=True)
            if not status.is_file() or status.stat().st_size>65536:raise Refused('worker-report-invalid')
            completed=json.loads(status.read_text())
            if not isinstance(completed,dict) or completed.get('format')!='statistics-index-rehearsal-1':raise Refused('worker-report-invalid')
            report=completed
        except (subprocess.SubprocessError,OSError,ValueError,Refused):
            if status.is_file() and status.stat().st_size<=65536:
                try:
                    partial=json.loads(status.read_text())
                    if isinstance(partial,dict) and partial.get('format')=='statistics-index-rehearsal-1':report=partial
                except ValueError:pass
            report.update(state='stopped',error='rehearsal-worker-stopped')
    report['temporaryCopyRemoved']=True
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker',type=Path,help=argparse.SUPPRESS);a=p.parse_args()
    os.umask(0o077)
    if os.geteuid()!=0:p.error('Use sudo to read the completed local backup.')
    if a.worker:
        directory=a.worker
        if directory.resolve(strict=True)!=directory or not directory.is_dir() or directory.parent!=Path('/var/tmp') or not directory.name.startswith('radar-index-rehearsal-'):raise Refused('worker-directory-refused')
        s=directory.stat()
        if s.st_uid!=0 or s.st_mode&0o077:raise Refused('worker-directory-refused')
        os.nice(10)
        previous=None
        def emit(report):
            nonlocal previous
            write_status(directory/'status.json',report)
            if report['phase']!=previous:print('Rehearsal: '+report['phase'],file=sys.stderr,flush=True);previous=report['phase']
        run_copy(BACKUPS,directory,emit=emit)
        return 0
    report=orchestrate();print(json.dumps(report,indent=2));return 0 if report['state']=='completed' else 1

if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,ValueError,Refused):
        print(json.dumps({'format':'statistics-index-rehearsal-1','state':'stopped','error':'rehearsal-launcher-failed','liveDatabaseOpened':False,'scannerStopped':False,'networkRequests':0}))
        sys.exit(1)
