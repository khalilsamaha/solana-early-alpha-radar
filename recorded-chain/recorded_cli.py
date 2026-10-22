#!/usr/bin/env python3
"""Verify a recorded transaction. Explicit --sample-devnet makes at most six public reads."""
import argparse
import datetime as dt
import gzip
from pathlib import Path
import sys

from recorded_capture import collect, loads, MAX_CAPTURE
from review import review
from recorded_checks import self_check
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launch-study'))
from report import publish


def read(path):
    with (gzip.open(path, 'rb') if path.suffix == '.gz' else path.open('rb')) as stream:
        raw = stream.read(MAX_CAPTURE + 1)
    if len(raw) > MAX_CAPTURE: raise ValueError('Capture byte cap')
    value = loads(raw)
    if isinstance(value, dict) and value.get('format') == 'recorded-chain-report-1': return value['capture']
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sample-devnet', action='store_true')
    p.add_argument('--network', choices=('devnet', 'mainnet-beta'))
    p.add_argument('--signature')
    p.add_argument('--input', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    explicit = bool(a.network or a.signature)
    if sum((a.sample_devnet, explicit, bool(a.input))) > 1: p.error('Choose one mode')
    if explicit and not (a.network and a.signature): p.error('Both network and public signature required')
    # Avoid network calls when the required exclusive output is already occupied.
    if a.output.exists() or a.output.is_symlink(): raise ValueError('Output already exists')
    if a.sample_devnet or explicit or a.input:
        c = read(a.input) if a.input else collect('devnet' if a.sample_devnet else a.network,
                                                 a.signature, sample=a.sample_devnet)
        result = {'format': 'recorded-chain-report-1', 'mode': 'offline-replay' if a.input else 'public-rpc-read-only',
            'capture': c, 'review': review(c), 'currentRunNetworkRequests': 0 if a.input else c['rpcRequestsAttempted'],
            'transactionsSent': 0, 'executionApproved': False, 'ledgerUpdated': False}
    else:
        result = self_check()
    result['capturedAt'] = dt.datetime.now(dt.timezone.utc).isoformat()
    publish(a.output, result)
    check = result.get('review', {})
    print('Recorded-chain check:', check.get('state', str(result.get('casesPassed')) + ' synthetic cases passed'))
    if check.get('reason'): print('Reason:', check['reason'])
    print('Public requests this run:', result.get('currentRunNetworkRequests', 0))
    print('No transaction sent or intent registered. Upload:', a.output.resolve())


if __name__ == '__main__':
    try: main()
    except Exception as e: raise SystemExit('Recorded-chain check stopped: ' + type(e).__name__)
