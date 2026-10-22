#!/usr/bin/env python3
"""Compare bounded release hashes with host and container files; no installation."""
import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'launch-study'))
from report import publish
MANIFEST = Path(__file__).with_name('engineering-release-1.json')
MAX_FILE_BYTES = 2 * 1024 * 1024


def command(args, timeout=15):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
        if p.returncode != 0 or len(p.stdout) > 256 * 1024:
            return None
        return p.stdout.decode('utf-8')
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return None


def file_hash(root, name):
    if Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('Unsafe manifest path')
    path = root
    for part in Path(name).parts:
        path = path / part
        if path.is_symlink():
            return None
    try:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return None
        with path.open('rb') as f:
            content = f.read(MAX_FILE_BYTES + 1)
        return hashlib.sha256(content).hexdigest() if len(content) <= MAX_FILE_BYTES else None
    except OSError:
        return None


def compare(expected, actual):
    return {'expectedFiles': len(expected), 'matched': sum(actual.get(k) == v for k, v in expected.items()),
            'mismatched': [k for k, v in expected.items() if actual.get(k) is not None and actual[k] != v],
            'unavailable': [k for k in expected if actual.get(k) is None]}


def disk_inventory(project, manifest):
    expected = manifest['scannerFiles']
    return compare(expected, {name: file_hash(project, name) for name in expected})


def container_inventory(project, expected):
    ids = command(['docker', 'compose', '--project-directory', str(project), 'ps', '-q', 'radar'])
    if ids is None or not re.fullmatch(r'[a-f0-9]{12,64}\s*', ids):
        return {'state': 'unavailable', 'reason': 'requires-one-running-container-and-docker-access'}
    cid = ids.strip()
    raw = command(['docker', 'inspect', '--format',
        '{"image":{{json .Image}},"startedAt":{{json .State.StartedAt}},"restartCount":{{.RestartCount}},"status":{{json .State.Status}},"health":{{json .State.Health.Status}}}', cid])
    try:
        state = json.loads(raw) if raw else None
    except ValueError:
        state = None
    # Fixed code reads only manifest-listed application files. No config, environment or database reads.
    script = """const fs=require('node:fs'),c=require('node:crypto');const names=JSON.parse(process.argv[1]),out={};
for(const name of names){try{const p='/app/'+name,s=fs.lstatSync(p);out[name]=s.isFile()&&fs.realpathSync(p)===p&&s.size<=2097152?c.createHash('sha256').update(fs.readFileSync(p)).digest('hex'):null}catch{out[name]=null}}console.log(JSON.stringify(out));"""
    applicable = {k: v for k, v in expected.items() if k == 'package.json' or k.startswith(('src/', 'scripts/', 'public/'))}
    hashes = command(['docker', 'exec', cid, 'node', '-e', script, json.dumps(list(applicable))], 20)
    try:
        actual = json.loads(hashes) if hashes else {}
        if not isinstance(actual, dict):
            actual = {}
    except ValueError:
        actual = {}
    return {'state': 'inspected' if state else 'partially-unavailable', 'container': state,
            'files': compare(applicable, actual),
            'basis': 'Current container filesystem, not proof of resident JavaScript module identity.'}


def observer_inventory(manifest):
    version = manifest['observerVersion']
    root = Path('/usr/local/lib/solana-radar-quotes') / version
    expected = manifest['observerFiles']
    status = command(['systemctl', 'show', 'solana-radar-quotes.service', '--no-pager',
                      '-p', 'ActiveState', '-p', 'SubState', '-p', 'ExecMainStatus'])
    state = {}
    for line in (status or '').splitlines():
        key, _, value = line.partition('=')
        if key in ('ActiveState', 'SubState', 'ExecMainStatus') and re.fullmatch(r'[a-zA-Z0-9-]{1,40}', value):
            state[key] = value
    start = command(['systemctl', 'show', 'solana-radar-quotes.service', '--no-pager', '-p', 'ExecStart', '--value'])
    versions = sorted(set(re.findall(r'/usr/local/lib/solana-radar-quotes/(\d+\.\d+\.\d+)/observer\.mjs', start or '')))
    return {'expectedVersion': version, 'configuredVersions': versions, 'unitState': state or None,
            'files': compare(expected, {k: file_hash(root, k) for k in expected}),
            'basis': 'Installed files and unit configuration; live observer self-report must be checked separately.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    git = ['git', '-c', 'safe.directory=' + str(ROOT), '-C', str(ROOT)]
    head = command(git + ['rev-parse', 'HEAD'])
    dirty = command(git + ['status', '--porcelain', '--untracked-files=no'])
    result = {'format': 'deployment-inventory-1', 'capturedAt': dt.datetime.now(dt.timezone.utc).isoformat(),
              'release': manifest['release'], 'protocolSha256': manifest['protocolSha256'],
              'devCommit': head.strip() if head and re.fullmatch(r'[a-f0-9]{40}\s*', head) else None,
              'devTrackedChanges': bool(dirty.strip()) if dirty is not None else None,
              'scannerHostFiles': disk_inventory(a.project, manifest),
              'scannerContainer': container_inventory(a.project, manifest['scannerFiles']),
              'observer': observer_inventory(manifest), 'externalNetworkRequests': 0,
              'changesMade': False,
              'limitations': ['Missing access is unavailable evidence, not a passing check.',
                              'No secrets, Compose configuration, logs, databases or private reports are included.',
                              'Versions describe separate components. Scanner 0.2.9 alone does not identify applied patches.']}
    publish(a.output, result)
    print('Host source:', result['scannerHostFiles'])
    print('Container:', result['scannerContainer']['state'])
    print('Upload:', a.output.resolve())


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        raise SystemExit('Deployment inventory stopped: ' + type(e).__name__)
