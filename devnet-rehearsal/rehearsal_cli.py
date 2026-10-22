#!/usr/bin/env python3
"""Dedicated devnet preparation only. Default: offline self-check. No broadcaster."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
from core import ROOT, initialize, prepare, Session
from rehearsal_checks import run
sys.path.insert(0,str(ROOT/'launch-study'))
from report import publish

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action',choices=('self-check','initialize','status','prepare'),default='self-check')
    parser.add_argument('--directory',type=Path)
    parser.add_argument('--allow-signed-devnet-simulation',action='store_true')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.action!='self-check' and args.directory is None: parser.error('--directory required')
    if args.action=='prepare' and not args.allow_signed_devnet_simulation:
        parser.error('prepare requires --allow-signed-devnet-simulation')
    if args.output.exists() or args.output.is_symlink(): raise ValueError('Output already exists')
    if not args.output.parent.is_dir(): raise ValueError('Output directory missing')
    if args.action=='self-check': result=run()
    elif args.action=='initialize': result=initialize(args.directory)
    elif args.action=='prepare': result=prepare(args.directory)
    else:
        with Session(args.directory) as session: result=session.status()
    result['capturedAt']=datetime.now(timezone.utc).isoformat()
    publish(args.output,result)
    print('Action: '+args.action+'; state: '+result.get('state',result['format']))
    if result.get('wallet'): print('Dedicated devnet public address: '+result['wallet'])
    print('No transaction submitted. Upload only this public report: '+str(args.output.absolute()))
    if args.action=='initialize': print('Keep the wallet directory private. Never upload signer.pk8 or rehearsal.sqlite.')

if __name__=='__main__':
    try: main()
    except Exception:
        print('Devnet preparation stopped. Check arguments and private file permissions. After partial initialization or preparation, inspect status; do not delete or recreate the session to retry.',file=sys.stderr)
        sys.exit(1)
