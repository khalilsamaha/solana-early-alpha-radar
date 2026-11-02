#!/usr/bin/env python3
"""Offline checks, one isolated unsigned commit rehearsal, or read-only recovery."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
import durable_admission as m
from durable_admission_checks import run
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('check','prepare','status'),default='check')
    p.add_argument('--allow-local-rehearsal',action='store_true')
    p.add_argument('--directory',type=Path);p.add_argument('--wallet');p.add_argument('--pool')
    p.add_argument('--maximum-exit-attempts',type=int);p.add_argument('--maximum-exit-fee-lamports');p.add_argument('--maximum-total-fee-lamports')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    scope=(a.directory,a.wallet,a.pool);caps=(a.maximum_exit_attempts,a.maximum_exit_fee_lamports,a.maximum_total_fee_lamports)
    if a.action=='check':
        if any(v is not None for v in scope+caps) or a.allow_local_rehearsal:raise ValueError('select-action')
        r=run()
    else:
        if any(v is None for v in scope):raise ValueError('explicit-scope-required')
        root=a.directory.resolve();output=a.output.resolve()
        for private in (root,m.storage(root),root.parent/(root.name+'-entry-handoff-v1')):
            if output.is_relative_to(private):raise ValueError('output-inside-private-source')
        if a.action=='prepare':
            if not a.allow_local_rehearsal or any(v is None for v in caps):raise ValueError('explicit-local-write-scenario-required')
            r=m.prepare(*scope,allow_local_rehearsal=True,maximum_exit_attempts=caps[0],maximum_exit_fee_lamports=caps[1],maximum_total_fee_lamports=caps[2])
        else:
            if a.allow_local_rehearsal or any(v is not None for v in caps):raise ValueError('status-is-read-only')
            r=m.status(*scope)
    r['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,r)
    print('State:',r['state'])
    if 'casesPassed' in r:print('Offline cases passed:',r['casesPassed'])
    else:
        print('Reservation recorded:',r['reservationRecorded'],'; commit observed on time:',r['commitOnTimeObserved'])
        print('Remaining original-deadline ms:',r['remainingMs'],'; diagnostic:',r['diagnosticCode'])
    print('No signing, send, operational reservation or runtime change.')
    print('Upload only this public report:',a.output.absolute())
    return 2 if r['state'] in ('unavailable','rehearsal-inspection-required','unsigned-rehearsal-recorded-unusable') else 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:raise SystemExit('Unsigned rehearsal stopped ('+type(exc).__name__+'). Preserve journals; use status after a prepare attempt.')
