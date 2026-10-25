#!/usr/bin/env python3
"""Explicit unsigned cycle-2 recovery; preparation and submission are separate actions."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
import unittest
import unsigned_replacement as replacement
from core import check
s=replacement.c.submit
sys.path.insert(0,str(s.bridge.ROOT/'launch-study'))
from report import publish


@replacement.binding.operation
def status(home,wallet,pool):
    with replacement.c.controlled.source_lock(home,wallet) as root:
        cycle=root/replacement.binding.CYCLE
        replacement.binding.load(cycle,wallet,pool)
        r=replacement.public(cycle)
        r['entry']=s.report(cycle,wallet)
        return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('self-check','prepare','entry','status','recover'),default='self-check')
    p.add_argument('--directory',type=Path);p.add_argument('--wallet');p.add_argument('--pool')
    p.add_argument('--expected-preparation');p.add_argument('--expected-evidence')
    p.add_argument('--allow-unsigned-plan-replacement',action='store_true')
    p.add_argument('--allow-devnet-submit',action='store_true')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    check(not a.output.exists() and not a.output.is_symlink() and a.output.parent.is_dir(),'output-unavailable')
    check(a.allow_unsigned_plan_replacement==(a.action=='prepare') and a.allow_devnet_submit==(a.action=='entry'), 'explicit-action-permission-required')
    check(bool(a.expected_preparation)==(a.action=='prepare') and bool(a.expected_evidence)==(a.action=='prepare'),'explicit-evidence-required')
    if a.action=='self-check':
        check(not any((a.directory,a.wallet,a.pool)),'unexpected-scope')
        import test_unsigned_replacement
        r=unittest.TestResult();unittest.defaultTestLoader.loadTestsFromModule(test_unsigned_replacement).run(r)
        check(r.wasSuccessful() and not r.skipped and r.testsRun==20,'offline-checks-failed')
        result=dict(format=replacement.VERSION,state='offline-checks-passed',casesPassed=r.testsRun,
                    publicRpcRequests=0,liveTransactionsSent=0,existingWalletAccessed=False)
    else:
        check(all((a.directory,a.wallet,a.pool)),'scope-required')
        if a.action=='prepare':
            result=replacement.prepare(a.directory,a.wallet,a.pool,a.expected_preparation,a.expected_evidence)
        elif a.action=='entry':
            result=s.execute(a.directory,a.wallet,a.pool,cycle=True,replace_unsigned=True)
        elif a.action=='status':result=status(a.directory,a.wallet,a.pool)
        else:result=s.recover(a.directory,a.wallet,cycle=True,expected_pool=a.pool)
    result['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,result)
    print('State:',result['state'])
    if 'casesPassed' in result:print('Offline cases passed:',result['casesPassed'])
    if 'sendRequestsThisRun' in result:print('Application send requests this run:',result['sendRequestsThisRun'])
    if 'spendingGuard' in result:print('Cumulative confirmed fees:',result['spendingGuard'].get('cumulativeConfirmedFeeLamports'))
    print('Upload only this public report:',a.output.absolute())
    if a.action=='entry':print('Do not repeat entry to retry. Use recover to observe its recorded signature.')


if __name__=='__main__':
    try:main()
    except Exception:
        raise SystemExit('Unsigned cycle recovery stopped. Preserve every journal; no automatic retry is enabled.')
