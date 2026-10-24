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
    p.add_argument('--action',choices=('self-check','status','prepare','prepare-funded','diagnose'),default='self-check')
    p.add_argument('--directory',type=Path);p.add_argument('--wallet');p.add_argument('--pool')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('Output unavailable')
    if a.action=='self-check':
        if any((a.directory,a.wallet,a.pool)):raise ValueError('Unexpected scope')
        import test_cycle_preparation, test_funding_reconciliation
        suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m)
                                 for m in (test_cycle_preparation, test_funding_reconciliation))
        result=unittest.TestResult();suite.run(result)
        if result.testsRun!=45 or not result.wasSuccessful() or result.skipped:raise ValueError('Offline checks failed')
        r=dict(c.public('offline-checks-passed'),casesPassed=result.testsRun,
               existingWalletAccessed=False,disposableKeysUsed=True,publicRpcRequests=0,
               mode='disposable-unfunded-wallets-synthetic-rpc')
    else:
        if not all((a.directory,a.wallet,a.pool)):raise ValueError('Explicit scope required')
        r=(c.diagnose(a.directory,a.wallet,a.pool) if a.action=='diagnose'
           else c.run(a.directory,a.wallet,a.pool,prepare=a.action in ('prepare','prepare-funded'), reconcile_funding=a.action=='prepare-funded'))
    r['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,r)
    print('State:',r['state'])
    if 'casesPassed' in r:print('Offline cases passed:',r['casesPassed'])
    if 'budget' in r:
        print('Historical swap fee lamports:',r['budget']['historicalSwapFeeLamports'])
        print('Cumulative fee allocation lamports:',r['budget']['cumulativeSwapFeesWithAllocationLamports'])
    if 'fundingReconciliation' in r:
        print('Verified external credit lamports:', r['fundingReconciliation']['externalCreditLamports'])
        print('Historical spending and cycle allowance unchanged.')
    if 'comparison' in r:
        native=r['comparison']['nativeLamports']
        print('Expected / observed native lamports:',native['expected'],'/',native['observed'])
        print('Native difference:',native['delta'],'lamports =',native['deltaDevnetSol'],'devnet SOL')
        print('Cause established: false; no balance override or journal change.')
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
        reason=str(exc) if type(exc) is ValueError and str(exc) in safe | c.funding.SAFE_ERRORS else type(exc).__name__
        raise SystemExit('Cycle preparation stopped ('+reason+'). No transaction sent. Preserve all journals.')
