#!/usr/bin/env python3
"""Inspect scoped local reservations; optionally bind a fresh public quote bundle."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

import reservation_view as view
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'swap-state'))
from cli import read
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launch-study'))
from report import publish


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--wallet', required=True)
    parser.add_argument('--pool', required=True)
    parser.add_argument('--bundle', type=Path, help='Optional fresh public binding bundle, reservations must be null')
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('output-unavailable')
    if a.output.resolve().is_relative_to(a.directory.resolve()):
        raise ValueError('report-must-be-outside-source-directory')
    if a.bundle:
        result = view.bind(a.directory, a.wallet, a.pool, read(a.bundle))
    else:
        result = view.inspect(a.directory, a.wallet, a.pool)
    result['capturedAt'] = datetime.now(timezone.utc).isoformat()
    publish(a.output, result)
    print('State:', result['state'])
    if result['reservations']:
        r = result['reservations']
        print('Controlled cycle phase:', r['phase'])
        print('Reserved native lamports:', r['nativeHeldLamports'])
        print('Reserved token amounts:', [t['heldAtomic'] for t in r['tokenAccounts']])
    print('Read-only local evidence; no RPC, signing, submission or new-cycle authorization.')
    print('Upload:', a.output.absolute())
    return 2 if result['state'] == 'unavailable' else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        raise SystemExit('Reservation inspection stopped (' + type(exc).__name__ + '). Preserve all journals.')
