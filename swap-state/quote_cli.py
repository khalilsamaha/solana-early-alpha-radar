#!/usr/bin/env python3
"""Offline declared-quote/account binding check. No RPC, signer or sender."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import time

from cli import read, publish
from quote_binding import review
from quote_checks import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Public binding bundle; checked against the current clock')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
        raise ValueError('Output unavailable')
    if args.input:
        result = review(read(args.input), now_ms=time.time_ns() // 1000000)
    else:
        result = run()
    result['capturedAt'] = datetime.now(timezone.utc).isoformat()
    publish(args.output, result)
    print('State:', result.get('state', 'offline-checks-passed'))
    if 'casesPassed' in result:
        print('Synthetic cases passed:', result['casesPassed'])
    print('No RPC requests, signing, submission or runtime changes.')
    print('Upload:', args.output.absolute())
    return 0 if result.get('state') in (None, 'declared-quote-state-consistent') else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        raise SystemExit('Quote binding stopped (' + type(exc).__name__ + '). No complete report published.')
