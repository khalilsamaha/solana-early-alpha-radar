#!/usr/bin/env python3
"""Profile disposable successor execution offline; no operational input or execution mode."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def command(args, pattern):
    try:
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=5)
        value = r.stdout.strip()
        return value if r.returncode == 0 and re.fullmatch(pattern, value) else None
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None


def runtime():
    dirty = None
    try:
        r = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=normal'],
                           cwd=ROOT, capture_output=True, timeout=5)
        if r.returncode == 0:
            dirty = bool(r.stdout)
    except (OSError, subprocess.SubprocessError):
        pass
    return dict(python='.'.join(map(str, sys.version_info[:3])),
                node=command(['node', '--version'], r'v\d+\.\d+\.\d+'),
                sourceCommit=command(['git', 'rev-parse', 'HEAD'], r'[0-9a-f]{40}'),
                workingTreeDirty=dirty, logicalCpuCount=os.cpu_count(),
                basis='Local runtime and Git metadata; not an independent source attestation.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
        raise ValueError('output-unavailable')
    from successor_profile import run
    before = runtime()
    report = run()
    report.update(capturedAt=datetime.now(timezone.utc).isoformat(), runtimeBefore=before, runtimeAfter=runtime())
    sys.path.insert(0, str(ROOT/'launch-study'))
    from report import publish
    publish(args.output, report)
    print('Diagnostic:', report['state'])
    print('Underlying rehearsal:', report['rehearsal']['state'])
    print('Headroom ms:', report['rehearsal'].get('headroomAtReturnMs'))
    print('Recorded spans:', len(report['profile']['spans']))
    print('Diagnostic only; not timing acceptance. No real network, wallet or transaction.')
    print('Upload:', args.output.absolute())
    return 0 if report['state'] == 'diagnostic-collected' else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        raise SystemExit('Offline successor profile stopped ('+type(exc).__name__+').')
