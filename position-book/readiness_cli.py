#!/usr/bin/env python3
"""Inspect controlled devnet readiness without network, signing or source changes."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
import readiness
sys.path.insert(0, str(readiness.cycles.c.ROOT / 'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('self-check','inspect'),default='self-check')
    p.add_argument('--directory',type=Path);p.add_argument('--wallet');p.add_argument('--pool')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    if a.action=='self-check':
        if any((a.directory,a.wallet,a.pool)):raise ValueError('unexpected-self-check-scope')
        import test_readiness
        suite=unittest.defaultTestLoader.loadTestsFromModule(test_readiness)
        result=unittest.TestResult();suite.run(result)
        if not result.wasSuccessful() or result.skipped or result.testsRun != 16:raise ValueError('offline-checks-failed')
        report=dict(format=readiness.VERSION,state='offline-checks-passed',casesPassed=result.testsRun,
            existingWalletAccessed=False,publicRpcRequests=0,liveTransactionsSent=0,
            mode='disposable-unfunded-wallets-synthetic-rpc')
    else:
        if not all((a.directory,a.wallet,a.pool)):raise ValueError('explicit-scope-required')
        if a.output.resolve().is_relative_to(a.directory.resolve()):raise ValueError('report-must-be-outside-source-directory')
        report=readiness.inspect(a.directory,a.wallet,a.pool)
    report['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,report)
    print('State:',report['state'])
    if 'casesPassed' in report:print('Offline cases passed:',report['casesPassed'])
    if 'blockingReasons' in report:
        print('Blocking reasons:',report['blockingReasons'])
        print('Unresolved legs:',report['unresolvedLegs'])
        print('Trading approval: false; source state unchanged.')
    print('Upload only this report:',a.output.absolute())
    if report['state']=='review-required':raise SystemExit(2)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        raise SystemExit('Readiness inspection stopped ('+type(exc).__name__+'). No signing or network request. Preserve all journals.')
