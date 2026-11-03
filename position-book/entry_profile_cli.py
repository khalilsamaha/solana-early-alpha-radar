#!/usr/bin/env python3
"""Offline entry phase profile using disposable test keys; no operational flags."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from entry_profile_rehearsal import run
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
        raise ValueError('output-unavailable')
    report = run(); report['capturedAt'] = datetime.now(timezone.utc).isoformat()
    publish(args.output, report)
    print('State:', report['state']); print('Connected checks passed:', report['casesPassed'])
    for row in report['profile']['spans']:
        print(row['stage']+':', row['elapsedMs'], 'ms; completed:', row['completed'])
    print('Original deadline remaining at send guard:', report['profile']['sendGuardRemainingMs'], 'ms')
    if report.get('signatureVerification'):
        for phase in ('attempt', 'signing', 'submission'):
            counts = report['signatureVerification'][phase]
            print(phase+': verifier processes:', counts['verifierProcesses'], '; memo hits:', counts['memoHits'])
    print('Offline only: synthetic provider replies and disposable test keys; no user wallet or network.')
    print('Upload:', args.output.absolute())
    return 0 if report['state']=='offline-entry-profile-passed' else 2


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        raise SystemExit('Entry profile stopped ('+type(exc).__name__+'); no complete report published.')
