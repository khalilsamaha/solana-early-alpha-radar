#!/usr/bin/env python3
"""Install separate bounded observer; never rebuild or modify scanner."""
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile,sqlite3,time
from pathlib import Path
BUNDLE=Path(__file__).resolve().parent
DEST=Path('/usr/local/lib/solana-radar-quotes/0.9.0')
CONFIG=Path('/etc/solana-radar-quotes.json')
REPORTS=Path('/var/lib/solana-radar-quotes')
UNIT=Path('/etc/systemd/system/solana-radar-quotes.service')
MARKER='# Managed by solana-radar-quote-observer-0.9.0'

def run(args,**kwargs):return subprocess.run(args,check=True,text=True,capture_output=True,timeout=45,**kwargs).stdout.strip()
def unit(node,database):
    return f'''{MARKER}
[Unit]
Description=Solana Radar walletless signal quote observer
After=docker.service network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=3
[Service]
Type=simple
ExecStart=/usr/bin/flock -n /run/lock/solana-radar-quotes.lock {node} {DEST}/observer.mjs
Restart=on-failure
RestartSec=30
TimeoutStopSec=15
KillMode=control-group
UMask=0077
MemoryMax=192M
CPUQuota=25%
Nice=10
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={REPORTS} /run/lock
ReadOnlyPaths={database.parent}
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
CapabilityBoundingSet=CAP_DAC_READ_SEARCH
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
[Install]
WantedBy=multi-user.target
'''

