#!/usr/bin/env python3
"""Offline checks or explicit bounded read-only devnet observation of a preserved exit."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('check','observe'),default='check')
    p.add_argument('--directory',type=Path);p.add_argument('--wallet');p.add_argument('--pool')
    p.add_argument('--expected-original-sha256');p.add_argument('--expected-current-sha256')
    p.add_argument('--allow-devnet-observation',action='store_true')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    scope=(a.directory,a.wallet,a.pool,a.expected_original_sha256,a.expected_current_sha256)
    if a.action=='check':
        if any(x is not None for x in scope) or a.allow_devnet_observation:raise ValueError('offline-has-no-scope')
        from preserved_exit_checks import run
        r=run();ok=r['state']=='offline-checks-passed'
        print('Offline cases passed:',r['casesPassed'])
    else:
        if any(x is None for x in scope) or not a.allow_devnet_observation:raise ValueError('explicit-scope-required')
        root=a.directory.resolve();out=a.output.resolve()
        for private in (root,root.parent/(root.name+'-entry-handoff-v1'),root.parent/(root.name+'-unsigned-admission-rehearsal-v1')):
            if out.is_relative_to(private):raise ValueError('output-inside-private-source')
        from preserved_exit_observation import observe
        r=observe(a.directory,a.wallet,a.pool,expected_original_sha256=a.expected_original_sha256,
            expected_current_sha256=a.expected_current_sha256,allow_devnet_observation=True)
        ok=r['state']=='preserved-exit-observation-complete'
        print('Devnet RPC requests:',r['networkRequests'])
        print('Diagnostic:',r['diagnosticCode'])
        print('Timing:',r.get('observationTiming'))
    r['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,r)
    print('State:',r['state'])
    print('No preparation appended, signing, sending or release. Preserve all journals.')
    print('Upload:',a.output.absolute());return 0 if ok else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        raise SystemExit('Preserved exit observation stopped ('+type(exc).__name__+'). No execution action exists; preserve all journals.')
