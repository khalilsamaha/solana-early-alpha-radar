#!/usr/bin/env python3
"""Measure one offline lifecycle using temporary test keys and synthetic providers."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from lifecycle_rehearsal import run
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True); a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir(): raise ValueError('output-unavailable')
    r=run(); r['capturedAt']=datetime.now(timezone.utc).isoformat(); publish(a.output,r)
    print('State:',r['state']); print('Connected checks passed:',r['casesPassed'])
    for row in r['timings']: print(row['stage']+':',row['elapsedMs'],'ms; completed:',row['completed'])
    print('Offline only: disposable test keys; synthetic provider replies; no user wallet or network.')
    print('Upload:',a.output.absolute())
    return 0 if r['state']=='offline-rehearsal-passed' else 2


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc: raise SystemExit('Lifecycle rehearsal stopped ('+type(exc).__name__+'); no complete report published.')
