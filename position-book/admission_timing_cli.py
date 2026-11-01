#!/usr/bin/env python3
"""Offline checks or one opt-in unsigned devnet entry/admission timing observation."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
import admission_timing
from admission_timing_checks import run
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--observe-devnet',action='store_true')
    p.add_argument('--directory',type=Path);p.add_argument('--wallet');p.add_argument('--pool')
    p.add_argument('--maximum-exit-attempts',type=int)
    p.add_argument('--maximum-exit-fee-lamports');p.add_argument('--maximum-total-fee-lamports')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    scope=(a.directory,a.wallet,a.pool,a.maximum_exit_attempts,a.maximum_exit_fee_lamports,a.maximum_total_fee_lamports)
    if a.observe_devnet:
        if any(v is None for v in scope):raise ValueError('explicit-scope-and-fee-scenario-required')
        root=a.directory.resolve();sibling=root.parent/(root.name+'-entry-handoff-v1')
        if a.output.resolve().is_relative_to(root) or a.output.resolve().is_relative_to(sibling):raise ValueError('output-inside-private-source')
        r=admission_timing.observe(a.directory,a.wallet,a.pool,maximum_exit_attempts=a.maximum_exit_attempts,
            maximum_exit_fee_lamports=a.maximum_exit_fee_lamports,maximum_total_fee_lamports=a.maximum_total_fee_lamports)
    else:
        if any(v is not None for v in scope):raise ValueError('select-observation')
        r=run()
    r['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,r)
    print('State:',r['state'])
    if 'casesPassed' in r:print('Offline cases passed:',r['casesPassed'])
    else:
        print('Stage:',r['stage'],'; diagnostic:',r['diagnosticCode'])
        print('Original-deadline headroom:',r['remainingMs'],'ms; requests:',r['networkRequests'])
    print('No private keys, signing, sends, durable admission, new reservations or runtime changes.')
    print('Upload:',a.output.absolute())
    return 2 if r['state']=='unavailable' else 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:raise SystemExit('Admission timing stopped ('+type(exc).__name__+'); preserve all journals.')
