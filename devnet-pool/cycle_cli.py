#!/usr/bin/env python3
"""Offline checks or bounded read-only-chain preparation for one subsequent devnet cycle."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
import cycle_preparation as c
sys.path.insert(0, str(c.submit.bridge.ROOT / 'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('self-check','status','prepare'),default='self-check')
    p.add_argument('--directory',type=Path);p.add_argument('--wallet');p.add_argument('--pool')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('Output unavailable')
    if a.action=='self-check':
        if any((a.directory,a.wallet,a.pool)):raise ValueError('Unexpected scope')
        import test_cycle_preparation
        suite=unittest.defaultTestLoader.loadTestsFromModule(test_cycle_preparation)
        result=unittest.TestResult();suite.run(result)
        if result.testsRun!=18 or not result.wasSuccessful() or result.skipped:raise ValueError('Offline checks failed')
        r=dict(c.public('offline-checks-passed'),casesPassed=result.testsRun,
               existingWalletAccessed=False,disposableKeysUsed=True,publicRpcRequests=0,
               mode='disposable-unfunded-wallets-synthetic-rpc')
    else:
        if not all((a.directory,a.wallet,a.pool)):raise ValueError('Explicit scope required')
        r=c.run(a.directory,a.wallet,a.pool,prepare=a.action=='prepare')
    r['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,r)
    print('State:',r['state'])
    if 'casesPassed' in r:print('Offline cases passed:',r['casesPassed'])
    if 'budget' in r:
        print('Historical swap fee lamports:',r['budget']['historicalSwapFeeLamports'])
        print('Cumulative fee allocation lamports:',r['budget']['cumulativeSwapFeesWithAllocationLamports'])
    print('No signing or submission. Preparation is not execution approval.')
    print('Upload only this public report:',a.output.absolute())


if __name__=='__main__':
    try:main()
    except Exception as exc:
        # No raw provider response, path, signed bytes or private key is printed.
        safe={'prior-round-trip-not-closed','prior-position-not-closed','historical-ledger-not-reconciled',
              'prior-spending-not-reconciled','wrong-cluster','historical-finality-unavailable',
              'historical-transaction-unavailable','historical-chain-receipt-mismatch',
              'wallet-balance-changed-since-close','token-balance-changed-since-close',
              'token-authority-changed-since-close','next-cycle-funding-required','balance-observation-expired',
              'stop-requested','cycle-source-or-policy-changed','cycle-seal-mismatch','cumulative-budget-exceeded'}
        reason=str(exc) if type(exc) is ValueError and str(exc) in safe else type(exc).__name__
        raise SystemExit('Cycle preparation stopped ('+reason+'). No transaction sent. Preserve all journals.')
