#!/usr/bin/env python3
"""Install the independent daily quote-ledger backup, including B2 verification."""
import hashlib, json, os, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DEST=Path('/usr/local/lib/solana-radar-operations/1.0.0')
SERVICE=Path('/etc/systemd/system/solana-radar-quotes-backup.service')
TIMER=Path('/etc/systemd/system/solana-radar-quotes-backup.timer')
MARKER='# Managed by radar-quote-backup-1'
UNIT=f'''{MARKER}
[Unit]
Description=Verified local and B2 Solana quote ledger backup
Wants=network-online.target
After=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -E -s {DEST}/quote_backup.py --cloud
TimeoutStartSec=300
UMask=0077
MemoryMax=192M
Nice=10
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/backups/solana-radar-quotes /var/lib/solana-radar-quotes
'''
CLOCK=f'''{MARKER}
[Unit]
Description=Daily verified quote ledger backup
[Timer]
OnCalendar=*-*-* 04:10:00
RandomizedDelaySec=300
Persistent=true
Unit=solana-radar-quotes-backup.service
[Install]
WantedBy=timers.target
'''

def atomic(path,content,mode):
    fd,name=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(content);f.flush();os.fsync(f.fileno())
        os.chmod(name,mode);os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)

def main():
    if os.geteuid()!=0:raise ValueError('Run with sudo')
    for p in [Path('/etc/solana-radar-quotes.json'),Path('/etc/solana-radar/rclone.conf'),Path('/usr/local/bin/rclone')]:
        if not p.is_file():raise ValueError('Missing prerequisite: '+str(p))
    config=json.loads(Path('/etc/solana-radar-quotes.json').read_text())
    if config.get('reports')!='/var/lib/solana-radar-quotes':raise ValueError('Unexpected quote ledger directory; review before installation')
    manifest=json.loads((ROOT/'manifest.json').read_text())
    for name,expected in manifest['files'].items():
        if Path(name).name!=name or (ROOT/name).is_symlink() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise ValueError('Package integrity failed')
    output=Path('/var/backups/solana-radar-quotes')
    for p in [DEST,output,SERVICE,TIMER,DEST/'quote_backup.py']:
        if p.is_symlink() or any(parent.is_symlink() for parent in p.parents):raise ValueError('Symlink target refused')
    for p,content in [(SERVICE,UNIT),(TIMER,CLOCK)]:
        if p.exists() and p.read_text()!=content:raise ValueError('Existing unit differs; preserved: '+str(p))
    if (DEST/'quote_backup.py').exists() and (DEST/'quote_backup.py').read_bytes()!=(ROOT/'quote_backup.py').read_bytes():raise ValueError('Installed payload differs')
    subprocess.run(['/usr/bin/python3','-E','-s','-m','unittest','test_operations.py'],cwd=ROOT,check=True,timeout=60)
    DEST.mkdir(parents=True,exist_ok=True);output.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(output,0o700)
    atomic(DEST/'quote_backup.py',(ROOT/'quote_backup.py').read_bytes(),0o644)
    atomic(SERVICE,UNIT.encode(),0o644);atomic(TIMER,CLOCK.encode(),0o644)
    subprocess.run(['systemctl','daemon-reload'],check=True,timeout=15)
    subprocess.run(['systemctl','enable','--now',TIMER.name],check=True,timeout=20)
    print('Daily quote backup enabled: 04:10–04:15 host time, with missed-run catch-up. Run the service once now to verify local and cloud access.')
    print('No cloud retention deletion or external failure notification is configured by this installer.')
if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit('Backup installation stopped: '+str(e))
