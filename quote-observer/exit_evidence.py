"""Derived, walletless evidence. No network, database writes or return imputation."""
import collections
import math
import statistics

VERSION='exit-evidence-1'
OFFSETS=(0,30000,60000,120000)
FIELDS=('liquidityUsd','organicScore','top10Pct','marketCap','holderCount',
        'averageReportedTradeUsd','transactions5m','volume5mUsd','unchangedForMs',
        'return30sPct','return60sPct','marketObservedAt','securityCheckedAt','jupiterCheckedAt')

def number(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)

def delta(a,b):
    return a-b if number(a) and number(b) else None

def describe(xs,total):
    return {'admitted':total,'quotedReturns':len(xs),'withoutQuotedReturn':total-len(xs),
            'meanQuotedChangePct':statistics.mean(xs) if xs else None,
            'medianQuotedChangePct':statistics.median(xs) if xs else None,
            'positive':sum(x>0 for x in xs),'lossAtLeast50':sum(x<=-50 for x in xs),
            'meanExcludingBestPct':(sum(xs)-max(xs))/(len(xs)-1) if len(xs)>1 else None}

def probe_evidence(p,cutoff):
    signal=p.get('signal') or {};obs=p.get('observations') or []
    if len(obs)>5:raise ValueError('More than five observations in a probe')
    buys=[o for o in obs if o.get('leg')=='buy']
    if len(buys)>1:raise ValueError('Duplicate buy observation')
    buy=buys[0] if buys else None
    by_offset={}
    for o in obs:
        if o.get('leg')!='sell':continue
        t=o.get('targetOffsetMs')
        if t not in OFFSETS or t in by_offset:raise ValueError('Invalid or duplicate sell offset')
        by_offset[t]=o
    sat=signal.get('signalAt');received=buy.get('receivedAt') if buy else None
    bought=bool(buy and buy.get('status')=='quoted');running=p.get('state')=='running'
    exits=[]
    for offset in OFFSETS:
        o=by_offset.get(offset);due=received+offset if number(received) else None
        if o:
            status=o.get('status')
            if status=='quoted':state='sell-quote-returned'
            elif status=='skipped':state='not-sampled'
            elif status=='interrupted':state='interrupted'
            else:state='sell-quote-failed'
        elif buy and not bought:state='not-sampled-buy-failed'
        elif running:
            # The first nominal zero-offset sample is spaced after the buy.
            buy_start=buy.get('startedAt') if buy else None
            latest=(max(due,buy_start+10000 if number(buy_start) else due)+23000) if due is not None else None
            state='pending' if latest is None or cutoff<=latest else 'overdue-unrecorded'
        else:state='incomplete-unrecorded'
        o=o or {}
        timings={'signalAt':sat,'buyRequestAt':buy.get('startedAt') if buy else None,
                 'buyResponseAt':received,'scheduledAt':due,
                 'requestAt':o.get('startedAt'),'responseAt':o.get('receivedAt'),
                 'requestFromSignalMs':delta(o.get('startedAt'),sat),
                 'responseFromSignalMs':delta(o.get('receivedAt'),sat),
                 'requestFromBuyResponseMs':delta(o.get('startedAt'),received),
                 'responseFromBuyResponseMs':delta(o.get('receivedAt'),received),
                 'requestAfterScheduledMs':delta(o.get('startedAt'),due)}
        invalid=any(v is not None and v<0 for k,v in timings.items() if k.endswith('Ms'))
        if number(o.get('receivedAt')) and number(o.get('startedAt')) and o['receivedAt']<o['startedAt']:invalid=True
        quoted=o.get('quotedUsdcChangePct') if state=='sell-quote-returned' and number(o.get('quotedUsdcChangePct')) else None
        exits.append({'targetOffsetMs':offset,'targetClock':'buy-response','state':state,
          'quoteStatus':o.get('status'),'reason':o.get('reason'),'providerCategory':o.get('providerCategory'),
          'quotedUsdcChangePct':quoted,'timing':timings,'invalidTiming':invalid,
          'originalPoolInRoute':o.get('originalPoolInRoute'),'executionVerified':False})
    features=signal.get('features') or {}
    flags=[]
    if features.get('liquidityUsd') is None:flags.append('liquidity-unknown')
    if features.get('security')!='limited checks complete':flags.append('limited-security-checks-not-complete')
    if features.get('securityCheckedAt') is None:flags.append('security-timestamp-unknown')
    if features.get('disposition')=='defer':flags.append('research-deferred')
    if features.get('historyReady') is not True:flags.append('research-history-not-ready')
    if number(features.get('averageReportedTradeUsd')) and features['averageReportedTradeUsd']<5:flags.append('small-average-reported-trade')
    if buy and number(buy.get('priceImpactPercentagePoints')) and abs(buy['priceImpactPercentagePoints'])>=5:flags.append('large-provider-reported-buy-impact')
    return {'seq':signal.get('seq'),'entryId':signal.get('entryId'),'mint':signal.get('mint'),
      'symbol':signal.get('symbol'),'cohort':signal.get('cohort'),
      'samplingPolicy':p.get('samplingPolicy','first-arrival-v0.2.0'),
      'featureCaptureVersion':(signal.get('featureCapture') or {}).get('version','legacy'),
      'signalAt':sat,'probeState':p.get('state'),'buyStatus':buy.get('status') if buy else 'unrecorded',
      'signalToBuyRequestMs':delta(buy.get('startedAt'),sat) if buy else None,
      'signalToBuyResponseMs':delta(received,sat),
      'entryEvidenceFlags':flags,'exits':exits}

