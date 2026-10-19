#!/usr/bin/env python3
"""Read-only devnet pool state capture or offline replay; no wallet access or submission."""
import argparse
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import sys
from state import audit
from state_capture import collect
from state_checks import run
from recorded_capture import loads
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish

MAX_INPUT=8*1024*1024


def read(path):
    with (gzip.open(path,'rb') if path.suffix=='.gz' else path.open('rb')) as f:
        raw=f.read(MAX_INPUT+1)
    if len(raw)>MAX_INPUT:raise ValueError('Input cap')
    return loads(raw)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group()
    group.add_argument('--sample-devnet',action='store_true',help='One latest program transaction hint; never resamples')
    group.add_argument('--pool',help='One explicit devnet pool public address')
    group.add_argument('--packet',type=Path,help='Current public unsigned policy packet; bounded devnet reads')
    group.add_argument('--input',type=Path,help='Offline replay of a public capture/report')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('Output unavailable')
    if a.input:
        c=read(a.input)
        if c.get('format')=='swap-state-report-1':c=c['capture']
        result={'format':'swap-state-report-1','capture':c,'review':audit(c),'currentRunNetworkRequests':0}
    elif a.sample_devnet or a.pool or a.packet:
        c=collect(sample=a.sample_devnet,pool=a.pool,packet=read(a.packet) if a.packet else None)
        result={'format':'swap-state-report-1','capture':c,'review':audit(c),'currentRunNetworkRequests':c['rpcRequestsAttempted']}
    else:
        result=run()
    result.update(capturedAt=datetime.now(timezone.utc).isoformat(),transactionsSent=0,signaturesCreated=0,
                  ledgerUpdated=False,signingApproved=False,executionApproved=False)
    if len(json.dumps(result).encode())>MAX_INPUT:raise ValueError('Report cap')
    publish(a.output,result)
    if 'review' in result:
        print('Pool state:',result['review']['state'])
        print('Reason:',result['capture'].get('stoppedReason') or result['review'].get('reason','none'))
        print('RPC requests:',result['currentRunNetworkRequests'])
    else:print('Pool-state self-check:',result['casesPassed'],'cases passed')
    print('No signatures or transactions. No signing or trading approval.')
    print('Upload:',a.output.absolute())


if __name__=='__main__':
    try:main()
    except Exception as exc:raise SystemExit('Pool state check stopped ('+type(exc).__name__+'); no complete report published.')
