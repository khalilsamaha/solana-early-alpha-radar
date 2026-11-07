#!/usr/bin/env python3
"""Read-only review of fresh evidence and budget after exact exit retirement."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish
from retired_exit_replan import inspect


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--wallet',required=True);p.add_argument('--pool',required=True)
    p.add_argument('--preparation-sha256',required=True)
    p.add_argument('--retirement-sha256',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    root=a.directory.resolve();out=a.output.resolve()
    for private in (root,root.parent/(root.name+'-entry-handoff-v1'),root.parent/(root.name+'-unsigned-admission-rehearsal-v1')):
        if out.is_relative_to(private):raise ValueError('output-inside-private-source')
    result=inspect(a.directory,a.wallet,a.pool,a.preparation_sha256,a.retirement_sha256)
    publish(a.output,result)
    print('State:',result['state']);print('Read-only devnet requests:',result['networkRequests'])
    print('Blockers:',result['blockingReasons'])
    if result['diagnosticCode']:print('Diagnostic:',result['diagnosticCode'])
    print('No new preparation, signing, submission or release. Holds remain.')
    print('Upload only this public report:',a.output.absolute())
    return 0 if result['state']=='retired-exit-review-consistent-held' else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:raise SystemExit('Retired exit review stopped ('+type(exc).__name__+'). Preserve journals.')
