#!/usr/bin/env python3
"""Offline successor signing handoff checks; disposable keys, no live actions."""
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
    from test_successor_signing_handoff import SuccessorSigningTests
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SuccessorSigningTests)
    with patch.object(socket.socket,'connect',side_effect=AssertionError('network-disabled')):
        result=unittest.TextTestRunner(stream=io.StringIO(),verbosity=0).run(suite)
    passed=result.wasSuccessful() and result.testsRun>0 and not result.skipped
    report=dict(format='successor-signing-handoff-check-1',capturedAt=datetime.now(timezone.utc).isoformat(),
        state='offline-checks-passed' if passed else 'offline-checks-failed',casesRun=result.testsRun,
        casesPassed=max(0,result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped)),
        failedCases=[test.id() for test,_ in result.errors+result.failures],skippedCases=[test.id() for test,_ in result.skipped],
        evidence='real retired-source replay, separate durable signing journal, disposable Ed25519 signatures and synthetic RPC',
        userJournalsOpened=False,userPrivateKeysAccessed=False,ephemeralTestKeysCreated=True,
        networkRequests=0,transactionsSent=0,liveKeyBackendConnected=False,liveSenderConnected=False,
        scannerRuntimeChanged=False,executionApproved=False,
        limitations=['No live successor preparation, private-key backend or sender is exposed.',
            'A committed unknown boundary never permits automatic re-signing.',
            'Existing retired evidence and all original fee and inventory holds remain.',
            'This offline report does not establish full live signing or submission timing.'])
    publish(args.output,report)
    print('State:',report['state']);print('Offline cases passed:',report['casesPassed'])
    print('Disposable test keys only; no user wallet, network or runtime changes.')
    print('Upload:',args.output.absolute())
    if not passed:print('Run test_successor_signing_handoff.py locally for detailed test failures.')
    return 0 if passed else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:raise SystemExit('Offline successor signing check stopped ('+type(exc).__name__+').')
