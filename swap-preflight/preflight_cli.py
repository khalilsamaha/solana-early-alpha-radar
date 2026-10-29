#!/usr/bin/env python3
"""Read-only combined devnet preflight capture or offline replay. No simulation or signing."""
import argparse
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import sys
import time
from preflight import audit,flags,BASELINE,digest
from preflight_capture import collect
from preflight_diagnostics import describe
from preflight_checks import run
from recorded_capture import loads
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish

MAX_REPORT=8*1024*1024


def read(path):
    with (gzip.open(path,'rb') if path.suffix=='.gz' else path.open('rb')) as f:raw=f.read(MAX_REPORT+1)
    if len(raw)>MAX_REPORT:raise ValueError('Input cap')
    return loads(raw)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--pool',help='Explicit devnet pool; no wallet or fee checks without a packet')
    mode.add_argument('--packet',type=Path,help='Current public unsigned contract packet')
    mode.add_argument('--input',type=Path,help='Replay a public combined capture at its original time')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():raise ValueError('Output unavailable')
    if a.pool or a.packet or a.input:
        if a.input:
            c=read(a.input)
            if type(c) is dict and c.get('format')=='swap-preflight-report-1':c=c['capture']
            at=c['finishedAtMs']
        else:
            c=collect(pool=a.pool,packet=read(a.packet) if a.packet else None);at=time.time_ns()//1000000
        result=dict(format='swap-preflight-report-1',capture=c,review=audit(c,now_ms=at),
                    captureDiagnostics=describe(c),
                    baselineId=BASELINE['id'],baselineSha256=digest(BASELINE),replayOnly=bool(a.input),
                    currentRunNetworkRequests=0 if a.input else c['rpcRequestsAttempted'])
    else:result=run()
    result.update(capturedAt=datetime.now(timezone.utc).isoformat(),**flags())
    if len(json.dumps(result).encode())>MAX_REPORT:raise ValueError('Report cap')
    publish(a.output,result)
    if 'review' in result:
        print('Preflight:',result['review']['state'])
        print('Reason:',result['capture'].get('stoppedReason') or result['review'].get('reason','none'))
        print('RPC requests:',result['currentRunNetworkRequests'])
    else:print('Preflight self-check:',result['casesPassed'],'cases passed')
    print('No signing, simulation, submission or position-book change.')
    print('Upload:',a.output.absolute())


if __name__=='__main__':
    try:main()
    except Exception as exc:raise SystemExit('Preflight stopped ('+type(exc).__name__+'); no complete report published.')
