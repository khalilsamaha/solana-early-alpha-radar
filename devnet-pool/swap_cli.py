#!/usr/bin/env python3
"""Inspect fixed controlled-pool scope, explicitly sign/simulate once, or read status."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from controlled_swap import ROOT, inspect, simulate, status
sys.path.insert(0, str(ROOT / 'launch-study'))
from report import publish


def self_check():
    import unittest
    import test_controlled_swap
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_controlled_swap)
    count = suite.countTestCases()
    result = unittest.TestResult()
    suite.run(result)
    if not result.wasSuccessful() or result.testsRun != count or result.skipped:
        raise ValueError('Controlled swap offline checks failed')
    return dict(format='controlled-pool-swap-self-check-1', state='offline-checks-passed',
                casesPassed=count, publicRpcRequests=0, liveTransactionsSent=0,
                existingWalletAccessed=False, mode='disposable-unfunded-wallets-synthetic-rpc')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action', choices=('self-check', 'inspect', 'simulate', 'status'), default='self-check')
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--wallet')
    parser.add_argument('--pool')
    parser.add_argument('--allow-devnet-sign', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('Output unavailable')
    if a.action == 'self-check':
        if any((a.directory, a.wallet, a.pool, a.allow_devnet_sign)):
            raise ValueError('Unexpected self-check arguments')
        result = self_check()
    else:
        if not a.directory or not a.wallet or (a.action == 'simulate') != a.allow_devnet_sign:
            raise ValueError('Explicit action arguments required')
        if a.action == 'status':
            if a.pool:
                raise ValueError('Status does not select a pool')
            result = status(a.directory, a.wallet)
        else:
            if not a.pool:
                raise ValueError('Explicit pool required')
            result = {'inspect': inspect, 'simulate': simulate}[a.action](a.directory, a.wallet, a.pool)
    result['capturedAt'] = datetime.now(timezone.utc).isoformat()
    publish(a.output, result)
    print('State:', result['state'])
    if 'casesPassed' in result:
        print('Offline cases passed:', result['casesPassed'])
    if 'scope' in result:
        print('Test token input: 0.001; minimum output: 0.000990; zero priority fee.')
    print('No swap broadcast. Upload only this public report:', a.output.absolute())
    if a.action == 'simulate':
        print('Do not repeat simulate to retry. Use status; keep the private journals intact.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Controlled swap stopped (' + type(exc).__name__ +
                         '). No automatic retry. Use status after a simulation attempt.')
