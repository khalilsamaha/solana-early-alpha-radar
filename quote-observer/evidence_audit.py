#!/usr/bin/env python3
"""Offline audit: preserve model outcomes, annotate exit evidence and align timestamps."""
import argparse,collections,datetime,gzip,json,math,os,statistics,tempfile
from pathlib import Path
from qualification_analysis import compare
from exit_evidence import summarize, delta
VERSION='radar-evidence-audit-3'
def finite(x):return isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x)
def load(p):
    with (gzip.open(p,'rb') if str(p).endswith('.gz') else open(p,'rb')) as f:raw=f.read(128*1024*1024+1)
    if len(raw)>128*1024*1024:raise ValueError('Input exceeds 128 MiB decompressed limit')
    return json.loads(raw,parse_constant=lambda s:(_ for _ in ()).throw(ValueError('Nonfinite JSON value')))
def describe(xs):
    if not xs:return {'observed':0,'meanPct':None,'medianPct':None}
    return {'observed':len(xs),'meanPct':statistics.mean(xs),'medianPct':statistics.median(xs),'positive':sum(x>0 for x in xs),
      'loss50':sum(x<=-50 for x in xs),'minPct':min(xs),'maxPct':max(xs),'meanExcludingBestPct':(sum(xs)-max(xs))/(len(xs)-1) if len(xs)>1 else None}
def liquidity_evidence(points,at,pool):
    exact=[p for p in points if p.get('at')==at and p.get('pairAddress')==pool]
    values={p.get('liquidityUsd') for p in exact if finite(p.get('liquidityUsd')) and p['liquidityUsd']>=0}
    if len(values)>1:return {'status':'conflicting','reportedUsd':None}
    if not exact or not values:return {'status':'unknown','reportedUsd':None}
    v=next(iter(values));state='near-zero' if v<=1 else 'at-or-below-10-usd' if v<=10 else 'thin-under-5000' if v<5000 else 'reported-at-least-5000'
    return {'status':state,'reportedUsd':v,'basis':'exact same-pool observation at model timestamp; not available trade depth'}
def point_record(p,entry,quote_time):
    if p is None:return None
    return {'at':p['at'],'offsetFromQuoteRequestMs':p['at']-quote_time,'priceUsd':p['price'],
      'priceChangeFromSignalPct':(p['price']/entry['price']-1)*100,'reportedLiquidityUsd':p.get('liquidityUsd'),
      'basis':p.get('basis'),'pool':p['pairAddress']}
def align_quote(entry,obs):
    if not finite(obs.get('startedAt')):return {'status':'no-request-timestamp'}
    t=obs['startedAt'];points=[p for p in entry['path'] if p.get('pairAddress')==entry['pairAddress'] and finite(p.get('price')) and p['price']>0 and finite(p.get('at'))]
    prior=max((p for p in points if p['at']<=t),key=lambda p:p['at'],default=None)
    after=min((p for p in points if p['at']>t),key=lambda p:p['at'],default=None)
    age=t-prior['at'] if prior else None
    return {'requestAt':t,'quoteStatus':obs.get('status'),'leg':obs.get('leg'),'targetOffsetMs':obs.get('targetOffsetMs'),
      'quotedUsdcChangePct':obs.get('quotedUsdcChangePct'),'originalPoolInRoute':obs.get('originalPoolInRoute'),
      'lastPriorObservation':point_record(prior,entry,t),'priorObservationAgeMs':age,'priorWithin5Seconds':age is not None and age<=5000,
      'nextObservationRetrospectiveOnly':point_record(after,entry,t),
      'note':'No interpolation. Price change uses scanner signal price; quoted change uses hypothetical quote input. These are different entry bases. Response timestamps do not prove underlying price freshness.'}
