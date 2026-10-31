#!/usr/bin/env python3
"""Disposable-key backend self-check only; no production wallet arguments."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def run():
    node = shutil.which('node')
    if node is None: raise ValueError('node-runtime-unavailable')
    r = subprocess.run([str(Path(node).resolve()), str(Path(__file__).with_name('exit_signer_checks.mjs'))],
        text=True, capture_output=True, timeout=30, env={'PATH':os.defpath})
    if r.returncode != 0 or len(r.stdout) > 16384: raise ValueError('disposable-signer-check-failed')
    return json.loads(r.stdout)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir(): raise ValueError('output-unavailable')
    result = run(); result['capturedAt'] = datetime.now(timezone.utc).isoformat()
    publish(a.output, result)
    print('State:', result['state']); print('Offline cases passed:', result['casesPassed'])
    print('Disposable test keys only; two test signatures, zero RPC requests or sends. No production wallet access.')
    print('Upload:', a.output.absolute())


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        raise SystemExit('Restricted exit signer check stopped ('+type(exc).__name__+'); no complete report published.')
