#!/usr/bin/env python3
"""Observe the fixed devnet program or replay public captures. No keys or transactions."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
from program import audit, compare, boundaries
from program_capture import collect
from checks import run
from recorded_capture import loads
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launch-study'))
from report import publish

MAX_REPORT = 8 * 1024 * 1024


def read_capture(path):
    with (gzip.open(path, 'rb') if path.suffix == '.gz' else path.open('rb')) as f:
        raw = f.read(MAX_REPORT+1)
    if len(raw) > MAX_REPORT:
        raise ValueError('Input cap')
    obj = loads(raw)
    if type(obj) is dict and obj.get('format') == 'swap-program-report-1':
        obj = obj.get('capture')
    if type(obj) is not dict or obj.get('format') != 'swap-program-capture-1':
        raise ValueError('Unsupported capture')
    return obj


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--capture-devnet', action='store_true')
    mode.add_argument('--input', type=Path, help='Offline replay; original observation time is preserved')
    parser.add_argument('--baseline', type=Path, help='Prior public program report for change comparison, never a trust grant')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
        raise ValueError('Output unavailable')
    if args.baseline and not (args.capture_devnet or args.input):
        raise ValueError('Baseline requires capture or replay')
    baseline = read_capture(args.baseline) if args.baseline else None
    if baseline is not None and audit(baseline)['state'] != 'deployment-observed':
        raise ValueError('Baseline has no complete observation')
    if args.capture_devnet or args.input:
        capture = collect() if args.capture_devnet else read_capture(args.input)
        result = dict(format='swap-program-report-1', capture=capture, baselineCapture=baseline,
                      review=audit(capture), comparison=compare(capture, baseline),
                      currentRunNetworkRequests=capture['rpcRequestsAttempted'] if args.capture_devnet else 0)
    else:
        result = run()
    result.update(capturedAt=datetime.now(timezone.utc).isoformat(), **boundaries())
    if len(json.dumps(result).encode()) > MAX_REPORT:
        raise ValueError('Report cap')
    publish(args.output, result)
    if 'review' in result:
        print('Program:', result['review']['state'])
        print('Reason:', result['capture'].get('stoppedReason') or result['review'].get('reason', 'none'))
        print('Comparison:', result['comparison']['state'])
        print('RPC requests:', result['currentRunNetworkRequests'])
    else:
        print('Program self-check:', result['casesPassed'], 'cases passed')
    print('Read-only deployment evidence; no source-build verification or signing approval.')
    print('Upload:', args.output.absolute())


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Program check stopped (' + type(exc).__name__ + '); no complete report published.')
