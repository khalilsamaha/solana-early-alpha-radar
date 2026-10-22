#!/usr/bin/env python3
"""Offline checks, repeatable funding inspection, explicit one-send devnet pool initialization."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
from pool_workflow import ROOT,inspect,execute,recover,status
sys.path.insert(0,str(ROOT/'launch-study'))
from report import publish


def self_check():
    import unittest
    import test_pool
    suite=unittest.defaultTestLoader.loadTestsFromModule(test_pool);names=[]
    def walk(s):
        for t in s:
            if isinstance(t,unittest.TestSuite):walk(t)
            else:names.append(t.id().split('.')[-1])
    walk(suite);r=unittest.TestResult();suite.run(r)
    if not r.wasSuccessful() or r.testsRun!=len(names) or r.skipped:raise ValueError('Pool offline checks failed')
    return dict(format='devnet-pool-self-check-1',state='offline-checks-passed',casesPassed=r.testsRun,cases=names,
       mode='disposable-unfunded-wallets-synthetic-rpc',publicRpcRequests=0,liveTransactionsSent=0,
       existingWalletAccessed=False,syntheticSendsExercised=True,executionApproved=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('self-check','inspect','execute','recover','status'),default='self-check')
    p.add_argument('--wallet');p.add_argument('--directory',type=Path);p.add_argument('--allow-devnet-submit',action='store_true')
    p.add_argument('--allow-unsigned-size-replacement',action='store_true')
    p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.allow_unsigned_size_replacement and a.action!='execute':raise ValueError('Unsigned replacement requires execute')
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('Output unavailable')
    if a.action=='self-check':
        if any((a.wallet,a.directory,a.allow_devnet_submit)):raise ValueError('Unexpected self-check arguments')
        r=self_check()
    else:
        if not a.wallet or not a.directory or (a.action=='execute')!=a.allow_devnet_submit:raise ValueError('Explicit action arguments required')
        if a.action=='execute':r=execute(a.directory,a.wallet,allow_replace_unsigned=a.allow_unsigned_size_replacement)
        else:r={'inspect':inspect,'recover':recover,'status':status}[a.action](a.directory,a.wallet)
    r['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,r)
    print('State:',r['state'])
    if 'casesPassed' in r:print('Offline cases passed:',r['casesPassed'])
    if 'fundingSufficient' in r:
        print('Required including fee reserve:',r['estimatedRequiredLamports'],'lamports')
        print('Funding shortfall:',r['estimatedShortfallLamports'],'devnet lamports')
    if 'sendRequestsThisRun' in r:print('Application send requests this run:',r['sendRequestsThisRun'])
    if r.get('controlledPoolVerified'):print('Controlled devnet pool, reserves and LP tokens verified. No swap executed.')
    print('Upload only this public report:',a.output.absolute())
    if a.action=='execute':print('If a pool journal was created, do not repeat execute. Use recover/status; never delete setup state.')


if __name__=='__main__':
    try:main()
    except Exception as e:raise SystemExit('Devnet pool stopped ('+type(e).__name__+'). No automatic retry; use status/recover after an execution attempt.')
