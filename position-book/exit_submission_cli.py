#!/usr/bin/env python3
"""Offline one-send exit transport exercise; no existing wallet, RPC endpoint or live mode."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
from exit_submission_checks import run
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    result=run();result['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,result)
    print('State:',result['state']);print('Offline cases passed:',result['casesPassed'])
    print('Public pre-signed fixtures and temporary ledgers only. No RPC, keys, new signatures, submission or runtime changes.')
    print('Upload:',a.output.absolute())


if __name__=='__main__':
    try:main()
    except Exception as exc:
        raise SystemExit('Exit submission check stopped ('+type(exc).__name__+'); no complete report published.')
