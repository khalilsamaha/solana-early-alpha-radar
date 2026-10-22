#!/usr/bin/env python3
"""Offline, entry-label comparison. No rule fitting, network or database access."""
import argparse, collections, datetime, gzip, hashlib, json, math, statistics, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launch-study'))
from join_quotes import probe_case, COHORTS, OFFSETS, IDENTITY_FIELDS
from report import publish

VERSION='qualification-review-1'
def number(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def stamp(x):return type(x) is int and 0<x<9007199254740992
def describe(xs,total):
    return {'admitted':total,'validatedQuotedReturns':len(xs),'withoutValidatedReturn':total-len(xs),
        'meanPct':statistics.mean(xs) if xs else None,'medianPct':statistics.median(xs) if xs else None,
        'positive':sum(x>0 for x in xs),'lossAtLeast50':sum(x<=-50 for x in xs),
        'meanExcludingBestPct':statistics.mean(sorted(xs)[:-1]) if len(xs)>1 else None}
def qualification(s):
    f=s.get('features') or {};q=f.get('disposition')
    bucket=q if q in ('retain','defer') else 'unknown'
    verified=(f.get('qualificationVersion')=='qualification-1' and f.get('qualificationMode')=='shadow'
        and stamp(f.get('qualificationAt')) and f['qualificationAt']<=s['signalAt'])
    return bucket,'qualification-1' if verified else 'version-unrecorded-or-invalid'
def flags(s):
    f=s.get('features') or {};out=[]
    if f.get('disposition')=='defer':out.append('entry-shadow-deferred')
    if f.get('disposition') not in ('retain','defer'):out.append('entry-qualification-unknown')
    if f.get('historyReady') is not True:out.append('continuous-history-not-confirmed')
    if not number(f.get('liquidityUsd')) or f['liquidityUsd']<0:out.append('liquidity-unknown')
    if f.get('security')!='limited checks complete':out.append('limited-security-checks-not-complete')
    if not stamp(f.get('securityCheckedAt')) or f['securityCheckedAt']>s['signalAt']:out.append('security-timestamp-unavailable')
    return out
def pricing(o):
    """Only descriptive provider fields; never deduct impact/fees from output again."""
    fields=('inUsdValue','outUsdValue','swapUsdValue','priceImpactPercentagePoints','feeBps',
        'signatureFeeLamports','prioritizationFeeLamports','rentFeeLamports','slippageBps')
    result={k:o[k] if number(o.get(k)) else None for k in fields}
    result['version']=o.get('pricingEvidenceVersion') if o.get('pricingEvidenceVersion')=='quote-pricing-1' else 'legacy-unrecorded'
    result['router']=o.get('router') if o.get('router') in ('metis','dflow','jupiterz','okx') else 'other-or-unknown'
    result['missingUsdValuation']=any(result[k] is None for k in ('inUsdValue','outUsdValue'))
    return result
def build(report):
    if report.get('format')!='quote-observer-report-0.2.0':raise ValueError('Unsupported report')
    source=report.get('sourceIdentity');cutoff=report.get('capturedAt')
    if not isinstance(source,str) or len(source)>128 or not stamp(cutoff):raise ValueError('Missing source identity or cutoff')
    signals={};probes={};ignored=0
    for name,target in [('signals',signals),('probes',probes)]:
        rows=report.get(name,[])
        if not isinstance(rows,list) or len(rows)>20000:raise ValueError('Row cap or schema')
        for row in rows:
            s=row if name=='signals' else row.get('signal',{})
            seq=s.get('seq')
            if type(seq) is not int or seq<1 or seq in target:raise ValueError('Invalid or duplicate sequence')
            target[seq]=row
    recovered=0
    for seq,p in probes.items():
        s=p.get('signal',{})
        if seq not in signals:signals[seq]={**s,'decision':'admitted'};recovered+=1
        else:
            a=signals[seq]
            if any(a.get(k)!=s.get(k) for k in IDENTITY_FIELDS) or a.get('features')!=s.get('features') or a.get('featureCapture')!=s.get('featureCapture') or a.get('entryContext')!=s.get('entryContext'):
                raise ValueError('Signal/probe entry evidence mismatch')
            if a.get('decision')!='admitted':raise ValueError('Probe attached to nonadmitted signal')
    groups={};cases=[]
    for seq,s in sorted(signals.items()):
        if s.get('cohort') not in COHORTS:ignored+=1;continue
        if not stamp(s.get('signalAt')) or not stamp(s.get('detectedAt')) or s['signalAt']>s['detectedAt'] or s['detectedAt']>cutoff:raise ValueError('Invalid signal clocks')
        bucket,version=qualification(s);policy=s.get('samplingPolicy','unrecorded')
        if not isinstance(policy,str) or len(policy)>96:raise ValueError('Invalid policy')
        key='/'.join((policy,s['cohort'],version,bucket))
        g=groups.setdefault(key,{'samplingPolicy':policy,'cohort':s['cohort'],'qualificationVersion':version,
            'disposition':bucket,'signals':0,'decisions':collections.Counter(),'admitted':0,'buyStates':collections.Counter(),
            'horizons':{},'byUtcDay':{}})
        g['signals']+=1;decision=s.get('decision','unknown');g['decisions'][decision]+=1
        if decision!='admitted':continue
        g['admitted']+=1;p=probes.get(seq);e=probe_case(p,s,cutoff);g['buyStates'][e['buy']['state']]+=1
        day=datetime.datetime.fromtimestamp(s['signalAt']/1000,datetime.timezone.utc).date().isoformat()
        daily=g['byUtcDay'].setdefault(day,{'admitted':0,'horizons':{}});daily['admitted']+=1
        observations=p.get('observations',[]) if p else []
        raw_buy=next((o for o in observations if o.get('leg')=='buy'),{})
        case={'sourceIdentity':source,'seq':seq,'entryId':s.get('entryId'),'mint':s.get('mint'),
            'cohort':s['cohort'],'samplingPolicy':policy,'disposition':bucket,'qualificationVersion':version,
            'entryEvidenceFlags':flags(s),'buy':e['buy'],'buyPricing':pricing(raw_buy),'exits':e['exits']}
        for h in OFFSETS:
            x=e['exits'][str(h)];o=next((o for o in observations if o.get('leg')=='sell' and o.get('targetOffsetMs')==h),{})
            x['pricing']=pricing(o)
            x['label']='first reverse quote after spacing' if h==0 else f'{h//1000}s after buy response'
            x['actualResponseAfterBuyMs']=o['receivedAt']-raw_buy['receivedAt'] if stamp(o.get('receivedAt')) and stamp(raw_buy.get('receivedAt')) else None
            for dest in (g,daily):
                v=dest['horizons'].setdefault(str(h),{'states':collections.Counter(),'onTimeCount':0,'_values':[],'_onTime':[]})
                v['states'][x['state']]+=1
                if x['state']=='validated-sell-quote':
                    v['_values'].append(x['quotedChangePct'])
                    # The 0 offset is deliberately spacing-delayed, not an instantaneous round-trip.
                    if h!=0 and not x.get('lateBeyond5s') and not x.get('responseBeyond8s'):v['_onTime'].append(x['quotedChangePct'])
        cases.append(case)
    for g in groups.values():
        for dest in [g,*g['byUtcDay'].values()]:
            for h,v in dest['horizons'].items():
                v.update(describe(v.pop('_values'),dest['admitted']))
                ontime=v.pop('_onTime');v['onTimeCount']=len(ontime)
                v['onTime']=describe(ontime,dest['admitted']) if h!='0' else None
    return {'format':VERSION,'sourceIdentity':source,'capturedAt':cutoff,'windowStartAt':report.get('windowStartAt'),
        'recoveredSignalsFromProbes':recovered,'ignoredOtherCohortSignals':ignored,'groups':groups,'cases':cases,
        'protocol':{'mode':'descriptive-existing-entry-labels','offsetsMs':list(OFFSETS),'changesAdmissions':False,
            'zeroOffsetIsImmediate':False,'promotionDecision':'none'},
        'limitations':['Stored labels are compared without recomputing or tuning qualification thresholds.',
            'Legacy labels lack recorded qualification version and remain a separate group; no historical backfill.',
            'Nonrandom samples, overlapping tokens and market regimes prevent causal or profitability conclusions.',
            'Skipped signals have no quote return; failed, missing and invalid quotes stay in admitted denominators.',
            'No liquidity/security pass is inferred from a retain label or a returned quote.',
            'Quoted output already reflects provider routing; reported impact and fees are not deducted again.',
            'The first reverse quote is about ten seconds later, not an instantaneous fee/spread estimate.',
            'USD valuations and route amounts are provider evidence, not independently verified market prices or fills.',
            'Do not add overlapping exports together; use source identity plus sequence to identify repeated cases.']}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with (gzip.open(a.input,'rb') if a.input.suffix=='.gz' else a.input.open('rb')) as f:raw=f.read(64*1024*1024+1)
    if len(raw)>64*1024*1024:raise ValueError('Input cap exceeded')
    r=build(json.loads(raw,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON'))))
    r['inputSha256']=hashlib.sha256(raw).hexdigest();publish(a.output,r)
    for key,g in r['groups'].items():
        h=g['horizons'].get('30000',{});print(key,': signals=',g['signals'],'admitted=',g['admitted'],'valid30s=',h.get('validatedQuotedReturns',0),'mean=',h.get('meanPct'))
    print('Upload: '+str(a.output.resolve()))
if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('Qualification review stopped: invalid input, evidence mismatch, cap or output permissions. No partial report published.')
