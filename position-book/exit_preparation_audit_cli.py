#!/usr/bin/env python3
"""Offline checks or read-only exit preparation inspection; no execution action."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import exit_preparation_audit as m
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('check','inspect'),default='check')
    p.add_argument('--directory',type=Path);p.add_argument('--wallet');p.add_argument('--pool')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('output-unavailable')
    scope=(a.directory,a.wallet,a.pool)
    if a.action=='check':
        if any(x is not None for x in scope):raise ValueError('check-has-no-operational-scope')
        from exit_preparation_audit_checks import run
        result=run()
    else:
        if any(x is None for x in scope):raise ValueError('explicit-scope-required')
        root=a.directory.resolve();out=a.output.resolve()
        for private in (root,root.parent/(root.name+'-entry-handoff-v1'),
                        root.parent/(root.name+'-unsigned-admission-rehearsal-v1')):
            if out.is_relative_to(private):raise ValueError('output-inside-private-source')
        result=m.inspect(*scope)
    result['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,result)
    print('State:',result['state'])
    if a.action=='check':print('Offline cases passed:',result['casesPassed'])
    else:
        print('Preparation:',result['preparation']);print('Signing:',result['signing'])
        print('Backend markers:',result['backendMarkers'])
    print('No RPC, private-key access, signing, sending, replacement or release.')
    print('Upload only this public report:',a.output.absolute())
    return 0 if a.action=='check' or result['coherent'] else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        raise SystemExit('Exit preparation inspection stopped ('+type(exc).__name__+'). Preserve all journals.')
