#!/usr/bin/env python3
"""Explicit local retirement or read-only status; no transaction submission mode."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish
from exit_retirement import retire,status


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('status','retire'),default='status')
    p.add_argument('--allow-local-retirement',action='store_true')
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--wallet',required=True);p.add_argument('--pool',required=True)
    p.add_argument('--preparation-sha256',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.allow_local_retirement!=(a.action=='retire'):raise ValueError('explicit-retirement-action-required')
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    root=a.directory.resolve();out=a.output.resolve()
    for private in (root,root.parent/(root.name+'-entry-handoff-v1'),root.parent/(root.name+'-unsigned-admission-rehearsal-v1')):
        if out.is_relative_to(private):raise ValueError('output-inside-private-source')
    args=(a.directory,a.wallet,a.pool,a.preparation_sha256)
    result=retire(*args,allow_retire=True) if a.action=='retire' else status(*args)
    publish(a.output,result)
    print('State:',result['state'])
    print('Retirement created this run:',result['createdThisRun'])
    print('Read-only devnet requests:',result['networkRequests'])
    print('No signing, submission, replacement or release. All inventory and fee holds remain.')
    print('Upload only this public report:',a.output.absolute())
    return 0 if result['state']=='exit-retired-held' else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        raise SystemExit('Retirement stopped ('+type(exc).__name__+'). Preserve journals and use --action status; no automatic retry.')
