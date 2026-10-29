#!/usr/bin/env python3
"""Offline curve checks or one explicit read-only controlled devnet observation."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

import fresh_quote
from cpmm_quote_checks import run
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--observe-devnet',action='store_true')
    p.add_argument('--directory',type=Path)
    p.add_argument('--wallet')
    p.add_argument('--pool')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
        raise ValueError('output-unavailable')
    if a.directory and a.output.resolve().is_relative_to(a.directory.resolve()):
        raise ValueError('report-must-be-outside-source-directory')
    if a.observe_devnet:
        if not all((a.directory,a.wallet,a.pool)):raise ValueError('explicit-devnet-scope-required')
        result=fresh_quote.observe(a.directory,a.wallet,a.pool)
    else:
        if any((a.directory,a.wallet,a.pool)):raise ValueError('select-observe-devnet')
        result=run()
    result['capturedAt']=datetime.now(timezone.utc).isoformat()
    publish(a.output,result)
    print('State:',result['state'])
    print('Public devnet requests:',result['networkRequests'])
    print('No signing, submission, new cycle or running-service changes.')
    print('Upload:',a.output.absolute())
    return 2 if result['state']=='unavailable' else 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:raise SystemExit('Fresh quote stopped ('+type(exc).__name__+'). Preserve all journals.')
