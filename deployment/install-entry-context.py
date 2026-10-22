#!/usr/bin/env python3
"""Guarded entry context source update. No configuration/data copy."""
import argparse, datetime, hashlib, json, os, shutil, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MANIFEST=Path(__file__).with_name('entry-context-manifest.json')

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

def safe(project,name):
    p=Path(name)
    if p.is_absolute() or '..' in p.parts:raise ValueError('Invalid relative path')
    current=project
    for part in p.parts:
        current=current/part
        if current.is_symlink():raise ValueError('Symlink source refused')
    if not current.resolve().is_relative_to(project):raise ValueError('Source outside project')
    return current

def atomic(path,data):
    mode=path.stat().st_mode&0o777 if path.exists() else 0o644
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.entry-context-')
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,mode);os.replace(tmp,path)
    finally:Path(tmp).unlink(missing_ok=True)

def install(project,rollback=None):
    project=Path(project).resolve(strict=True);manifest=json.loads(MANIFEST.read_text());changed=manifest['changed']
    for name in list(changed)+list(manifest['dependencies']):safe(project,name)
    if rollback:
        backup=Path(rollback).resolve(strict=True)
        if backup.parent!=project/'source-backups':raise ValueError('Backup outside this project')
        record=json.loads((backup/'manifest.json').read_text())
        if record['release']!=manifest:raise ValueError('Different backup release')
        for name,h in changed.items():
            if digest(project/name)!=h['after'] or digest(safe(backup,name))!=record['original'][name]:raise ValueError('Source/backup changed; rollback refused')
        for name in changed:
            if record['original'][name] is None:(project/name).unlink()
            else:atomic(project/name,(backup/name).read_bytes())
        print('Source rolled back. Rebuild radar. Stored evidence remains in the existing database.');return
    for name,h in changed.items():
        if digest(ROOT/'scanner'/name)!=h['after']:raise ValueError('Payload integrity mismatch: '+name)
    for name,h in manifest['dependencies'].items():
        if digest(project/name)!=h:raise ValueError('Unexpected installed dependency: '+name)
    if all(digest(project/n)==h['after'] for n,h in changed.items()):print('Entry context source already installed.');return
    original={name:digest(project/name) for name in changed}
    for name,h in changed.items():
        if original[name] not in h['before']:raise ValueError('Unexpected installed source: '+name)
    with tempfile.TemporaryDirectory(prefix='radar-launch-stage-') as d:
        stage=Path(d)
        for folder in ['src','public']:shutil.copytree(project/folder,stage/folder)
        shutil.copyfile(project/'package.json',stage/'package.json')
        for folder in ['test','scripts','fixtures']:shutil.copytree(ROOT/'scanner'/folder,stage/folder)
        for name in changed:shutil.copyfile(ROOT/'scanner'/name,stage/name)
        subprocess.run(['node','--test',*[str(p.relative_to(stage)) for p in sorted((stage/'test').glob('*.test.js'))]],cwd=stage,check=True,timeout=120)
    parent=project/'source-backups'
    if parent.is_symlink():raise ValueError('Symlink backup parent refused')
    parent.mkdir(exist_ok=True);backup=parent/('entry-context-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));backup.mkdir(mode=0o700)
    for name in changed:
        if original[name] is not None:
            (backup/name).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(project/name,backup/name)
    atomic(backup/'manifest.json',(json.dumps({'release':manifest,'original':original},indent=2)+'\n').encode())
    try:
        for name in changed:atomic(project/name,(ROOT/'scanner'/name).read_bytes())
    except BaseException:
        for name in changed:
            if original[name] is None:(project/name).unlink(missing_ok=True)
            else:atomic(project/name,(backup/name).read_bytes())
        raise
    print('Entry context source installed. Backup: '+str(backup))
    print('Rebuild in the original running project. Scanner 0.2.9 rules, Compose, credentials and quote observer are unchanged.')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path,required=True);p.add_argument('--rollback',type=Path);a=p.parse_args();install(a.project,a.rollback)
if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit('Update stopped: '+str(e))
