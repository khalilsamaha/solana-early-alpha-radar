#!/usr/bin/env python3
"""Return only the observer program to the installed 0.4.0 version; retain its ledger."""
import hashlib,json,os,re,shutil,subprocess
from pathlib import Path
import install

def main():
    if os.geteuid()!=0:raise RuntimeError('Run rollback with sudo')
    os.umask(0o077)
    config=json.loads(install.CONFIG.read_text());database=Path(config['database'])
    expected=json.dumps({'managedBy':install.MARKER,'database':str(database),'reports':str(install.REPORTS)},indent=2)+'\n'
    node=str(Path(shutil.which('node') or '').resolve())
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+',node):raise RuntimeError('Unsupported Node path')
    current=install.unit(node,database)
    if install.CONFIG.is_symlink() or install.UNIT.is_symlink() or install.CONFIG.read_text()!=expected or install.UNIT.read_text()!=current:
        raise RuntimeError('Current configuration differs; preserved')
    old=install.DEST.parent/'0.4.0'
    if old.is_symlink():raise RuntimeError('Refusing symlink program directory')
    manifest=json.loads((old/'manifest.json').read_text())
    if manifest.get('version')!='0.4.0':raise RuntimeError('Expected installed 0.4.0 manifest')
    for name,sha in manifest['files'].items():
        p=old/name
        if Path(name).name!=name or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise RuntimeError('Previous payload verification failed')
    active=subprocess.run(['systemctl','is-active','--quiet',install.UNIT.name],timeout=10).returncode==0
    if active:install.run(['systemctl','stop',install.UNIT.name])
    try:
        install.write(install.CONFIG,expected.replace('0.5.0','0.4.0').encode(),0o600)
        install.write(install.UNIT,current.replace('0.5.0','0.4.0').encode(),0o644)
        install.run(['systemctl','daemon-reload'])
        if active:install.run(['systemctl','start',install.UNIT.name])
    except Exception:
        install.write(install.CONFIG,expected.encode(),0o600);install.write(install.UNIT,current.encode(),0o644)
        install.run(['systemctl','daemon-reload'])
        if active:install.run(['systemctl','start',install.UNIT.name])
        raise
    print('Observer program returned to 0.4.0. Ledger, cursor and sampling budgets retained; scanner unchanged.')

if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit('Rollback stopped: '+str(e))