def audit(quotes,research):
    if quotes.get('format')!='quote-observer-report-0.2.0':raise ValueError('Unsupported quote export format')
    if research.get('format')!='radar-research-tools-1.1.0':raise ValueError('Expected research tools 1.1.0 report')
    entries={}
    for e in research['entries']:
        if e['id'] in entries:raise ValueError('Duplicate research entry ID')
        entries[e['id']]=e
    probes=quotes['probes'];seen=set()
    for p in probes:
        seq=p['signal']['seq']
        if seq in seen:raise ValueError('Duplicate quote sequence')
        seen.add(seq)
    out={'format':VERSION,'quoteCapturedAt':quotes['capturedAt'],'researchWindow':research['window'],
      'quoteRegisteredAt':quotes.get('registeredAt'),'sourceIdentity':quotes.get('sourceIdentity'),
      'notes':['Analysis only; inputs and original paper outcomes unchanged.','Failed, skipped, unknown and unresolved cases remain in their denominators.',
      'A route quote is not a fill or proof of sellability.','Liquidity flags apply equally to gains and losses and do not establish fraud or an executable loss.',
      'No quote is substituted for a differently timed model exit.','Sampling versions are separated; repeated exports overlap.'],
      'quoteGroups':{},'matchedProbes':[],'unmatchedProbes':[],'modelExitEvidence':[],'modelEvidenceCounts':{},
      'collection':{'signalCounts':quotes['signalCounts'],'probeCounts':quotes['probeCounts'],'incidents':quotes.get('incidents',[])}}
    obs=[o for p in probes for o in p.get('observations',[])]
    out['collection']['requestStatuses']=dict(collections.Counter(o.get('status') for o in obs))
    out['collection']['httpFailures']=dict(collections.Counter(str(o.get('httpStatus')) for o in obs if o.get('status')!='quoted'))
    out['collection']['admittedEntries']=len(probes)
    for policy in sorted({p.get('samplingPolicy','first-arrival-v0.2.0') for p in probes}):
        for cohort in ['baseline','early-activity']:
            group=[p for p in probes if p['signal']['cohort']==cohort and p.get('samplingPolicy','first-arrival-v0.2.0')==policy]
            if not group:continue
            for target in [0,30000,60000,120000]:
                rows=[o for p in group for o in p.get('observations',[]) if o.get('leg')=='sell' and o.get('targetOffsetMs')==target]
                xs=[o['quotedUsdcChangePct'] for o in rows if o.get('status')=='quoted' and finite(o.get('quotedUsdcChangePct'))]
                out['quoteGroups'][f'{policy}/{cohort}/{target}']={**describe(xs),'admitted':len(group),'notObserved':len(group)-len(xs),
                  'statuses':dict(collections.Counter(o.get('status') for o in rows)),'unrecorded':len(group)-len(rows),'basis':'quoted change, not net P&L'}
    for p in probes:
        s=p['signal'];e=entries.get(s['entryId'])
        if not e:out['unmatchedProbes'].append({'seq':s['seq'],'entryId':s['entryId'],'reason':'entry-not-in-research-export'});continue
        if (s['mint'],s['signalAt'],s['cohort'],s['originalPool'])!=(e['mint'],e['at'],e['cohort'],e['pairAddress']):raise ValueError('Matched ID has inconsistent entry identity')
        out['matchedProbes'].append({'seq':s['seq'],'entryId':s['entryId'],'symbol':s.get('symbol'),'cohort':s['cohort'],'state':p['state'],
          'signalToBuyRequestMs':p.get('signalToBuyRequestMs'),'observations':[align_quote(e,o) for o in p.get('observations',[])]})
    counts=collections.Counter()
    for row in research['evaluation']['results']:
        # The exported model contains zero-cost base rows. Retain all delays/policies, never refit them.
        e=entries[row['entryId']];status=row['status']
        item={k:row.get(k) for k in ['entryId','cohort','policy','delayMs','costBpsPerSide','status','reason','simulatedEntryAt','simulatedExitAt','grossReturnPct']}
        item['symbol']=e.get('symbol');item['mint']=e['mint'];item['originalPool']=e['pairAddress'];item['entryEvidence']=liquidity_evidence(e['path'],row.get('simulatedEntryAt'),e['pairAddress'])
        item['exitEvidence']=liquidity_evidence(e['path'],row.get('simulatedExitAt'),e['pairAddress']) if status=='observed-model' else {'status':'model-unresolved-or-pending','reportedUsd':None}
        item['signalToModelEntryMs']=row['simulatedEntryAt']-e['at'] if finite(row.get('simulatedEntryAt')) else None
        item['signalToModelExitMs']=row['simulatedExitAt']-e['at'] if finite(row.get('simulatedExitAt')) else None
        item['executionVerified']=False
        counts[f"{e['cohort']}/{row['policy']}/delay{row['delayMs']}/{item['exitEvidence']['status']}"]+=1
        out['modelExitEvidence'].append(item)
    out['modelEvidenceCounts']=dict(counts)
    out['matchingSummary']={'quoteEntries':len(probes),'researchEntries':len(entries),'matched':len(out['matchedProbes']),'outsideResearchExport':len(out['unmatchedProbes'])}
    out['quoteExitEvidence']=summarize(quotes)
    matched={p['signal']['entryId']:p for p in probes if p['signal']['entryId'] in entries}
    out['clockComparisons']=[]
    for row in research['evaluation']['results']:
        p=matched.get(row['entryId'])
        if not p or row.get('policy') not in ('time-60','time-120'):continue
        target=60000 if row['policy']=='time-60' else 120000
        e=entries[row['entryId']];buy=next((o for o in p.get('observations',[]) if o.get('leg')=='buy'),{})
        sell=next((o for o in p.get('observations',[]) if o.get('leg')=='sell' and o.get('targetOffsetMs')==target),{})
        out['clockComparisons'].append({'entryId':e['id'],'symbol':e.get('symbol'),'cohort':e['cohort'],
          'policy':row['policy'],'modelDelayMs':row.get('delayMs'),'modelCostBpsPerSide':row.get('costBpsPerSide'),
          'signalAt':e['at'],'modelStatus':row.get('status'),
          'modelEntryAt':row.get('simulatedEntryAt'),'modelExitAt':row.get('simulatedExitAt'),
          'modelEntryFromSignalMs':delta(row.get('simulatedEntryAt'),e['at']),
          'modelExitFromSignalMs':delta(row.get('simulatedExitAt'),e['at']),
          'modelHoldingMs':delta(row.get('simulatedExitAt'),row.get('simulatedEntryAt')),
          'modelGrossReturnPct':row.get('grossReturnPct'),
          'quoteBuyRequestAt':buy.get('startedAt'),'quoteBuyResponseAt':buy.get('receivedAt'),
          'quoteSellRequestAt':sell.get('startedAt'),'quoteSellResponseAt':sell.get('receivedAt'),
          'quoteBuyRequestFromSignalMs':delta(buy.get('startedAt'),e['at']),
          'quoteSellRequestFromSignalMs':delta(sell.get('startedAt'),e['at']),
          'quoteSellFromBuyResponseMs':delta(sell.get('startedAt'),buy.get('receivedAt')),
          'modelExitMinusQuoteSellRequestMs':delta(row.get('simulatedExitAt'),sell.get('startedAt')),
          'quoteStatus':sell.get('status','unrecorded'),'quotedUsdcChangePct':sell.get('quotedUsdcChangePct') if sell.get('status')=='quoted' else None,
          'comparableAsSameExecution':False,
          'note':'Different entry bases and exit clocks; no interpolation, net-profit comparison or substitution.'})
    out['qualificationComparison']=compare(quotes,research)
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--quotes',type=Path,required=True);p.add_argument('--research',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=audit(load(a.quotes),load(a.research));raw=json.dumps(result,separators=(',',':'),allow_nan=False).encode()
    if len(raw)>64*1024*1024:raise ValueError('Output cap reached')
    # Exclusive creation preserves existing outputs and source files.
    with a.out.open('xb') as f:
        os.chmod(a.out,0o600)
        with gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as z:z.write(raw)
    print(json.dumps(result['matchingSummary']));print('Explicit model/quote clock comparisons:',len(result['clockComparisons']));print('Audit saved:',a.out.resolve())
if __name__=='__main__':main()
