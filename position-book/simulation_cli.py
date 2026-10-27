#!/usr/bin/env python3
"""Offline effects check or one explicit unsigned controlled-devnet simulation."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

import fresh_quote
from unsigned_simulation_checks import run
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate-devnet',action='store_true')
    parser.add_argument('--directory',type=Path)
    parser.add_argument('--wallet')
    parser.add_argument('--pool')
    parser.add_argument('--output',type=Path,required=True)
    a = parser.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('output-unavailable')
    if a.directory and a.output.resolve().is_relative_to(a.directory.resolve()):
        raise ValueError('report-must-be-outside-source-directory')
    if a.simulate_devnet:
        if not all((a.directory,a.wallet,a.pool)): raise ValueError('explicit-devnet-scope-required')
        result = fresh_quote.observe(a.directory,a.wallet,a.pool,simulate=True)
    else:
        if any((a.directory,a.wallet,a.pool)): raise ValueError('select-simulate-devnet')
        result = run()
    result['capturedAt'] = datetime.now(timezone.utc).isoformat()
    publish(a.output,result)
    print('State:',result['state'])
    print('Public devnet requests:',result['networkRequests'])
    print('No signatures, sends, new cycle or running-service changes.')
    print('Upload:',a.output.absolute())
    return 2 if result['state']=='unavailable' else 0


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc: raise SystemExit('Unsigned simulation stopped ('+type(exc).__name__+'). Preserve all journals.')
