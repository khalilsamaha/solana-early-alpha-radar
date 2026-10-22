#!/usr/bin/env python3
"""Offline intent reconciliation. Default: synthetic cases; never opens a network connection."""
import argparse
import datetime as dt
import gzip
import json
import sys
from pathlib import Path
from reconcile import MAX_BYTES, reconcile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launch-study'))
from report import publish


def unique_object(pairs):
    result = {}
    for k, v in pairs:
        if k in result: raise ValueError('Duplicate JSON key')
        result[k] = v
    return result


def read(path):
    with (gzip.open(path, 'rb') if path.suffix == '.gz' else path.open('rb')) as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES: raise ValueError('Input byte cap')
    return json.loads(raw, object_pairs_hook=unique_object,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    if a.input:
        result = reconcile(read(a.input))
        result['mode'] = 'offline-supplied-evidence'
    else:
        from intent_fixtures import fixture
        bundles = {k: fixture(k) for k in ('existing', 'create', 'close')}
        bundles['failed-with-fee'] = fixture(failed=True)
        bundles['unknown-submission'] = fixture()
        bundles['unknown-submission']['rpcEvidence']['signatureStatus']['result']['value'] = [None]
        bundles['unknown-submission']['rpcEvidence']['transaction']['result'] = None
        bundles['unexpected-wallet-debit'] = fixture()
        bundles['unexpected-wallet-debit']['rpcEvidence']['transaction']['result']['meta']['postBalances'][0] -= 1
        cases = {name: reconcile(bundle) for name, bundle in bundles.items()}
        expected = dict.fromkeys(('existing', 'create', 'close'), 'balance-consistent-with-bound-message')
        expected.update({'failed-with-fee': 'finalized-failure-fee-only', 'unknown-submission': 'unknown', 'unexpected-wallet-debit': 'mismatch'})
        if any(cases[k]['state'] != state for k, state in expected.items()): raise ValueError('Self-check failed')
        result = {'format': 'intent-self-check-1', 'mode': 'synthetic-offline', 'cases': cases,
                  'networkRequests': 0, 'executionApproved': False, 'ledgerUpdated': False}
    result['capturedAt'] = dt.datetime.now(dt.timezone.utc).isoformat()
    publish(a.output, result)
    print('Intent reconciliation:', result.get('state', 'six offline scenarios passed'))
    print('No transactions sent or ledger changed. Upload:', a.output.resolve())


if __name__ == '__main__':
    try: main()
    except Exception as e: raise SystemExit('Intent lab stopped: ' + type(e).__name__)
