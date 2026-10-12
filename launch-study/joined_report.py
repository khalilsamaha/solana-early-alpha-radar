#!/usr/bin/env python3
"""Create or replay a complete launch/quote report from two bounded offline exports."""
import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path
from join_quotes import join
from reconcile import reconcile
from report import publish, MAX_REPORT_BYTES

QUOTE_KEYS=('format','sourceIdentity','capturedAt','windowStartAt','registeredAt','observerVersion','limits',
    'samplingRegistration','previousSamplingRegistration','featureCaptureRegistration','signals','probes')


def read(path):
    with gzip.open(path,'rb') as f:
        raw=f.read(MAX_REPORT_BYTES+1)
    if len(raw)>MAX_REPORT_BYTES:raise ValueError('Input byte cap')
    value=json.loads(raw)
    if not isinstance(value,dict):raise ValueError('Input schema')
    return value,hashlib.sha256(raw).hexdigest()


def build(study,quotes,digests=None):
    if study.get('format')!='launch-study-report-1':raise ValueError('Unsupported study report')
    evidence={k:quotes[k] for k in QUOTE_KEYS if k in quotes}
    result=join(study['capture'],evidence)
    return {'format':'launch-quote-report-1','studyCapture':study['capture'],'quoteEvidence':evidence,
        'inputDecompressedSha256':digests or {},'analysis':result,
        'reconciliation':reconcile(study['capture'],evidence,result)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',type=Path);p.add_argument('--quotes',type=Path)
    p.add_argument('--input',type=Path,help='Replay a previously joined report')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if bool(a.input)==bool(a.study or a.quotes) or (not a.input and not (a.study and a.quotes)):
        p.error('Use --study plus --quotes, or --input')
    if a.input:
        old,_=read(a.input)
        if old.get('format')!='launch-quote-report-1':raise ValueError('Unsupported joined report')
        out=build({'format':'launch-study-report-1','capture':old['studyCapture']},old['quoteEvidence'],old.get('inputDecompressedSha256'))
    else:
        study,sh=read(a.study);quotes,qh=read(a.quotes)
        out=build(study,quotes,{'study':sh,'quotes':qh})
    publish(a.output,out)
    r=out['analysis']
    print('Matched observer decisions:',r['matchedObserverDecisions'],'/',r['commonWindowEntries'])
    print('Admitted watches:',r['admitted'],'; source identity matched')
    print('Primary comparison: 30s after buy response. Quotes are not fills or net profit.')
    for g in r['groups']:
        h=g['horizons']['30000'];v=h['onTimeQuotedChange'];mean=v['meanPct']
        print(f"{g['cohort']} / {g['samplingPolicy']}: entries={g['entries']}; admitted={g['admitted']}; on-time 30s quotes={v['observed']}; mean={mean:.2f}%" if mean is not None else f"{g['cohort']}: no on-time 30s quoted changes")
    print('Whole quote-export groups are retained separately; no skipped returns are imputed.')
    audit=out['reconciliation']['summary'];h=audit['horizons']['30000']
    print(f"Reconciliation at 30s: paired={h['paired']}; opposite signs={h['oppositeSigns']}; large disagreements with close receipts/original pool/on-time quote={h['largeCloseOriginalPoolOnTime']}")
    print('Entry history:',audit['entryHistoryStates'],'; provider market freshness remains unverified.')
    print('Upload: '+str(a.output.absolute()))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Only our fixed validation messages are surfaced for ValueError; parser errors can include supplied text.
        reason=str(exc) if type(exc) is ValueError else type(exc).__name__
        print('Joined report stopped: '+reason+'. No partial report published.',file=sys.stderr)
        raise SystemExit(1)
