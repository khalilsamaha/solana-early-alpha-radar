#!/usr/bin/env python3
"""Offline successor submission checks; disposable keys and synthetic transport only."""
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
        raise ValueError('output-unavailable')
    from test_successor_submission import SuccessorSubmissionTests
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SuccessorSubmissionTests)
    with patch.object(socket.socket,'connect',side_effect=AssertionError('network-disabled')):
        result=unittest.TextTestRunner(stream=io.StringIO(),verbosity=0).run(suite)
    passed=result.wasSuccessful() and result.testsRun>0 and not result.skipped
    report=dict(format='successor-submission-check-1',capturedAt=datetime.now(timezone.utc).isoformat(),
        state='offline-checks-passed' if passed else 'offline-checks-failed',casesRun=result.testsRun,
        casesPassed=max(0,result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped)),
        failedCases=[test.id() for test,_ in result.errors+result.failures],skippedCases=[test.id() for test,_ in result.skipped],
        evidence='real retired-source replay, durable one-send boundary, disposable signatures and synthetic RPC recovery',
        userJournalsOpened=False,userPrivateKeysAccessed=False,ephemeralTestKeysCreated=True,
        networkRequests=0,transactionsSent=0,liveKeyBackendConnected=False,liveSenderConnected=False,
        scannerRuntimeChanged=False,executionApproved=False,
        limitations=['Only an offline CLI is exposed; internal transport requires an injected adapter.',
            'A committed send boundary never permits a second application send or re-signing.',
            'Existing retired evidence and all original fee and inventory holds remain.',
            'Finalized RPC claims do not settle balances, release holds or prove live timing.'])
    publish(args.output,report)
    print('State:',report['state']);print('Offline cases passed:',report['casesPassed'])
    print('Disposable test keys only; no user wallet, network or runtime changes.')
    print('Upload:',args.output.absolute())
    if not passed:print('Run test_successor_submission.py locally for detailed test failures.')
    return 0 if passed else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:raise SystemExit('Offline successor submission check stopped ('+type(exc).__name__+').')
