#!/usr/bin/env python3
"""Explicit single devnet self-transfer submission, recovery or offline check."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
from core import ROOT
from submission import execute,recover,stop
sys.path.insert(0,str(ROOT/'launch-study'))
from report import publish

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('self-check','execute','recover','status','stop'),default='self-check')
    p.add_argument('--directory',type=Path)
    p.add_argument('--wallet')
    p.add_argument('--allow-devnet-submit',action='store_true')
    p.add_argument('--allow-expired-plan-replacement',action='store_true')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.action!='self-check' and a.directory is None: p.error('--directory required')
    if a.action in ('execute','recover') and not a.wallet: p.error('--wallet required')
    if a.action=='execute' and not a.allow_devnet_submit: p.error('--allow-devnet-submit required')
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir(): raise ValueError('Output unavailable')
    if a.action=='self-check':
        from submission_checks import run
        r=run()
    elif a.action=='execute': r=execute(a.directory,a.wallet,allow_replace=a.allow_expired_plan_replacement)
    elif a.action=='recover': r=recover(a.directory,a.wallet)
    elif a.action=='stop': r=stop(a.directory)
    else:
        from submission import Lifecycle,SubmitRpc
        with Lifecycle(a.directory) as s: r=s.report(SubmitRpc())
    r['capturedAt']=datetime.now(timezone.utc).isoformat(); publish(a.output,r)
    print('State: '+r.get('state',r['format']))
    print('Upload only this public report: '+str(a.output.absolute()))
    if a.action=='execute': print('Do not repeat execute to retry. Use recover to observe the recorded signature.')

if __name__=='__main__':
    try: main()
    except Exception:
        print('Devnet action stopped. Preserve the session. Use status or recover; do not delete the journal or recreate the wallet. No automatic retry was performed.',file=sys.stderr)
        sys.exit(1)
