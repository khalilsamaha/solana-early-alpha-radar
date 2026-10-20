#!/usr/bin/env python3
"""Read-only devnet setup costs; fresh unsigned packets; explicit signed simulation handoff."""
import argparse
from pathlib import Path
import sys
from fresh_packet import build, prepare_fresh, ROOT
from setup_costs import collect_costs
from preflight_cli import read
sys.path.insert(0, str(ROOT / 'launch-study'))
from report import publish


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--action', choices=('setup-costs','build-packet','prepare-fresh'), required=True)
    p.add_argument('--wallet'); p.add_argument('--pool'); p.add_argument('--scope', type=Path)
    p.add_argument('--directory', type=Path); p.add_argument('--allow-devnet-sign', action='store_true')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir(): raise ValueError('Output unavailable')
    if a.action == 'setup-costs':
        if not a.wallet or not a.pool or any((a.scope,a.directory,a.allow_devnet_sign)): raise ValueError('Cost arguments')
        result = collect_costs(a.pool, a.wallet)
    elif a.action == 'build-packet':
        if not a.scope or any((a.wallet,a.pool,a.directory,a.allow_devnet_sign)): raise ValueError('Packet arguments')
        result = build(read(a.scope))
    else:
        if not all((a.scope,a.wallet,a.directory,a.allow_devnet_sign)) or a.pool: raise ValueError('Explicit signing arguments required')
        result = prepare_fresh(a.directory, a.wallet, read(a.scope))
    publish(a.output, result)
    r = result.get('review', result)
    print('State:', r.get('state','fresh-unsigned-packet-built'))
    for k in ('walletLamports','configCreationFeeLamports','estimatedTotalLamports','estimatedShortfallLamports','blockers'):
        if k in r: print(k + ':', r[k])
    print('No transaction submitted. Upload:', a.output.absolute())


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        raise SystemExit('Devnet setup stopped (' + type(exc).__name__ + '). No automatic retry; use rehearsal status after a signing attempt.')
