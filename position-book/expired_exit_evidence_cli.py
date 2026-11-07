#!/usr/bin/env python3
"""Eight bounded devnet reads of expiry, receipt and scoped balances; no execution action."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish
from expired_exit_evidence import inspect


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--wallet',required=True);p.add_argument('--pool',required=True)
    p.add_argument('--preparation-sha256',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    root=a.directory.resolve();out=a.output.resolve()
    for private in (root,root.parent/(root.name+'-entry-handoff-v1'),root.parent/(root.name+'-unsigned-admission-rehearsal-v1')):
        if out.is_relative_to(private):raise ValueError('output-inside-private-source')
    result=inspect(a.directory,a.wallet,a.pool,a.preparation_sha256)
    publish(a.output,result)
    print('State:',result['state'])
    print('Read-only devnet requests:',result['networkRequests'])
    if result['assessment']:
        print('Assessment:',result['assessment']['state'])
        print('Blockers:',result['assessment']['blockers'])
    print('No signing, submission, ledger update, release or replacement authorization.')
    print('Upload only this public report:',a.output.absolute())
    return 0 if result['state']=='expired-exit-evidence-observed' else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        raise SystemExit('Expiry evidence stopped ('+type(exc).__name__+'). Preserve all journals; no automatic retry.')
