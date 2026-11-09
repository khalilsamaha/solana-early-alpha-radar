#!/usr/bin/env python3
"""Offline successor snapshot/restore rehearsal; no operational backup mode."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import socket
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
        raise ValueError('output-unavailable')
    from successor_recovery_checks import run, CONNECTED_CASES, VERSION
    from successor_execution_cli import checks
    from test_successor_load_snapshot import LoadSnapshotTests
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('network-disabled')):
        snapshot = checks(LoadSnapshotTests)
    if snapshot['casesRun'] == snapshot['casesPassed'] == 7 and not snapshot['failedCases'] and not snapshot['skippedCases']:
        report = run()
    else:
        report = dict(format=VERSION, state='review-required', casesPassed=0, phases=[], executionApproved=False)
    report.update(capturedAt=datetime.now(timezone.utc).isoformat(), realNetworkRequests=0,
        loadSnapshotChecks=snapshot, successorLoadReplayVersion='successor-load-snapshot-1',
        realTransactionsSent=0, userJournalsOpened=False, userPrivateKeysAccessed=False,
        operationalSnapshotCreated=False, activeRestorePerformed=False)
    publish(args.output, report)
    print('State:', report['state'])
    print('Snapshot checks:', snapshot['casesPassed'], '/', 7)
    print('Connected checks:', report['casesPassed'], '/', CONNECTED_CASES)
    print('Send deadline headroom ms:', report.get('headroomAtReturnMs'))
    print('Balance deadline headroom ms:', report.get('balanceHeadroomAtReturnMs'))
    print('Private snapshot fixtures removed:', report.get('privateSnapshotFixturesRemoved', False))
    for row in report['phases']:
        print(row['phase'] + ':', row['elapsedMs'], 'ms; completed:', row['completed'])
    print('Offline only. No operational backup, active restore, real transaction or release.')
    print('Upload this sanitized report only:', args.output.absolute())
    return 0 if report['state'] == 'offline-integration-passed' else 2


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc: raise SystemExit('Successor recovery rehearsal stopped (' + type(exc).__name__ + ').')
