#!/usr/bin/env python3
"""Default offline checks; explicit one-send devnet token setup; status and read-only recovery."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
from pair_workflow import ROOT, execute, recover, status
sys.path.insert(0,str(ROOT/'launch-study'))
from report import publish


def self_check():
    import unittest
    import test_pair
    suite=unittest.defaultTestLoader.loadTestsFromModule(test_pair)
    names=[]
    def walk(s):
        for t in s:
            if isinstance(t,unittest.TestSuite):walk(t)
            else:names.append(t.id().split('.')[-1])
    walk(suite);result=unittest.TestResult();suite.run(result)
    if not result.wasSuccessful() or result.testsRun!=len(names) or result.skipped:
        raise ValueError('Offline token pair self-check failed')
    return dict(format='devnet-token-pair-self-check-1',state='offline-checks-passed',
                casesPassed=result.testsRun,cases=names,mode='disposable-unfunded-wallets-synthetic-rpc',
                publicRpcRequests=0,liveTransactionsSent=0,existingWalletAccessed=False,
                syntheticSendsExercised=True,executionApproved=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('self-check','execute','recover','status'),default='self-check')
    p.add_argument('--wallet');p.add_argument('--directory',type=Path)
    p.add_argument('--allow-devnet-submit',action='store_true');p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('Output unavailable')
    if a.action=='self-check':
        if any((a.wallet,a.directory,a.allow_devnet_submit)):raise ValueError('Unexpected self-check arguments')
        result=self_check()
    else:
        if not a.wallet or not a.directory or (a.action=='execute')!=a.allow_devnet_submit:raise ValueError('Explicit action arguments required')
        result={'execute':execute,'recover':recover,'status':status}[a.action](a.directory,a.wallet)
    result['capturedAt']=datetime.now(timezone.utc).isoformat()
    publish(a.output,result)
    print('State:',result['state'])
    if 'casesPassed' in result:print('Offline cases passed:',result['casesPassed'])
    if 'sendRequestsThisRun' in result:print('Application send requests this run:',result['sendRequestsThisRun'])
    if result.get('setupPairVerified'):
        print('Two test mints and holder balances verified; mint and freeze authorities are absent. No pool created.')
    print('Upload only this public report:',a.output.absolute())
    if a.action=='execute':print('Do not repeat execute to retry. Use recover or status; never delete setup state.')


if __name__=='__main__':
    try:main()
    except Exception as exc:
        raise SystemExit('Test token pair stopped ('+type(exc).__name__+'). Use status/recover after an execution attempt; no automatic retry.')
