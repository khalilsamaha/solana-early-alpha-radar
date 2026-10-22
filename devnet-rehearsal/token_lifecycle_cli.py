#!/usr/bin/env python3
"""One fixed atomic devnet WSOL lifecycle; default is offline self-check."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
from core import ROOT
from token_lifecycle import execute,recover,status
from submission import stop
sys.path.insert(0,str(ROOT/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('self-check','execute','recover','status','stop'),default='self-check')
    p.add_argument('--directory',type=Path)
    p.add_argument('--wallet')
    p.add_argument('--allow-devnet-token-submit',action='store_true')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.action!='self-check' and not a.directory:p.error('--directory required')
    if a.action in ('execute','recover','status') and not a.wallet:p.error('--wallet required')
    if a.action=='execute' and not a.allow_devnet_token_submit:p.error('--allow-devnet-token-submit required')
    if a.allow_devnet_token_submit and a.action!='execute':p.error('Submission flag is only for execute')
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('Output unavailable')
    if a.action=='self-check':
        from token_lifecycle_checks import run
        r=run()
    elif a.action=='stop':r=stop(a.directory)
    else:r={'execute':execute,'recover':recover,'status':status}[a.action](a.directory,a.wallet)
    r['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,r)
    print('State:',r.get('state',r['format']))
    print('Upload only this public report:',a.output.absolute())
    if a.action=='execute':print('Do not execute again to retry. Preserve the session and use recover.')


if __name__=='__main__':
    try:main()
    except Exception:
        print('Token lifecycle stopped. Preserve the private session; use status or recover. No automatic retry was performed.',file=sys.stderr)
        sys.exit(1)
