#!/usr/bin/env python3
"""Offline connected continuation rehearsal; no user wallet or operational action."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
from continuation_exit_checks import run
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    result=run();result['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,result)
    print('State:',result['state']);print('Checks passed:',result['casesPassed'])
    print('Independent signer contract checks:',len(result.get('independentContractCases',{})))
    print('Connected continuation/sign/send time (ms):',result['integrationElapsedMs'])
    print('Deadline headroom (ms):',result.get('deadlineHeadroomMs'))
    print('Synthetic replies and disposable test keys only. No user wallet, real RPC or runtime changes.')
    print('Upload:',a.output.absolute())


if __name__=='__main__':
    try:main()
    except Exception as exc:raise SystemExit('Continuation integration check stopped ('+type(exc).__name__+'); no complete report published.')
