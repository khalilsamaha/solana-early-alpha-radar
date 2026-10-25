#!/usr/bin/env python3
"""Fixed prepared cycle 2: offline checks, local inspection, explicit devnet legs, read-only recovery."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
import cycle_binding as binding
import swap_submission as submit
sys.path.insert(0, str(submit.bridge.ROOT / 'launch-study'))
from report import publish


@binding.operation
def inspect(home, wallet, pool):
    # Inspection needs public wallet metadata and journals, not the signing key.
    from cycle_preparation import controlled
    with controlled.source_lock(home, wallet) as root:
        child = root / binding.CYCLE
        b = binding.load(child, wallet, pool)
        entry = submit.report(child, wallet); exit_ = submit.report(child, wallet, reverse=True)
        return dict(format='controlled-cycle-execution-1', state='cycle-inspected', cycleId=binding.CYCLE,
                    cycleBinding=b, entry=entry, exit=exit_, networkRequests=0, transactionsSent=0,
                    signaturesCreated=0, privateKeyAccessed=False, mainnetEnabled=False,
                    nextAction='recover-exit' if exit_['submissionBoundaryRecorded'] and exit_['state'] not in submit.TERMINAL
                      else 'recover-entry' if entry['submissionBoundaryRecorded'] and entry['state'] not in submit.TERMINAL
                      else 'entry' if entry['state']=='not-started'
                      else 'exit' if entry['state']=='finalized-success' and exit_['state']=='not-started'
                      else 'review-recorded-state',
                    executionApproved=False, currentWalletBalancesKnown=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('self-check','inspect','entry','exit','status-entry','status-exit','recover-entry','recover-exit'),default='self-check')
    p.add_argument('--directory',type=Path);p.add_argument('--wallet');p.add_argument('--pool')
    p.add_argument('--allow-devnet-submit',action='store_true');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    if a.action=='self-check':
        if any((a.directory,a.wallet,a.pool,a.allow_devnet_submit)):raise ValueError('unexpected-scope')
        import test_cycle_execution
        suite=unittest.defaultTestLoader.loadTestsFromModule(test_cycle_execution)
        r=unittest.TestResult();suite.run(r)
        if not r.wasSuccessful() or r.skipped or r.testsRun!=23:raise ValueError('offline-checks-failed')
        result=dict(format='controlled-cycle-execution-1',state='offline-checks-passed',casesPassed=r.testsRun,
                    publicRpcRequests=0,liveTransactionsSent=0,existingWalletAccessed=False,
                    mode='disposable-unfunded-wallets-synthetic-rpc')
    else:
        if not all((a.directory,a.wallet,a.pool)) or a.allow_devnet_submit != (a.action in ('entry','exit')):
            raise ValueError('explicit-action-and-scope-required')
        if a.action=='inspect': result=inspect(a.directory,a.wallet,a.pool)
        elif a.action in ('entry','exit'):
            fn=submit.execute if a.action=='entry' else submit.execute_reverse
            result=fn(a.directory,a.wallet,a.pool,cycle=True)
        else:
            fn=submit.recover if a.action.startswith('recover') else submit.status
            result=fn(a.directory,a.wallet,cycle=True,reverse=a.action.endswith('exit'),expected_pool=a.pool)
    result['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,result)
    print('State:',result['state'])
    if 'casesPassed' in result:print('Offline cases passed:',result['casesPassed'])
    if 'sendRequestsThisRun' in result: print('Application send requests this run:', result['sendRequestsThisRun'])
    if 'spendingGuard' in result:
        print('Spending state:', result['spendingGuard']['state'])
        print('Cumulative confirmed swap fees:', result['spendingGuard'].get('cumulativeConfirmedFeeLamports', 'unavailable'))
    print('Upload only this public report:',a.output.absolute())
    if a.action in ('entry','exit'):
        print('Do not repeat execution to retry. Use recover-'+a.action+' to observe the recorded signature.')


if __name__=='__main__':
    try:main()
    except Exception as exc:
        safe={'stop-requested','cycle-starting-balances-changed','cycle-plan-binding','cycle-preparation-changed-during-operation',
              'explicit-pool-mismatch','explicit-wallet-mismatch','complete-cycle-preparation-required','offline-checks-failed'}
        reason=str(exc) if type(exc) is ValueError and str(exc) in safe else type(exc).__name__
        raise SystemExit('Controlled cycle stopped ('+reason+'). No automatic retry; preserve all journals and use status/recover after an attempt.')
