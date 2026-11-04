#!/usr/bin/env python3
"""Offline phase rehearsal, or read-only historical timing; no execution action."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('check','inspect'),default='check')
    p.add_argument('--directory',type=Path);p.add_argument('--wallet');p.add_argument('--pool')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    scope=(a.directory,a.wallet,a.pool)
    if a.action=='check':
        if any(x is not None for x in scope):raise ValueError('offline-has-no-operational-scope')
        from exit_profile_rehearsal import run
        r=run();ok=r['state']=='offline-exit-profile-passed'
        print('State:',r['state'])
        encoding=(r.get('connected') or {}).get('encodingReplay')
        if encoding:
            print('Encoding reuse:',encoding['version'],'; hits=',encoding['hits'],
                  '; computations=',encoding['computations'],'; entries=',encoding['entries'])
        history=(r.get('connected') or {}).get('admissionHistoryReplay')
        if history:print('Admission history reuse:',history)
        if r['profiles']:
            for stage,row in r['profiles'][0]['stageTotals'].items():
                print(stage+': count=',row['count'],'; exclusiveMs=',row['exclusiveMs'],'; incomplete=',row['incomplete'])
        print('Offline only: synthetic replies and disposable test keys.')
    else:
        if any(x is None for x in scope):raise ValueError('explicit-scope-required')
        root=a.directory.resolve();out=a.output.resolve()
        for private in (root,root.parent/(root.name+'-entry-handoff-v1'),root.parent/(root.name+'-unsigned-admission-rehearsal-v1')):
            if out.is_relative_to(private):raise ValueError('output-inside-private-source')
        from exit_history_timing import inspect
        r=inspect(*scope);ok=r['state']=='saved-exit-timing-observed'
        print('State:',r['state'])
        if r['timing']:
            for k in ('collectionElapsedMs','summedRecordedRequestIntervalsMs','finalResponseToDeliveryMs',
                      'deliveryToRecordTimestampMs','remainingAtRecordTimestampMs'):print(k+':',r['timing'][k])
        print('Read-only saved evidence; no network, private-key access, replacement or signing.')
    r['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,r)
    print('Upload:',a.output.absolute());return 0 if ok else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        raise SystemExit('Exit timing stopped ('+type(exc).__name__+'). No execution action exists; preserve all journals.')
