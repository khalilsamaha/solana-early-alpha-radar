#!/usr/bin/env python3
"""Default disposable-key offline checks; public inventory; explicit one-shot devnet simulation."""
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
import sys
from swap_rehearsal import prepare,report,Session
from preflight_cli import read
from swap_rehearsal_checks import run
from swap_inventory import collect_inventory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action',choices=('self-check','inventory','prepare','status'),default='self-check')
    p.add_argument('--wallet');p.add_argument('--directory',type=Path)
    p.add_argument('--pool-capture',type=Path);p.add_argument('--scope',type=Path);p.add_argument('--packet',type=Path)
    p.add_argument('--allow-devnet-sign',action='store_true')
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('Output unavailable')
    if a.action=='self-check':
        if any((a.wallet,a.directory,a.pool_capture,a.scope,a.packet,a.allow_devnet_sign)):raise ValueError('Unexpected arguments')
        result=run()
    elif a.action=='inventory':
        if not a.wallet or not a.pool_capture or any((a.directory,a.scope,a.packet,a.allow_devnet_sign)):raise ValueError('Inventory arguments')
        c=read(a.pool_capture)
        if c.get('format')=='swap-preflight-report-1':c=c['capture']
        result=collect_inventory(c,a.wallet)
    elif a.action=='prepare':
        if not all((a.wallet,a.directory,a.scope,a.packet,a.allow_devnet_sign)) or a.pool_capture:raise ValueError('Explicit preparation arguments required')
        result=prepare(a.directory,a.wallet,read(a.scope),read(a.packet))
    else:
        if not a.directory or not a.wallet or any((a.scope,a.packet,a.pool_capture,a.allow_devnet_sign)):raise ValueError('Status arguments')
        with Session(a.directory) as s:
            if s.wallet!=a.wallet:raise ValueError('Wallet mismatch')
            result=report(s.home)
    result['capturedAt']=datetime.now(timezone.utc).isoformat()
    if len(json.dumps(result).encode())>8*1024*1024:raise ValueError('Report cap')
    publish(a.output,result)
    print('State:',result.get('state',result.get('review',{}).get('state','self-check-passed')))
    if 'casesPassed' in result:print('Cases passed:',result['casesPassed'])
    if result.get('format')=='devnet-swap-inventory-1':
        r=result['review'];print('Wallet lamports:',r.get('walletLamports','unavailable'))
        for m in r.get('mints',[]):print('Mint:',m['mint'],'supported accounts:',len(m['existingSupportedAccounts']),'funded:',m['hasFundedAccount'])
    print('No transaction submitted. Upload:',a.output.absolute())


if __name__=='__main__':
    try:main()
    except Exception as exc:raise SystemExit('Swap rehearsal stopped ('+type(exc).__name__+'); inspect local state with status before any further signing attempt.')
