#!/usr/bin/env python3
"""Offline post-entry evidence contract checks only; no RPC, wallet or execution flags."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from post_entry_checks import run
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('output-unavailable')
    r = run();r['capturedAt'] = datetime.now(timezone.utc).isoformat()
    publish(a.output,r)
    print('State:',r['state'])
    print('Offline cases passed:',r['casesPassed'])
    print('No RPC, signing, submission, source journal or runtime changes.')
    print('Live post-entry collector and exit simulation are not integrated.')
    print('Upload:',a.output.absolute())


if __name__ == '__main__':
    try:main()
    except Exception as exc:
        raise SystemExit('Post-entry checks stopped ('+type(exc).__name__+').')
