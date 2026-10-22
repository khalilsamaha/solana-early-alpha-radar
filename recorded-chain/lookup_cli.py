#!/usr/bin/env python3
"""Audit lookup account bytes for an existing capture; explicit --live permits three public reads."""
import argparse
import datetime as dt
import gzip
from pathlib import Path

from recorded_capture import loads, MAX_CAPTURE
from recorded_cli import read, publish
from lookup import collect_lookups, review_lookups


def main():
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--live', action='store_true')
    group.add_argument('--replay', type=Path)
    p.add_argument('--input', type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    if bool(a.input) != a.live: p.error('--input is required only with --live')
    if a.output.exists() or a.output.is_symlink(): raise ValueError('Output already exists')
    if a.live:
        source = read(a.input)
        capture = collect_lookups(source)
    else:
        with (gzip.open(a.replay, 'rb') if a.replay.suffix == '.gz' else a.replay.open('rb')) as f:
            raw = f.read(MAX_CAPTURE + 1)
        if len(raw) > MAX_CAPTURE: raise ValueError('Input cap')
        data = loads(raw)
        if data['format'] != 'lookup-report-1': raise ValueError('Report format')
        source, capture = data['sourceCapture'], data['lookupCapture']
    result = {'format': 'lookup-report-1', 'mode': 'public-rpc-read-only' if a.live else 'offline-replay',
        'sourceCapture': source, 'lookupCapture': capture, 'review': review_lookups(source, capture),
        'currentRunNetworkRequests': capture['rpcRequestsAttempted'] if a.live else 0,
        'transactionsSent': 0, 'executionApproved': False, 'ledgerUpdated': False,
        'capturedAt': dt.datetime.now(dt.timezone.utc).isoformat()}
    publish(a.output, result)
    print('Lookup check:', result['review']['state'], result['review']['reason'] or '')
    print('Public requests this run:', result['currentRunNetworkRequests'])
    print('Historical state is not proven. No transaction sent. Upload:', a.output.resolve())


if __name__ == '__main__':
    try: main()
    except Exception as e: raise SystemExit('Lookup check stopped: ' + type(e).__name__)
