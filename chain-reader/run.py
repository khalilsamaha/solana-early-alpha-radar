#!/usr/bin/env python3
"""Offline fixture check by default; explicit public identifiers required for live reads."""
import argparse
import datetime as dt
import sys
from pathlib import Path
from reader import fetch, reconcile, ENDPOINTS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launch-study'))
from report import publish


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--network', choices=ENDPOINTS)
    p.add_argument('--signature')
    p.add_argument('--wallet')
    p.add_argument('--mint')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    public = (a.signature, a.wallet, a.mint)
    if a.network:
        if not all(public):
            raise ValueError('Live read requires signature, public wallet, and mint')
        # Validate all public identifiers before either RPC request.
        from reader import base58
        for value, size in zip(public, (64, 32, 32)):
            base58(value, size)
        result = reconcile(fetch(a.network, a.signature), *public)
        result.update(mode='public-rpc-read-only', network=a.network, rpcRequestsAttempted=2)
    else:
        if any(public):
            raise ValueError('Public identifiers require an explicit network')
        from fixtures import fixture, SIGNATURE, WALLET, MINT
        import copy
        good = fixture()
        absent = copy.deepcopy(good)
        absent['signatureStatus']['result']['value'] = [None]
        absent['transaction']['result'] = None
        result = {'format': 'chain-reader-self-check-1', 'mode': 'synthetic-offline', 'rpcRequestsAttempted': 0,
                  'executionApproved': False, 'cases': [reconcile(b, SIGNATURE, WALLET, MINT) for b in (good, absent)]}
        if [c['state'] for c in result['cases']] != ['finalized-success', 'not-found-unknown']:
            raise ValueError('Self-check failed')
    result['capturedAt'] = dt.datetime.now(dt.timezone.utc).isoformat()
    publish(a.output, result)
    print('Chain evidence:', result.get('state', 'offline self-check passed'))
    print('No transaction sent or ledger changed. Upload:', a.output.resolve())


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        raise SystemExit('Chain reader stopped: ' + type(e).__name__)
