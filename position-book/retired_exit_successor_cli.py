#!/usr/bin/env python3
"""Offline unsigned-successor contract checks; no live source arguments."""
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
    from test_retired_exit_successor import SuccessorTests
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SuccessorTests)
    stream=io.StringIO()
    with patch.object(socket.socket,'connect',side_effect=AssertionError('network-disabled')):
        result=unittest.TextTestRunner(stream=stream,verbosity=0).run(suite)
    passed=result.wasSuccessful() and result.testsRun>0 and not result.skipped
    report=dict(format='retired-exit-successor-offline-check-1',
        capturedAt=datetime.now(timezone.utc).isoformat(),
        state='offline-checks-passed' if passed else 'offline-checks-failed',
        casesRun=result.testsRun,casesPassed=max(0,result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped)),
        failedCases=[test.id() for test,_ in result.errors+result.failures],
        skippedCases=[test.id() for test,_ in result.skipped],
        evidence='disposable synthetic journals and provider responses',
        userJournalsOpened=False,networkRequests=0,privateKeysAccessed=False,
        transactionsSent=0,liveCollectorConnected=False,liveSignerConnected=False,
        liveSenderConnected=False,scannerRuntimeChanged=False,
        limitations=['Offline contract validation is not live successor preparation or execution approval.',
                    'The retired sender remains denied and every original hold stays in place.',
                    'Live collection and successor signing require separate implementations.'])
    publish(args.output,report)
    print('State:',report['state']);print('Offline cases passed:',report['casesPassed'])
    print('No user journals, network, signing, submission or runtime changes.')
    print('Upload:',args.output.absolute())
    if not passed:print('Run test_retired_exit_successor.py locally for detailed test failures.')
    return 0 if passed else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:raise SystemExit('Offline successor check stopped ('+type(exc).__name__+').')
