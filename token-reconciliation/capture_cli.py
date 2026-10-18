#!/usr/bin/env python3
"""Read one existing public token transaction, or replay a saved capture. Never signs or sends."""
import argparse
import datetime as dt
import gzip
from pathlib import Path
import sys
from recorded_flows import analyze
from recorded_capture import collect, TOKEN, SYSTEM, MAX_CAPTURE, loads
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from report import publish


def read(path):
    with (gzip.open(path,'rb') if path.suffix=='.gz' else path.open('rb')) as f:
        raw=f.read(MAX_CAPTURE+1)
    if len(raw)>MAX_CAPTURE:raise ValueError('Capture byte cap')
    value=loads(raw)
    if isinstance(value,dict) and value.get('format') in ('recorded-chain-report-1','recorded-token-report-1'):
        return value['capture']
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sample-devnet',action='store_true')
    p.add_argument('--network',choices=('devnet','mainnet-beta'))
    p.add_argument('--signature')
    p.add_argument('--input',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();explicit=bool(a.network or a.signature)
    if sum((a.sample_devnet,explicit,bool(a.input)))>1:p.error('Choose one mode')
    if explicit and not (a.network and a.signature):p.error('Explicit network and signature required together')
    if a.output.exists() or a.output.is_symlink():raise ValueError('Output already exists')
    if a.sample_devnet or explicit or a.input:
        c=read(a.input) if a.input else collect('devnet' if a.sample_devnet else a.network,
                a.signature,sample=a.sample_devnet,sample_program=TOKEN if a.sample_devnet else SYSTEM)
        result={'format':'recorded-token-report-1','mode':'offline-replay' if a.input else 'public-rpc-read-only',
                'capture':c,'review':analyze(c),'currentRunNetworkRequests':0 if a.input else c['rpcRequestsAttempted'],
                'transactionsSent':0,'intentProven':False,'executionApproved':False,'productionLedgerUpdated':False}
    else:
        from token_capture_checks import self_check
        result=self_check()
    result['capturedAt']=dt.datetime.now(dt.timezone.utc).isoformat()
    publish(a.output,result)
    print('State:',result.get('review',{}).get('state',result['format']))
    if result.get('review',{}).get('reason'):print('Reason:',result['review']['reason'])
    print('Public requests this run:',result['currentRunNetworkRequests'])
    print('No transaction sent or prior intent inferred. Upload:',a.output.resolve())


if __name__=='__main__':
    try:main()
    except Exception as exc:raise SystemExit('Recorded token capture stopped: '+type(exc).__name__+'. No report published.')
