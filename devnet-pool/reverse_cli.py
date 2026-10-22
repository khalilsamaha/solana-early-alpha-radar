#!/usr/bin/env python3
"""Offline checks, one receipt-bound reverse devnet swap, or read-only status/recovery."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from swap_submission import execute_reverse, inspect_reverse, recover, status
from controlled_swap import ROOT
sys.path.insert(0, str(ROOT / 'launch-study'))
from report import publish


def self_check():
    import unittest
    import test_reverse_swap
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_reverse_swap)
    count = suite.countTestCases()
    result = unittest.TestResult()
    suite.run(result)
    if not result.wasSuccessful() or result.testsRun != count or result.skipped:
        raise ValueError('Reverse swap offline checks failed')
    return dict(format='controlled-pool-reverse-self-check-1', state='offline-checks-passed',
                casesPassed=count, publicRpcRequests=0, liveTransactionsSent=0,
                existingWalletAccessed=False, mode='disposable-unfunded-wallets-synthetic-rpc')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action', choices=('self-check', 'inspect', 'execute', 'status', 'recover'), default='self-check')
    p.add_argument('--directory', type=Path)
    p.add_argument('--wallet')
    p.add_argument('--pool')
    p.add_argument('--allow-devnet-submit', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('Output unavailable')
    if a.action == 'self-check':
        if any((a.directory, a.wallet, a.pool, a.allow_devnet_submit)):
            raise ValueError('Unexpected self-check arguments')
        r = self_check()
    else:
        if not a.directory or not a.wallet or (a.action == 'execute') != a.allow_devnet_submit:
            raise ValueError('Explicit action arguments required')
        if a.action in ('execute', 'inspect'):
            if not a.pool:
                raise ValueError('Explicit pool required')
            r = (execute_reverse if a.action == 'execute' else inspect_reverse)(a.directory, a.wallet, a.pool)
        else:
            if a.pool:
                raise ValueError('Recovery/status uses recorded scope')
            r = {'status': status, 'recover': recover}[a.action](a.directory, a.wallet, reverse=True)
    r['capturedAt'] = datetime.now(timezone.utc).isoformat()
    publish(a.output, r)
    print('State:', r['state'])
    if 'casesPassed' in r:
        print('Offline cases passed:', r['casesPassed'])
    if 'sendRequestsThisRun' in r:
        print('Application send requests this run:', r['sendRequestsThisRun'])
    if 'scope' in r:
        print('Receipt-bound input atomic:', r['scope']['amountIn'])
        print('Fixed test minimum output atomic:', r['scope']['minimumAmountOut'])
    if 'roundTrip' in r:
        t = r['roundTrip']
        print('Round trip:', t['state'])
        print('Original token net atomic:', t['netOriginalTokenAtomic'])
        print('Acquired token residual atomic:', t['residualAcquiredTokenAtomic'])
        print('Total native fee lamports:', t['totalFeeLamports'])
    print('Upload only this public report:', a.output.absolute())
    if a.action == 'execute':
        print('Do not repeat execute to retry. Use recover for the recorded signature; preserve all private journals.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Controlled reverse devnet swap stopped (' + type(exc).__name__ +
                         '). No automatic retry. Use status/recover after an execution attempt.')
