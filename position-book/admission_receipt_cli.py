#!/usr/bin/env python3
"""Run only the temporary synthetic admission-to-receipt checks."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from admission_receipt_checks import run
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('output-unavailable')
    result = run(); result['capturedAt'] = datetime.now(timezone.utc).isoformat()
    publish(a.output, result)
    print('State:', result['state']); print('Offline cases passed:', result['casesPassed'])
    print('Synthetic receipts and temporary ledgers only. No keys, RPC, signing, sends or runtime changes.')
    print('Upload:', a.output.absolute())


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Admission receipt check stopped ('+type(exc).__name__+'); no complete report published.')
