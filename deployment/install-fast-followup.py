#!/usr/bin/env python3
"""Apply verified source files in the existing host project; never move Compose or data."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).with_name('fast-followup-manifest.json')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_target(project, name):
    relative = Path(name)
    if relative.is_absolute() or '..' in relative.parts:
        raise RuntimeError('Invalid source path')
    current = project
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError('Symlink source target refused')
    if not current.resolve().is_relative_to(project):
        raise RuntimeError('Source outside project')
    return current


def atomic(path, data):
    mode = path.stat().st_mode & 0o777
    fd, name = tempfile.mkstemp(prefix='.fast-followup-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(name, mode); os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def install(project, rollback=None):
    project = Path(project).expanduser().resolve(strict=True)
    manifest = json.loads(MANIFEST.read_text())
    changed = manifest['changed']
    for name in list(changed) + list(manifest['dependencies']):
        safe_target(project, name)
    if rollback:
        backup = Path(rollback).expanduser().resolve(strict=True)
        if backup.parent != project / 'source-backups' or json.loads((backup/'manifest.json').read_text()) != manifest:
            raise RuntimeError('Backup does not belong to this update and project')
        for name, hashes in changed.items():
            if digest(project/name) != hashes['after'] or digest(backup/name) != hashes['before']:
                raise RuntimeError('Source changed; rollback refused')
        for name in changed: atomic(project/name, (backup/name).read_bytes())
        print('Previous source restored. Rebuild in the original project directory to activate.'); return
    for name, hashes in changed.items():
        if digest(ROOT/'scanner'/name) != hashes['after']:
            raise RuntimeError('Checkout payload integrity mismatch: '+name)
    for name, expected in manifest['dependencies'].items():
        if digest(project/name) != expected:
            raise RuntimeError('Unexpected installed dependency; no changes: '+name)
    if all(digest(project/name) == hashes['after'] for name, hashes in changed.items()):
        print('Fast follow-up source already installed.'); return
    for name, hashes in changed.items():
        if digest(project/name) != hashes['before']:
            raise RuntimeError('Unexpected installed source; no changes: '+name)
    with tempfile.TemporaryDirectory(prefix='radar-fast-stage-') as folder:
        stage=Path(folder)
        for directory in ['src','public']:
            shutil.copytree(project/directory,stage/directory)
        shutil.copyfile(project/'package.json',stage/'package.json')
        shutil.copytree(ROOT/'scanner/test',stage/'test')
        shutil.copytree(ROOT/'scanner/scripts',stage/'scripts')
        shutil.copytree(ROOT/'scanner/fixtures',stage/'fixtures')
        for name in changed: shutil.copyfile(ROOT/'scanner'/name,stage/name)
        subprocess.run(['node','--test',*[str(p.relative_to(stage)) for p in sorted((stage/'test').glob('*.test.js'))]],cwd=stage,check=True,timeout=120)
    backup_parent=project/'source-backups'
    if backup_parent.is_symlink(): raise RuntimeError('Symlink backup directory refused')
    backup_parent.mkdir(exist_ok=True)
    backup=backup_parent/('fast-followup-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(mode=0o700)
    for name in changed:
        (backup/name).parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(project/name,backup/name)
    shutil.copyfile(MANIFEST,backup/'manifest.json')
    try:
        for name in changed: atomic(project/name,(ROOT/'scanner'/name).read_bytes())
    except BaseException:
        for name in changed: atomic(project/name,(backup/name).read_bytes())
        raise
    print('Fast follow-up source installed. Backup: '+str(backup))
    print('Rebuild radar from the original project directory. Compose, configuration and databases were not changed.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,required=True);p.add_argument('--rollback',type=Path)
    args=p.parse_args();install(args.project,args.rollback)


if __name__ == '__main__':
    try: main()
    except Exception as error: raise SystemExit('Update stopped: '+str(error))
