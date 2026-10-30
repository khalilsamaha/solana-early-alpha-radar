#!/usr/bin/env python3
"""Explicit bounded unsigned devnet entry with same-response pool projection."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import fresh_quote
from post_entry_checks import run
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--simulate-devnet',action='store_true')
    p.add_argument('--deployment-observation-20261027',action='store_true')
    p.add_argument('--directory',type=Path);p.add_argument('--wallet');p.add_argument('--pool')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    if a.directory and a.output.resolve().is_relative_to(a.directory.resolve()):raise ValueError('output-inside-source')
    if a.simulate_devnet:
        if not all((a.directory,a.wallet,a.pool)):raise ValueError('explicit-scope-required')
        r=fresh_quote.observe(a.directory,a.wallet,a.pool,simulate=True,assess_costs=True,
            post_entry_projection=True,refreshed_deployment=a.deployment_observation_20261027)
    else:
        if any((a.directory,a.wallet,a.pool,a.deployment_observation_20261027)):raise ValueError('select-simulation')
        r=run()
    r['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,r)
    print('State:',r['state'])
    if 'casesPassed' in r:print('Offline cases passed:',r['casesPassed'])
    if r.get('postEntryProjection'):
        q=r['postEntryProjection']['projection']
        print('Simulated acquired quantity:',q['acquiredInputAtomic'])
        print('Projected reverse output:',q['projectedOutputAtomic'])
    print('One unsigned entry simulation only; no exit simulation, signing or submission.')
    print('No journal or runtime changes. Projection is not a fill or profit.')
    print('Upload:',a.output.absolute())
    return 2 if r['state']=='unavailable' else 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:raise SystemExit('Post-entry observation stopped ('+type(exc).__name__+'). Preserve all journals.')
