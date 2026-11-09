#!/usr/bin/env python3
"""Offline successor balance checks; no operational action or report import."""
import argparse
from datetime import datetime, timezone
import io
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
        raise ValueError('output-unavailable')
    from test_successor_balance import BalanceTests
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BalanceTests)
    expected = suite.countTestCases()
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('network-disabled')):
        result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    ok = expected > 0 and result.testsRun == expected and result.wasSuccessful() and not result.skipped
    report = dict(format='successor-balance-check-1', capturedAt=datetime.now(timezone.utc).isoformat(),
        state='offline-checks-passed' if ok else 'offline-checks-failed',
        casesExpected=expected, casesRun=result.testsRun,
        failedCases=[test.id() for test, _ in result.errors + result.failures],
        skippedCases=[test.id() for test, _ in result.skipped],
        realNetworkRequests=0, userJournalsOpened=False, userPrivateKeysAccessed=False,
        realTransactionsSent=0, reservationsReleased=False, retiredExposureReleased=False,
        scopedClosureRecorded=False, executionApproved=False,
        evidence='Disposable signed/accounted successor and synthetic finalized five-account balances only')
    publish(args.output, report)
    print('State:', report['state'])
    print('Offline cases run:', report['casesRun'], '; expected:', report['casesExpected'])
    print('No operational journal changes, RPC, user signing, submission or release.')
    print('Upload:', args.output.absolute())
    return 0 if ok else 2


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        raise SystemExit('Successor balance check stopped (' + type(exc).__name__ + ').')