def summarize(report):
    if report.get('format')!='quote-observer-report-0.2.0':raise ValueError('Unsupported quote report')
    ps=report.get('probes',[])
    if len(ps)>20000:raise ValueError('Probe cap exceeded')
    cutoff=report.get('capturedAt')
    if not number(cutoff):raise ValueError('Missing evidence cutoff')
    cases=[];seen=set();groups={};availability={};shadow={}
    registration=report.get('featureCaptureRegistration') or {}
    for p in ps:
        s=p.get('signal') or {};seq=s.get('seq')
        if seq is not None:
            if seq in seen:raise ValueError('Duplicate probe sequence')
            seen.add(seq)
        c=probe_evidence(p,cutoff);cases.append(c)
        policy=c['samplingPolicy'];cohort=c['cohort'] or 'unknown';version=c['featureCaptureVersion']
        key=f'{policy}/{cohort}'
        group=groups.setdefault(key,{'admitted':0,'buyStates':collections.Counter(),'horizons':{}})
        group['admitted']+=1;group['buyStates'][c['buyStatus']]+=1
        av=availability.setdefault(f'{key}/{version}',{'admitted':0,'recordedNumericFields':collections.Counter()});av['admitted']+=1
        f=s.get('features') or {}
        for field in FIELDS:
            if number(f.get(field)):av['recordedNumericFields'][field]+=1
        valid_registration=(registration.get('id')=='entry-features-1' and (registration.get('shadow') or {}).get('id')=='average-reported-trade-5-v1' and (registration.get('shadow') or {}).get('thresholdUsd')==5)
        phase='prospective' if valid_registration and number(s.get('signalAt')) and number(registration.get('registeredAt')) and s['signalAt']>=registration['registeredAt'] and version=='entry-features-1' else 'not-prospective'
        average=f.get('averageReportedTradeUsd');bucket=('below-5' if average<5 else 'at-least-5') if number(average) and average>=0 else 'unknown'
        sg=shadow.setdefault(f'{key}/{phase}/{bucket}',{'admitted':0,'states':collections.Counter(),'_values':[]});sg['admitted']+=1
        for e in c['exits']:
            h=group['horizons'].setdefault(str(e['targetOffsetMs']),{'states':collections.Counter(),'invalidTimings':0,'_values':[]})
            h['states'][e['state']]+=1;h['invalidTimings']+=int(e['invalidTiming'])
            if e['quotedUsdcChangePct'] is not None:h['_values'].append(e['quotedUsdcChangePct'])
            if e['targetOffsetMs']==120000:
                sg['states'][e['state']]+=1
                if e['quotedUsdcChangePct'] is not None:sg['_values'].append(e['quotedUsdcChangePct'])
    for g in groups.values():
        for h in g['horizons'].values():h.update(describe(h.pop('_values'),g['admitted']))
    for sg in shadow.values():sg.update(describe(sg.pop('_values'),sg['admitted']))
    return {'version':VERSION,'sourceIdentity':report.get('sourceIdentity'),'cutoffAt':cutoff,
      'groups':groups,'cases':cases,'featureAvailability':availability,
      'activityShadow':{'registration':registration,'primaryOffsetMs':120000,'groups':shadow},
      'notes':['Quotes are not fills or net realized returns. Failed and skipped observations are never assigned returns.',
        'The nominal zero-second quote occurs after request spacing; actual timestamps are authoritative.',
        'Price continuity and exit quote availability are separate evidence.',
        'Feature presence does not establish freshness or safety. Legacy absent fields are not backfilled.',
        'Sampling is non-random. Activity groups are descriptive prospective research, not admission rules.',
        'No new requests, retries, scanner edits or trades are performed by this analysis.']}