def write(p,data,mode):
    p.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=p.parent,prefix='.quote-install-')
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,mode);os.replace(tmp,p)
    finally:Path(tmp).unlink(missing_ok=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path,required=True);p.add_argument('--enable-service',action='store_true');a=p.parse_args()
    if os.geteuid()!=0:raise RuntimeError('Run installer with sudo')
    os.umask(0o077)
    project=a.project.resolve(strict=True)
    if json.loads((project/'package.json').read_text()).get('version')!='0.2.9':raise RuntimeError('Expected scanner v0.2.9')
    manifest=json.loads((BUNDLE/'manifest.json').read_text())
    for name,sha in manifest['files'].items():
        if Path(name).name!=name or (BUNDLE/name).is_symlink() or hashlib.sha256((BUNDLE/name).read_bytes()).hexdigest()!=sha:raise RuntimeError('Bundle verification failed: '+name)
    node=shutil.which('node');flock=Path('/usr/bin/flock')
    if not node or not flock.exists():raise RuntimeError('Node and flock are required')
    node=str(Path(node).resolve())
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+',node):raise RuntimeError('Unsupported Node path')
    if not run([node,'--version']).startswith('v24.'):raise RuntimeError('Host Node 24 required')
    cid=run(['docker','compose','ps','-q','radar'],cwd=project)
    if not cid or '\n' in cid:raise RuntimeError('Expected one running radar container')
    info=json.loads(run(['docker','inspect',cid]))[0]
    mounts=[m for m in info['Mounts'] if m['Destination']=='/app/data']
    if len(mounts)!=1:raise RuntimeError('Cannot resolve scanner data mount')
    database=(Path(mounts[0]['Source'])/'radar.sqlite').resolve(strict=True)
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+',str(database)):raise RuntimeError('Unsupported data path')
    config=json.dumps({'managedBy':MARKER,'database':str(database),'reports':str(REPORTS)},indent=2)+'\n'
    service=unit(node,database)
    for path,expected in [(CONFIG,config),(UNIT,service)]:
        if path.is_symlink() or (path.exists() and path.read_text() not in (expected,expected.replace('0.9.0','0.8.0'),expected.replace('0.9.0','0.7.0'),expected.replace('0.9.0','0.6.0'),expected.replace('0.9.0','0.5.0'),expected.replace('0.9.0','0.4.0'),expected.replace('0.9.0','0.3.0'),expected.replace('0.9.0','0.2.0'))):raise RuntimeError('Existing configuration differs; preserved: '+str(path))
    for directory in [DEST,REPORTS]:
        if directory.is_symlink():raise RuntimeError('Refusing symlink directory')
    if DEST.exists():
        for name,sha in manifest['files'].items():
            dest=DEST/name
            if dest.is_symlink() or not dest.is_file() or hashlib.sha256(dest.read_bytes()).hexdigest()!=sha:raise RuntimeError('Installed payload differs; preserved')
    # Check runtime SQLite support and read-only schema before installation.
    run([node,'--input-type=module','-e',"import {DatabaseSync} from 'node:sqlite'; const d=new DatabaseSync(process.argv[1],{readOnly:true});d.prepare('SELECT seq,kind,at,data FROM events LIMIT 1').get();d.close();",str(database)])
    with tempfile.TemporaryDirectory(prefix='radar-quotes-tests-') as d:
        for name in manifest['files']:shutil.copyfile(BUNDLE/name,Path(d)/name)
        result=run([node,'--test','quote-check.test.mjs','observer.test.mjs','sampling.test.mjs','error-evidence.test.mjs','entry-features.test.mjs','pricing-evidence.test.mjs'],cwd=d);print(result)
        print(run(['/usr/bin/python3','-E','-s','-m','unittest','test_manage.py','test_audit.py','test_qualification.py','test_exit_evidence.py','test_install.py'],cwd=d))
    if (DEST.is_dir() and CONFIG.exists() and UNIT.exists() and CONFIG.read_text()==config and UNIT.read_text()==service
            and subprocess.run(['systemctl','is-active','--quiet',UNIT.name],timeout=10).returncode==0):
        if a.enable_service:run(['systemctl','enable',UNIT.name])
        print('Quote observer 0.9.0 already installed and running; no restart or ledger rewrite.');return
    DEST.mkdir(parents=True,exist_ok=True);REPORTS.mkdir(parents=True,exist_ok=True);os.chmod(REPORTS,0o700)
    for name in manifest['files']:write(DEST/name,(BUNDLE/name).read_bytes(),0o644)
    write(DEST/'manifest.json',(BUNDLE/'manifest.json').read_bytes(),0o644)
    previous={p:p.read_bytes() if p.exists() else None for p in (CONFIG,UNIT)}
    active=subprocess.run(['systemctl','is-active','--quiet',UNIT.name],timeout=10).returncode==0
    if active:run(['systemctl','stop',UNIT.name])
    try:
        ledger=REPORTS/'observer.sqlite'
        if ledger.exists():
            if ledger.is_symlink():raise RuntimeError('Refusing symlink ledger')
            stamp=time.time_ns();backup=REPORTS/f'pre-0.9.0-{stamp}.sqlite';deadline=time.monotonic()+10
            def progress(status,remaining,total):
                if time.monotonic()>deadline:raise RuntimeError('Ledger safety copy exceeded deadline')
            try:
                with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(backup) as dst:
                    src.backup(dst,pages=1024,progress=progress)
                    dst.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
                    if dst.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise RuntimeError('Ledger safety copy failed integrity check')
            except Exception:
                backup.unlink(missing_ok=True)
                raise
            os.chmod(backup,0o600)
        write(CONFIG,config.encode(),0o600);write(UNIT,service.encode(),0o644)
        run(['systemctl','daemon-reload'])
        if a.enable_service:run(['systemctl','enable',UNIT.name])
        if active or a.enable_service:run(['systemctl','restart',UNIT.name])
    except Exception:
        for path,data in previous.items():
            if data is None:path.unlink(missing_ok=True)
            else:write(path,data,0o600 if path==CONFIG else 0o644)
        run(['systemctl','daemon-reload'])
        if active:run(['systemctl','start',UNIT.name])
        raise
    print('Quote observer 0.9.0 installed. Scanner and research tools unchanged; no rebuild needed.')
    print('Observer enabled/restarted.' if a.enable_service or active else 'Service installed, not started.')
    print('Existing ledger and cursor preserved. A running watch may be marked interrupted during the observer restart.')
    print('Versioned entry context is captured from immutable scanner events. Request budgets and sampling are unchanged.')
if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit('Installation stopped: '+str(e))
