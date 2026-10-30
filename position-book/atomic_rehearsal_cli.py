#!/usr/bin/env python3
"""Offline atomic rehearsal contract self-check. No RPC, wallet or source-directory input."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from atomic_rehearsal_checks import run
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('output-unavailable')
    r = run(); r['capturedAt'] = datetime.now(timezone.utc).isoformat()
    publish(a.output, r)
    print('State:', r['state']); print('Offline cases passed:', r['casesPassed'])
    print('No RPC requests, signing, submission or runtime changes.')
    print('Live atomic simulation and two-transaction execution remain unverified.')
    print('Upload:', a.output.absolute())


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        raise SystemExit('Atomic rehearsal check stopped ('+type(exc).__name__+'). Preserve all journals.')
