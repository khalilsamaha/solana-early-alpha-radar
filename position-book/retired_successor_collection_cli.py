#!/usr/bin/env python3
"""Offline checks or one read-only fixed-devnet successor observation."""
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
    parser.add_argument('--action',choices=('check','observe'),default='check')
    parser.add_argument('--directory',type=Path)
    for key in ('wallet','pool','preparation-sha256','retirement-sha256'):parser.add_argument('--'+key)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():raise ValueError('output-unavailable')
    scope=(args.directory,args.wallet,args.pool,args.preparation_sha256,args.retirement_sha256)
    if args.action=='check':
        if any(x is not None for x in scope):parser.error('check accepts only --output')
        from test_retired_successor_collection import CollectionTests
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(CollectionTests)
        with patch.object(socket.socket,'connect',side_effect=AssertionError('network-disabled')):
            result=unittest.TextTestRunner(stream=io.StringIO(),verbosity=0).run(suite)
        passed=result.wasSuccessful() and result.testsRun>0 and not result.skipped
        report=dict(format='retired-successor-collection-check-1',capturedAt=datetime.now(timezone.utc).isoformat(),
            state='offline-checks-passed' if passed else 'offline-checks-failed',casesRun=result.testsRun,
            casesPassed=max(0,result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped)),
            failedCases=[t.id() for t,_ in result.errors+result.failures],
            userJournalsOpened=False,networkRequests=0,privateKeysAccessed=False,transactionsSent=0,
            evidence='actual bounded collectors with synthetic replies and disposable journals')
        ok=passed
    else:
        if not all(x is not None for x in scope):parser.error('observe requires directory, wallet, pool and both hashes')
        root=args.directory.resolve();out=args.output.resolve()
        for private in (root,root.parent/(root.name+'-entry-handoff-v1'),root.parent/(root.name+'-unsigned-admission-rehearsal-v1')):
            if out.is_relative_to(private):raise ValueError('output-inside-private-source')
        from retired_successor_collection import observe
        report=observe(*scope)
        report['capturedAt']=datetime.now(timezone.utc).isoformat()
        ok=report['state']=='successor-observation-consistent-held'
    publish(args.output,report)
    print('State:',report['state'])
    if args.action=='check':print('Offline cases passed:',report['casesPassed'])
    else:
        print('Read-only devnet requests:',report['networkRequests'])
        print('Deadline headroom ms:',report['timing'].get('headroomAtReturnMs'))
        if report['diagnosticCode']:print('Diagnostic:',report['diagnosticCode'])
    print('No user signing, submission, reservation release or scanner changes.')
    print('Upload only this public report:',args.output.absolute())
    return 0 if ok else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:raise SystemExit('Successor collection stopped ('+type(exc).__name__+'). Preserve journals.')
