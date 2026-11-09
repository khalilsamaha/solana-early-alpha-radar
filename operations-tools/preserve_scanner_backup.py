#!/usr/bin/env python3
"""Preserve an exact local scanner backup; never open the running database."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time

MAX_BYTES=8*1024**3
COPY_SECONDS=180
BLOCK=1024*1024

def fingerprint(info):
    return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)

def no_sidecars(path):
    if any(Path(str(path)+suffix).exists() or Path(str(path)+suffix).is_symlink()
           for suffix in ('-wal','-shm','-journal')):
        raise ValueError('Backup has SQLite sidecars; preserve and investigate')

def locate(directory,identity):
    directory=Path(directory).absolute()
    if directory.resolve(strict=True)!=directory:raise ValueError('Symlink backup directory refused')
    if not re.fullmatch(r'[0-9]+:[0-9]+',identity):raise ValueError('Invalid source identity')
    matches=[]
    with os.scandir(directory) as entries:
        for n,entry in enumerate(entries,1):
            if n>512:raise ValueError('Backup directory cap reached')
            if entry.name.endswith('.sqlite') and entry.is_file(follow_symlinks=False):
                s=entry.stat(follow_symlinks=False)
                if f'{s.st_dev}:{s.st_ino}'==identity:matches.append(Path(entry.path))
    if len(matches)!=1:raise ValueError('Expected exactly one backup with the reviewed identity')
    return matches[0]

def preserve(directory,identity,output):
    source=locate(directory,identity);initial=source.stat();no_sidecars(source)
    if not 0<initial.st_size<=MAX_BYTES:raise ValueError('Backup byte cap reached or empty source')
    if time.time()-initial.st_mtime<300:raise ValueError('Backup too recent or future dated')
    output=Path(output).absolute()
    if output.parent.resolve(strict=True)!=output.parent:raise ValueError('Symlink output parent refused')
    if shutil.disk_usage(output.parent).free<initial.st_size+256*1024**2:raise ValueError('Insufficient preservation space')
    # mkdir and exclusive file creation refuse replacement; failure leaves evidence.
    output.mkdir(mode=0o700)
    partial=output/'scanner.sqlite.incomplete';target=output/'scanner.sqlite'
    started=time.monotonic();end=started+COPY_SECONDS
    def guard():
        if time.monotonic()>end:raise TimeoutError('Preservation copy/verification deadline exceeded')
    source_hash=hashlib.sha256();copied=0
    fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as incoming:
        if fingerprint(os.fstat(incoming.fileno()))!=fingerprint(initial):raise ValueError('Source changed before copy')
        with os.fdopen(os.open(partial,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as outgoing:
            while True:
                guard();block=incoming.read(BLOCK)
                if not block:break
                copied+=len(block)
                if copied>initial.st_size:raise ValueError('Source grew during copy')
                outgoing.write(block);source_hash.update(block)
            outgoing.flush();os.fsync(outgoing.fileno());guard()
        if copied!=initial.st_size or fingerprint(os.fstat(incoming.fileno()))!=fingerprint(initial):
            raise ValueError('Source changed during copy')
    digest=hashlib.sha256();verified=0
    with partial.open('rb') as restored:
        while True:
            guard();block=restored.read(BLOCK)
            if not block:break
            verified+=len(block)
            if verified>initial.st_size:raise ValueError('Preserved copy grew during verification')
            digest.update(block)
    if verified!=copied or digest.digest()!=source_hash.digest():raise ValueError('Preserved copy hash mismatch')
    no_sidecars(source)
    if fingerprint(source.stat())!=fingerprint(initial):raise ValueError('Source changed during verification')
    guard()
    result={'format':'scanner-backup-preservation-1','state':'bytes-preserved-and-verified',
        'completedAt':datetime.now(timezone.utc).isoformat(),
        'sourceIdentity':identity,'sourceFilename':source.name,'sourceBytes':copied,
        'sourceMtimeNs':initial.st_mtime_ns,'sha256':digest.hexdigest(),'preservedDatabase':str(target),
        'copySeconds':round(time.monotonic()-started,3),'limits':{'maxBytes':MAX_BYTES,'copyAndVerifySeconds':COPY_SECONDS},
        'payloadsValidated':False,'sqliteIntegrityChecked':False,'liveDatabaseCompared':False,
        'cloudRequests':0,'servicesChanged':False,
        'limitations':['Byte equality with the selected local backup only; not full SQLite or launch-payload validation.',
            'No comparison with live payloads, cloud restoration, retention change or operational recovery.']}
    # Publish the database without replacing a path; manifest is the completion marker.
    os.link(partial,target);partial.unlink()
    with os.fdopen(os.open(output/'preservation.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'w') as f:
        json.dump(result,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    folder=os.open(output,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(folder)
    finally:os.close(folder)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backup-directory',type=Path,default=Path('/var/backups/solana-radar'))
    p.add_argument('--source-identity',required=True);p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();print(json.dumps(preserve(a.backup_directory,a.source_identity,a.output_dir),indent=2))

if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit('Backup preservation stopped: '+str(e))
