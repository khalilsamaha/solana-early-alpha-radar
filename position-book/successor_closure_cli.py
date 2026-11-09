#!/usr/bin/env python3
"""Offline successor closure-contract rehearsal; no operational or release mode."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import socket
import sys
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
        raise ValueError('output-unavailable')
    from successor_execution_cli import checks
    from successor_profile_cli import runtime
    from test_successor_closure import ClosureTests
    from successor_closure_checks import run,VERSION,CONNECTED_CASES
    before=runtime()
    with patch.object(socket.socket,'connect',side_effect=AssertionError('network-disabled')):
        contract=checks(ClosureTests)
    if contract['casesRun']==contract['casesPassed']==9 and not contract['failedCases'] and not contract['skippedCases']:
        report=run()
    else:report=dict(format=VERSION,state='review-required',casesPassed=0,phases=[])
    report.update(capturedAt=datetime.now(timezone.utc).isoformat(),closureContractChecks=contract,
        runtimeBefore=before,runtimeAfter=runtime(),
        realNetworkRequests=0,realTransactionsSent=0,userJournalsOpened=False,userPrivateKeysAccessed=False,
        operationalClosureApplied=False,reservationsReleased=False,executionApproved=False)
    publish(args.output,report)
    print('State:',report['state'])
    print('Closure contract checks:',contract['casesPassed'],'/',9)
    print('Connected checks:',report['casesPassed'],'/',CONNECTED_CASES)
    print('Send headroom ms:',report.get('headroomAtReturnMs'))
    print('Balance headroom ms:',report.get('balanceHeadroomAtReturnMs'))
    print('Closure disposition:',report.get('closureContract',{}).get('state'))
    print('Temporary ledgers removed:',report.get('temporaryLedgersRemoved',False))
    for row in report['phases']:
        print(row['phase']+':',row['elapsedMs'],'ms; completed:',row['completed'])
    print('Passing verifies blocked closure. No real transaction, release or E0 closure.')
    print('Upload:',args.output.absolute())
    return 0 if report['state']=='offline-integration-passed' else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:raise SystemExit('Successor closure rehearsal stopped ('+type(exc).__name__+').')
