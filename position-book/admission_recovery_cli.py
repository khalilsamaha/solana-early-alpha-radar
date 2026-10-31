#!/usr/bin/env python3
"""Private combined evidence capture and isolated verification; no active restore."""
import argparse
from pathlib import Path
import sys
import unittest
import admission_recovery as m
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('self-check','capture','verify'),default='self-check')
    p.add_argument('--directory',type=Path);p.add_argument('--snapshot',type=Path)
    p.add_argument('--wallet');p.add_argument('--pool');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    roots=[root for root in (a.directory,a.snapshot) if root is not None]
    if a.directory is not None:roots.append(a.directory.absolute().with_name(a.directory.name+'-entry-handoff-v1'))
    for root in roots:
        if a.output.resolve().is_relative_to(root.resolve()):raise ValueError('report-must-be-outside-private-state')
    if a.action=='self-check':
        if any((a.directory,a.snapshot,a.wallet,a.pool)):raise ValueError('unexpected-self-check-scope')
        print('Running 19 offline recovery checks; this may take several minutes...',flush=True)
        import test_admission_recovery
        suite=unittest.defaultTestLoader.loadTestsFromModule(test_admission_recovery)
        result=unittest.TestResult();suite.run(result)
        if not result.wasSuccessful() or result.skipped or result.testsRun!=19:raise ValueError('offline-checks-failed')
        report=dict(format=m.VERSION+'-self-check',state='offline-checks-passed',capturedAt=m.backup.stamp(),
            mode='synthetic-offline',casesPassed=result.testsRun,
            cases={test:'passed' for test in sorted(name for name in dir(test_admission_recovery.RecoveryTests) if name.startswith('test_'))},
            disposableSignedFixtures=True,existingWalletAccessed=False,networkRequests=0,transactionsSent=0,
            sourceStateChanged=False,activeRestoreAvailable=False,executionApproved=False,nextCycleAuthorized=False,
            runtimeIntegrated=False,reservationReleased=False,cloudRequests=0,temporaryFixturesRemoved=True)
    else:
        if not all((a.snapshot,a.wallet,a.pool)):raise ValueError('explicit-scope-required')
        if a.action=='capture':
            if a.directory is None:raise ValueError('source-directory-required')
            report=m.capture(a.directory,a.wallet,a.pool,a.snapshot)
        else:
            if a.directory is not None:raise ValueError('verification-never-opens-active-source')
            report=m.verify(a.snapshot,a.wallet,a.pool)
    publish(a.output,report)
    print('State:',report['state'])
    if 'casesPassed' in report:print('Offline cases passed:',report['casesPassed'])
    print('No network, active restore or submitted transaction. Self-check uses disposable signed fixtures.')
    print('Upload only this public report:',a.output.absolute())
    if a.snapshot:print('Keep the private snapshot locally. Do not upload it or its manifest.')


if __name__=='__main__':
    try:main()
    except Exception as exc:
        raise SystemExit('Admission recovery stopped ('+type(exc).__name__+'). Preserve source and incomplete snapshots; no automatic repair or retry.')
