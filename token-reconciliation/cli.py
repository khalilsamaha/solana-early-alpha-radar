#!/usr/bin/env python3
"""Offline signed-token evidence audit or public synthetic self-check. No wallet access."""
import argparse
import datetime as dt
from pathlib import Path
import sys
from audit import audit, FLAGS
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'intent-lab'))
from intent_cli import read
from report import publish


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('Output already exists')
    if args.input:
        result = audit(read(args.input))
        result['mode'] = 'offline-supplied-evidence'
    else:
        from checks import run
        result = run()
    result['capturedAt'] = dt.datetime.now(dt.timezone.utc).isoformat()
    publish(args.output, result)
    print('State:', result.get('state', result['format']))
    print('No network requests, transactions or ledger changes. Upload:', args.output.resolve())


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Token audit stopped: ' + type(exc).__name__ + '. No report published.')
