#!/usr/bin/env python3
"""Offline complete successor signing rehearsal; no wallet or execution arguments."""
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


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    from test_successor_signing_integration import IntegrationTests
    from successor_signing_rehearsal import run
    from test_successor_fixture_setup import FixtureSetupTests
    from test_successor_backend_replay import BackendReplayTests
    with patch.object(socket.socket,'connect',side_effect=AssertionError('network-disabled')):
        setup_tests=unittest.TextTestRunner(stream=io.StringIO(),verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(FixtureSetupTests))
        replay_tests=unittest.TextTestRunner(stream=io.StringIO(),verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(BackendReplayTests))
        tests=unittest.TextTestRunner(stream=io.StringIO(),verbosity=0).run(unittest.defaultTestLoader.loadTestsFromTestCase(IntegrationTests))
    faults=dict(casesRun=tests.testsRun,casesPassed=max(0,tests.testsRun-len(tests.errors)-len(tests.failures)-len(tests.skipped)),
        failedCases=[t.id() for t,_ in tests.errors+tests.failures],skippedCases=[t.id() for t,_ in tests.skipped])
    fixture_checks=dict(casesRun=setup_tests.testsRun,
        casesPassed=max(0,setup_tests.testsRun-len(setup_tests.errors)-len(setup_tests.failures)-len(setup_tests.skipped)),
        failedCases=[t.id() for t,_ in setup_tests.errors+setup_tests.failures],
        skippedCases=[t.id() for t,_ in setup_tests.skipped])
    replay_checks=dict(casesRun=replay_tests.testsRun,
        casesPassed=max(0,replay_tests.testsRun-len(replay_tests.errors)-len(replay_tests.failures)-len(replay_tests.skipped)),
        failedCases=[t.id() for t,_ in replay_tests.errors+replay_tests.failures],
        skippedCases=[t.id() for t,_ in replay_tests.skipped])
    if all(t.wasSuccessful() and not t.skipped for t in (tests,setup_tests,replay_tests)):r=run()
    else:r=dict(format='successor-signing-rehearsal-1',state='review-required',casesPassed=0,phases=[],
        realNetworkRequests=0,transactionsSent=0,productionWalletAccessed=False,executionApproved=False)
    r['capturedAt']=datetime.now(timezone.utc).isoformat();r['boundaryChecks']=faults;r['fixtureSetupChecks']=fixture_checks;r['backendReplayChecks']=replay_checks
    publish(a.output,r)
    print('State:',r['state']);print('Fixture setup checks:',fixture_checks['casesPassed'])
    print('Backend replay checks:',replay_checks['casesPassed'])
    print('Boundary checks:',faults['casesPassed']);print('Connected checks:',r['casesPassed'])
    if r.get('integration'):
        print('Integration elapsed ms:',r['integrationElapsedMs']);print('Original deadline headroom ms:',r['headroomAtReturnMs'])
    for row in r['phases']:
        print(row['phase']+':',row['elapsedMs'],'ms; completed:',row['completed'])
        if not row['completed']:print('Diagnostic:',row.get('diagnosticCode','unclassified'))
    print('Offline only: temporary ledgers, disposable keys, synthetic providers; no transaction or runtime change.')
    print('Upload:',a.output.absolute())
    return 0 if r['state']=='offline-integration-passed' else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:raise SystemExit('Successor rehearsal stopped ('+type(exc).__name__+').')
