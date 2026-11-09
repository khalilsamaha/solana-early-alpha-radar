#!/usr/bin/env python3
"""Offline successor receipt/accounting/balance integration; no live mode."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import socket
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish
from successor_execution_cli import checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
        raise ValueError('output-unavailable')
    from test_successor_accounting import AccountingTests
    from test_successor_balance import BalanceTests
    from successor_completion_checks import run, VERSION, CONNECTED_CASES
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('network-disabled')):
        accounting = checks(AccountingTests); balances = checks(BalanceTests)
        accepted = all(row['casesRun'] == row['casesPassed'] == expected and not row['failedCases'] and
            not row['skippedCases'] for row, expected in ((accounting, 13), (balances, 9)))
        report = run() if accepted else dict(format=VERSION, state='review-required', casesPassed=0,
            casesExpected=CONNECTED_CASES, phases=[], executionApproved=False)
    report.update(capturedAt=datetime.now(timezone.utc).isoformat(), accountingChecks=accounting,
        balanceChecks=balances, realNetworkRequests=0, realTransactionsSent=0,
        userJournalsOpened=False, userPrivateKeysAccessed=False)
    publish(args.output, report)
    print('State:', report['state'])
    print('Accounting checks:', accounting['casesPassed'], '/ 13')
    print('Balance checks:', balances['casesPassed'], '/ 9')
    print('Connected checks:', report['casesPassed'], '/', CONNECTED_CASES)
    print('Send deadline headroom ms:', report.get('headroomAtReturnMs'))
    print('Balance deadline headroom ms:', report.get('balanceHeadroomAtReturnMs'))
    for row in report['phases']:
        print(row['phase'] + ':', row['elapsedMs'], 'ms; completed:', row['completed'])
    print('Offline only: temporary journals, disposable keys, synthetic RPC; retired exposure stays held.')
    print('Upload:', args.output.absolute())
    return 0 if report['state'] == 'offline-integration-passed' else 2


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc: raise SystemExit('Successor completion rehearsal stopped (' + type(exc).__name__ + ').')
