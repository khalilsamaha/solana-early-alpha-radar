#!/usr/bin/env python3
"""Offline unsigned-exit continuation exercise; no existing wallet, RPC endpoint or live mode."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import sys
from unsigned_exit_continuation_checks import run,independent_contract
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('output-unavailable')
    result=run();checks=independent_contract()
    result['independentContractCases']=checks['cases']
    result['independentContractCasesPassed']=checks['casesPassed']
    result['disposableFixtureSigning']=True
    result['continuationSignaturesCreated']=0
    result['continuationSendRequests']=0
    result.pop('signaturesCreated',None)
    result.pop('privateKeyAccessed',None)
    result['capturedAt']=datetime.now(timezone.utc).isoformat();publish(a.output,result)
    print('State:',result['state']);print('Offline cases passed:',result['casesPassed'])
    print('Independent contract cases passed:',checks['casesPassed'])
    print('Offline disposable fixtures only. No production wallet, real RPC or user-position submission.')
    print('Upload:',a.output.absolute())


if __name__=='__main__':
    try:main()
    except Exception as exc:
        raise SystemExit('Unsigned exit continuation check stopped ('+type(exc).__name__+'); no complete report published.')
