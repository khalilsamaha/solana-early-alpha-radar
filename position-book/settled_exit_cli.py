#!/usr/bin/env python3
"""Synthetic settled entry and delayed exit checks only. No operational action flags."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
from settled_exit_checks import run
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    r=run();r['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,r)
    print('State:',r['state']);print('Offline cases passed:',r['casesPassed'])
    print('Synthetic responses and temporary journals only. No wallet keys, RPC requests, signing or submission.')
    print('Upload:',a.output.absolute())


if __name__=='__main__':
    try:main()
    except Exception as exc:raise SystemExit('Settled exit integration check stopped ('+type(exc).__name__+'); no complete report published.')
