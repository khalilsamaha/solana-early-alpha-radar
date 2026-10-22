#!/usr/bin/env python3
"""Run offline signed position self-checks; no persistent production state or wallet access."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from position_checks import run
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('Output unavailable')
    r=run();r['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,r)
    print('Position accounting self-check:',r['casesPassed'],'cases passed')
    print('No network requests, signatures created or transactions sent.')
    print('Upload:',a.output.absolute())


if __name__=='__main__':
    try:main()
    except Exception as exc:raise SystemExit('Position check stopped ('+type(exc).__name__+'); no complete report published.')
