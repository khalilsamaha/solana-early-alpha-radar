#!/usr/bin/env python3
"""Install a separate research service. Scanner source, config and backups are untouched."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from research_analysis import RULES_HASH

BUNDLE=Path(__file__).resolve().parent
DEST=Path('/usr/local/lib/solana-radar-research/1.1.0')
LAUNCHER=Path('/usr/local/sbin/radar-research')
CONFIG=Path('/etc/solana-radar-research.json')
REPORTS=Path('/var/lib/solana-radar-research')
SERVICE=Path('/etc/systemd/system/solana-radar-research.service')
TIMER=Path('/etc/systemd/system/solana-radar-research.timer')
MARKER='# Managed by solana-radar-research-tools-1.1.0'


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def payload():
    manifest=json.loads((BUNDLE/'manifest.json').read_text())
    for name,sha in manifest['files'].items():
        if Path(name).name!=name or (BUNDLE/name).is_symlink() or digest(BUNDLE/name)!=sha:
            raise RuntimeError('Bundle verification failed: '+name)
    return manifest


def generated(project):
    return {
      LAUNCHER: '#!/bin/sh\n'+MARKER+'\nexec /usr/bin/python3 -E -s '+str(DEST/'radar_research.py')+' "$@"\n',
      CONFIG: json.dumps({'managedBy':MARKER,'project':str(project)},indent=2)+'\n',
      SERVICE: f'''{MARKER}
[Unit]
Description=Bounded read-only Solana Radar research report
After=docker.service
[Service]
Type=oneshot
ExecStart={LAUNCHER} --live --scheduled --hours 2
TimeoutStartSec=90
KillMode=control-group
Nice=10
CPUQuota=50%
MemoryMax=384M
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
StandardOutput=journal
StandardError=journal
''',
      TIMER: f'''{MARKER}
[Unit]
Description=Solana Radar research summary every 30 minutes
[Timer]
OnCalendar=*-*-* *:00,30:00
RandomizedDelaySec=30
AccuracySec=10
Persistent=true
Unit=solana-radar-research.service
[Install]
WantedBy=timers.target
'''}


def write(path,data,mode=0o644):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.research-install-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,mode);os.replace(tmp,path)
    finally:Path(tmp).unlink(missing_ok=True)


def install(project, timer=False):
    manifest=payload()
    project=project.resolve(strict=True)
    if not (project/'package.json').is_file() or json.loads((project/'package.json').read_text()).get('version')!='0.2.9':
        raise RuntimeError('This add-on expects the deployed v0.2.9 project')
    files=generated(project)
    previous=[{p:data.replace('solana-radar-research-tools-1.1.0','solana-radar-research-tools-'+v).replace('/solana-radar-research/1.1.0','/solana-radar-research/'+v) for p,data in files.items()} for v in ('1.0.0','1.0.1')]
    for p,data in files.items():
        if p.is_symlink():raise RuntimeError('Refusing symlink: '+str(p))
        if p.exists() and p.read_text() not in (data,*(old[p] for old in previous)):
            raise RuntimeError('Existing installation differs: '+str(p))
    registration_path=REPORTS/'shadow-registration-v1.json'
    if registration_path.is_symlink():raise RuntimeError('Refusing registration symlink')
    if registration_path.exists():
        reg=json.loads(registration_path.read_text())
        if reg.get('rulesSha256')!=RULES_HASH or not isinstance(reg.get('registeredAtMs'),int):
            raise RuntimeError('Existing shadow registration differs; preserved')
    if DEST.exists():
        for name,sha in manifest['files'].items():
            if not (DEST/name).is_file() or digest(DEST/name)!=sha:
                raise RuntimeError('Installed payload differs; no files overwritten')
    # Run meaningful tests before installing anything. No scanner environment is loaded.
    with tempfile.TemporaryDirectory(prefix='radar-research-tests-') as d:
        for name in manifest['files']:shutil.copyfile(BUNDLE/name,Path(d)/name)
        subprocess.run(['/usr/bin/python3','-E','-s','-m','unittest','discover','-p','test_*.py'],cwd=d,check=True)
    DEST.mkdir(parents=True,exist_ok=True)
    os.chmod(DEST,0o755)
    for name in manifest['files']:write(DEST/name,(BUNDLE/name).read_bytes(),0o644)
    write(DEST/'manifest.json',(BUNDLE/'manifest.json').read_bytes())
    REPORTS.mkdir(parents=True,exist_ok=True);os.chmod(REPORTS,0o700)
    if not registration_path.exists():
        write(registration_path,json.dumps({'rulesSha256':RULES_HASH,'registeredAtMs':int(time.time()*1000),'registeredBy':'research-tools-1.1.0'}).encode(),0o600)
    for p,data in files.items():write(p,data.encode(),0o755 if p==LAUNCHER else 0o600 if p==CONFIG else 0o644)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    if timer:subprocess.run(['systemctl','enable','--now',TIMER.name],check=True)
    print('Research tools 1.1.0 installed. Scanner unchanged; no rebuild or restart needed. Shadow rules registered for forward comparison.')
    print('30-minute timer enabled.' if timer else 'Timer installed but not enabled.')


def uninstall():
    # Leave reports intact. Stop only this add-on, never radar or backup services.
    if not CONFIG.exists() or json.loads(CONFIG.read_text()).get('managedBy')!=MARKER:
        raise RuntimeError('No matching managed installation')
    project=Path(json.loads(CONFIG.read_text())['project'])
    for p,data in generated(project).items():
        if p.exists() and (p.is_symlink() or p.read_text()!=data):
            raise RuntimeError('Edited file preserved; manual review needed: '+str(p))
    subprocess.run(['systemctl','disable','--now',TIMER.name],check=True)
    subprocess.run(['systemctl','stop',SERVICE.name],check=True)
    for p in [SERVICE,TIMER,LAUNCHER,CONFIG]:p.unlink(missing_ok=True)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    # Keep the small immutable payload and collected reports for audit/replay.
    print('Research timer and command removed; scanner, backups and collected reports preserved.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path)
    p.add_argument('--enable-timer',action='store_true')
    p.add_argument('--uninstall',action='store_true')
    a=p.parse_args()
    if os.geteuid()!=0:raise RuntimeError('Use sudo for installing the root-owned host service')
    if a.uninstall:uninstall()
    elif a.project:install(a.project,a.enable_timer)
    else:p.error('--project is required for installation')

if __name__=='__main__':
    try:main()
    except Exception as e:print('Installation stopped:',e,file=sys.stderr);sys.exit(1)
