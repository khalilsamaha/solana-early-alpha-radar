#!/usr/bin/env python3
"""Status and bounded report export. No credentials, scanner writes or network."""
import argparse, gzip, json, os, sqlite3, sys, time
from pathlib import Path
from exit_evidence import summarize
CONFIG=Path('/etc/solana-radar-quotes.json')

def read_report(config, hours=24, status=False):
    file=Path(config['reports'])/'observer.sqlite'
    if not file.is_file():raise RuntimeError('Observer has not created its ledger yet')
    started=time.monotonic();deadline=started+10
    with sqlite3.connect(file.as_uri()+'?mode=ro',uri=True,timeout=1) as db:
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-4096')
        db.set_progress_handler(lambda: int(time.monotonic()>deadline),1000)
        db.execute('BEGIN')
        now=int(time.time()*1000);cutoff=now-hours*3600000
        meta={k:json.loads(v) for k,v in db.execute('SELECT k,v FROM meta')}
        counts=[{'cohort':c,'decision':d,'count':n} for c,d,n in db.execute('SELECT cohort,decision,count(*) FROM signals WHERE detected>=? GROUP BY cohort,decision',(cutoff,))]
        probes=[{'state':s,'count':n} for s,n in db.execute('SELECT state,count(*) FROM probes WHERE at>=? GROUP BY state',(cutoff,))]
        capacity={}
        sampling=meta.get('samplingRegistration') or {}
        if sampling.get('id')=='cohort-budgets-v2':
            recent=list(db.execute('SELECT p.at,s.cohort FROM probes p LEFT JOIN signals s ON s.seq=p.seq WHERE p.at>? ORDER BY p.at',(now-86400000,)))
            for cohort in ('baseline','early-activity'):
                own=[at for at,c in recent if c==cohort];hour=[at for at in own if at>now-3600000]
                ready=now
                if own:ready=max(ready,own[-1]+1200000)
                if len(hour)>=3:ready=max(ready,hour[-3]+3600000)
                if len(own)>=72:ready=max(ready,own[-72]+86400000)
                capacity[cohort]={'hourUsed':len(hour),'dayUsed':len(own),'cohortBudgetOpensAt':ready,
                  'note':'Includes legacy admissions; global budget, busy, freshness and provider checks also apply.'}
        result={'format':'quote-observer-report-0.2.0','capturedAt':now,'windowStartAt':cutoff,'registeredAt':meta.get('registeredAt'),'limits':meta.get('limits'),'observerVersion':meta.get('version'),'samplingRegistration':meta.get('samplingRegistration'),'previousSamplingRegistration':meta.get('previousSamplingRegistration'),
          'cohortCapacity':capacity,'featureCaptureRegistration':meta.get('featureCaptureRegistration'),
          'lastPollAt':meta.get('lastPollAt'),'lastPollAgeSeconds':(now-meta['lastPollAt'])/1000 if meta.get('lastPollAt') else None,
          'halted':meta.get('halted'),'blockedUntil':meta.get('blockedUntil'),'signalCounts':counts,'probeCounts':probes,
          'limitations':['Quotes are not fills or proof of profitability.','Sampling policy is recorded per signal/probe; each policy must be analyzed separately.',
            'Repeated mint admissions suppressed for 24 hours. Overlapping exports must be deduplicated by source identity plus seq.',
            'No route quote for skipped signals; they are not losses, wins or zero returns.','Only quotes are sampled; no automatic buy, sell, stop-loss, or notification.',
            'Exit offsets are relative to buy response; signal offsets are recorded separately.','Seven days of observer evidence retained; scanner backup does not include this separate ledger.'],
          'sourceIdentity':meta.get('sourceIdentity')}
        if not status:
            size=0
            for key,sql in [('signals','SELECT data,decision FROM signals WHERE detected>=? ORDER BY seq LIMIT 20001'),('probes','SELECT data,state FROM probes WHERE at>=? ORDER BY seq LIMIT 20001')]:
                result[key]=[]
                for raw,tag in db.execute(sql,(cutoff,)):
                    size+=len(raw)
                    if size>32*1024*1024 or len(result[key])>=20000:raise RuntimeError('Export cap reached; narrow --hours. No partial report published')
                    row=json.loads(raw);row['decision' if key=='signals' else 'state']=tag;result[key].append(row)
            result['incidents']=[{'at':a,'kind':k,'detail':d} for a,k,d in db.execute('SELECT at,kind,detail FROM incidents WHERE at>=? ORDER BY at LIMIT 1001',(cutoff,))]
            if len(result['incidents'])>1000:raise RuntimeError('Incident cap reached; narrow --hours')
        db.rollback()
    result['readSeconds']=round(time.monotonic()-started,3)
    if not status:
        analysis_start=time.monotonic();result['exitEvidence']=summarize(result)
        result['analysisSeconds']=round(time.monotonic()-analysis_start,3)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['status','export']);p.add_argument('--hours',type=int,default=24)
    args=p.parse_args()
    if not 1<=args.hours<=168:p.error('--hours must be 1..168')
    config=json.loads(CONFIG.read_text());data=read_report(config,args.hours,args.action=='status')
    if args.action=='status':print(json.dumps(data,indent=2))
    else:
        # Stream bytes to caller. Run redirection as the normal user for file ownership.
        with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',mtime=0) as f:f.write(json.dumps(data,separators=(',',':')).encode())
if __name__=='__main__':
    try:main()
    except Exception as e:print('Quote report stopped: '+str(e),file=sys.stderr);sys.exit(1)
