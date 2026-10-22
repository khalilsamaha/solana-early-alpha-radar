#!/usr/bin/env python3
"""Offline unsigned swap checks; never opens a wallet, ledger, or network connection."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from contract import validate
from swap_checks import run
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'intent-lab'))
from intent_cli import read
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launch-study'))
from report import publish


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Optional public unsigned packet; no private keys')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
        raise ValueError('Output unavailable')
    result = validate(read(args.input), now_ms=time.time_ns() // 1000000) if args.input else run()
    result['capturedAt'] = datetime.now(timezone.utc).isoformat()
    publish(args.output, result)
    print('Swap contract:', result.get('state', str(result.get('casesPassed')) + ' self-check cases passed'))
    print('No network requests, signatures or transactions. A match is not signing approval.')
    print('Upload:', args.output.absolute())


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Swap contract check stopped (' + type(exc).__name__ + '); no complete report published.')
