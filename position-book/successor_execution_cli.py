#!/usr/bin/env python3
"""Offline combined successor collection/sign/send rehearsal; no execution mode."""
import argparse
from datetime import datetime,timezone
import io
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def checks(cls):
    result=unittest.TextTestRunner(stream=io.StringIO(),verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
    return dict(casesRun=result.testsRun,casesPassed=max(0,result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped)),
        failedCases=[test.id() for test,_ in result.errors+result.failures],skippedCases=[test.id() for test,_ in result.skipped])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    from test_successor_execution import ExecutionTests
    from test_successor_fixture_setup import FixtureSetupTests
    from test_successor_scope_ownership import ScopeOwnershipTests
    from successor_execution_checks import run,VERSION
    with patch.object(socket.socket,'connect',side_effect=AssertionError('network-disabled')):
        setup=checks(FixtureSetupTests);faults=checks(ExecutionTests);ownership=checks(ScopeOwnershipTests)
    if all(t['casesRun']>0 and t['casesRun']==t['casesPassed'] and not t['failedCases'] and not t['skippedCases'] for t in (setup,faults,ownership)):
        report=run()
    else:report=dict(format=VERSION,state='review-required',casesPassed=0,phases=[],realNetworkRequests=0,transactionsSent=0,executionApproved=False)
    report.update(capturedAt=datetime.now(timezone.utc).isoformat(),fixtureSetupChecks=setup,boundaryChecks=faults,scopeOwnershipChecks=ownership,
        computationScopeVersion='successor-computation-owner-1')
    publish(a.output,report)
    print('State:',report['state']);print('Setup checks:',setup['casesPassed']);print('Boundary checks:',faults['casesPassed']);print('Scope ownership checks:',ownership['casesPassed']);print('Connected checks:',report['casesPassed'])
    result=report.get('integration')
    if result:
        print('Combined integration elapsed ms:',report['integrationElapsedMs'])
        print('Original deadline headroom ms:',report['headroomAtReturnMs'])
        print('Synthetic send requests:',result['sendRequestsThisRun'])
        print('Integration state:',result['state']);print('Integration diagnostic:',result['diagnosticCode'])
    for row in report['phases']:
        print(row['phase']+':',row['elapsedMs'],'ms; completed:',row['completed'])
        if not row['completed']:print('Diagnostic:',row.get('diagnosticCode','unclassified'))
    print('Offline only: disposable keys, temporary ledgers and synthetic RPC. No real transaction or runtime change.')
    print('Upload:',a.output.absolute())
    return 0 if report['state']=='offline-integration-passed' else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:raise SystemExit('Successor execution rehearsal stopped ('+type(exc).__name__+').')
