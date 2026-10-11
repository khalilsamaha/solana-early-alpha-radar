"""Check tracked source hygiene and immutable package manifests without network access.

This is a bounded credential-pattern check, not a complete secret detector.
Original deployed hashes are provenance, not a restriction on future source edits.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    re.compile(r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----'),
    re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    re.compile(r'\b\d{7,12}:AA[A-Za-z0-9_-]{25,}\b'),
    re.compile(r'https://(?:hc-ping\.com|ping\.healthchecks\.io)/[0-9a-fA-F-]{36}'),
    re.compile(r'''["']?(?:DASHBOARD_TOKEN|HELIUS_API_KEY|JUPITER_API_KEY|TELEGRAM_BOT_TOKEN|PUMPPORTAL_API_KEY)["']?\s*[:=]\s*["'][A-Za-z0-9_:/+.-]{20,}["']'''),
]


def main():
    result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, check=True, capture_output=True)
    names = [p for p in result.stdout.decode().split('\0') if p]
    if not names:
        raise SystemExit('No tracked files to check')
    failures = []
    for name in names:
        path = ROOT / name
        parts = Path(name).parts
        if (path.is_symlink() or any(p in {'data', 'backups', 'source-backups', 'reports', '__pycache__', 'node_modules'} for p in parts)
                or path.name.startswith('.env') or path.name in {'rclone.conf', 'heartbeat-url'}
                or re.search(r'\.(sqlite|db)(?:-|\.|$)|\.(pem|key|pyc)$', path.name)):
            failures.append(name + ': prohibited tracked file')
            continue
        if path.stat().st_size > 4 * 1024 * 1024:
            failures.append(name + ': oversized source file')
            continue
        try:
            content = path.read_text()
        except UnicodeDecodeError:
            failures.append(name + ': unexpected binary file')
            continue
        for line, text in enumerate(content.splitlines(), 1):
            if any(pattern.search(text) for pattern in PATTERNS):
                failures.append(f'{name}:{line}: credential pattern; value withheld')
    for component in ['quote-observer', 'research-tools', 'operations-tools']:
        manifest = json.loads((ROOT / component / 'manifest.json').read_text())
        for name, expected in manifest['files'].items():
            path = ROOT / component / name
            if Path(name).name != name or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                failures.append(f'{component}/{name}: package manifest mismatch')
    if failures:
        raise SystemExit('\n'.join(failures))
    print(f'Source hygiene and package manifests: OK ({len(names)} tracked files)')


if __name__ == '__main__':
    main()
