"""Compare fixed, previously registered entry rules against walletless quotes.

Never filters the collector or changes scanner/model results.
"""
import collections,math,statistics

RULES=('history-ready-v1','known-liquidity-5000-v1','qualified-liquidity-5000-v1')
REGISTERED_HASH='7ab1135047e3c2a4f520058ba3d803f58dcbdbe25e2b39f33683f2458d5c84f3'
def number(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def classify(features,rule):
    h=features.get('historyReady');liq=features.get('liquidityUsd');disposition=features.get('disposition')
    if rule=='history-ready-v1':return 'selected' if h is True else 'excluded' if h is False else 'unknown'
    known=number(liq) and liq>=0
    if rule=='known-liquidity-5000-v1':return ('selected' if liq>=5000 else 'excluded') if known else 'unknown'
    if rule!='qualified-liquidity-5000-v1':raise ValueError('Unknown rule')
    # Three-valued AND: a known false condition is excluded even if another is unknown.
    if (known and liq<5000) or disposition=='defer':return 'excluded'
    return 'selected' if known and liq>=5000 and disposition=='retain' else 'unknown'
def summary(values,total):
    return {'admitted':total,'observed':len(values),'notObserved':total-len(values),
      'meanPct':statistics.mean(values) if values else None,'medianPct':statistics.median(values) if values else None,
      'positive':sum(v>0 for v in values),'loss50':sum(v<=-50 for v in values),
      'meanExcludingBestPct':(sum(values)-max(values))/(len(values)-1) if len(values)>1 else None}
def compare(quotes,research):
    entries={e['id']:e for e in research['entries']};probes={p['signal']['seq']:p for p in quotes['probes']}
    signals={}
    for s in quotes.get('signals',[]):
        if s['seq'] in signals:raise ValueError('Duplicate signal sequence')
        signals[s['seq']]=s
    # Accommodate a probe that straddles an export boundary; explicitly tag it.
    for seq,p in probes.items():
        if seq not in signals:signals[seq]={**p['signal'],'decision':'admitted','recoveredFromProbe':True}
    registration=research.get('shadowRegistration',{})
    verified=registration.get('rulesSha256')==REGISTERED_HASH and number(registration.get('registeredAtMs'))
    groups={};cases=[];models=collections.defaultdict(list)
    for v in research['evaluation']['results']:
        if v['delayMs']==10000 and v.get('costBpsPerSide',0)==0:models[v['entryId']].append(v)
    for seq,s in signals.items():
        if s.get('cohort') not in ('baseline','early-activity') or not s.get('entryId'):continue
        features=s.get('features',{});entry=entries.get(s['entryId']);p=probes.get(seq)
        if entry and (s.get('mint'),s.get('signalAt'),s.get('cohort'),s.get('originalPool'))!=(entry['mint'],entry['at'],entry['cohort'],entry['pairAddress']):
            raise ValueError('Signal/research identity mismatch')
        phase=('prospective' if s['signalAt']>=registration['registeredAtMs'] else 'exploratory') if verified else 'registration-unverified'
        policy=s.get('samplingPolicy','first-arrival-v0.2.0')
        buckets={rule:classify(features,rule) for rule in RULES}
        decision=s.get('decision','unknown')
        for rule,bucket in buckets.items():
            key='/'.join((policy,phase,s['cohort'],rule,bucket))
            g=groups.setdefault(key,{'eligibleSignals':0,'decisions':collections.Counter(),'admitted':0,'matchedResearchEntries':0,'quoteOutcomes':{},'_probes':[]})
            g['eligibleSignals']+=1;g['decisions'][decision]+=1;g['matchedResearchEntries']+=int(entry is not None)
            if p:g['admitted']+=1;g['_probes'].append(p)
        if not p:continue
        observations=p.get('observations',[]);sell=[o for o in observations if o.get('leg')=='sell'];buy=next((o for o in observations if o.get('leg')=='buy'),{})
        mismatches=[]
        if entry:
            rf=entry.get('entryFeatures',{});rq=entry.get('qualification',{})
            other={'liquidityUsd':rf.get('liquidityUsd'),'disposition':rq.get('disposition'),'historyReady':rq.get('historyReady')}
            mismatches=[k for k,v in other.items() if v!=features.get(k)]
        deferred=features.get('disposition')=='defer' or features.get('historyReady') is False
        label='deferred-research' if deferred else 'entry-rule-candidate' if all(b=='selected' for b in buckets.values()) else 'incomplete-entry-evidence'
        cases.append({'seq':seq,'entryId':s['entryId'],'mint':s['mint'],'cohort':s['cohort'],'samplingPolicy':policy,'phase':phase,
          'entryClassification':label,'classificationIsTradeApproval':False,'ruleBuckets':buckets,'entryFeatures':features,
          'matchedResearch':entry is not None,'featureDisagreements':mismatches,'probeState':p['state'],
          'buyQuoteStatus':buy.get('status','unrecorded'),'sellQuoteStatuses':dict(collections.Counter(o.get('status') for o in sell)),
          'sellQuoteSuccesses':sum(o.get('status')=='quoted' for o in sell),'sellCheckpointsExpected':4,
          'buyAbsoluteReportedImpactAtLeast5':abs(buy['priceImpactPercentagePoints'])>=5 if number(buy.get('priceImpactPercentagePoints')) else None,
          'signalToBuyRequestMs':p.get('signalToBuyRequestMs'),
          'providerFailures':[{'leg':o.get('leg'),'targetOffsetMs':o.get('targetOffsetMs'),'httpStatus':o.get('httpStatus'),
             'category':o.get('providerCategory'),'diagnosticTerms':o.get('diagnosticTerms'),'fingerprint':o.get('messageFingerprint')}
             for o in observations if o.get('status') in ('http-error','provider-error')],
          'modelComparisons':[{'policy':v['policy'],'status':v['status'],'grossReturnPct':v.get('grossReturnPct'),
             'signalToEntryMs':v['simulatedEntryAt']-s['signalAt'] if number(v.get('simulatedEntryAt')) else None,
             'signalToExitMs':v['simulatedExitAt']-s['signalAt'] if number(v.get('simulatedExitAt')) else None}
             for v in models[s['entryId']]]})
    for g in groups.values():
        ps=g.pop('_probes');g['decisions']=dict(g['decisions'])
        for offset in (0,30000,60000,120000):
            rows=[o for p in ps for o in p.get('observations',[]) if o.get('leg')=='sell' and o.get('targetOffsetMs')==offset]
            vals=[o['quotedUsdcChangePct'] for o in rows if o.get('status')=='quoted' and number(o.get('quotedUsdcChangePct'))]
            g['quoteOutcomes'][str(offset)]={**summary(vals,len(ps)),'statuses':dict(collections.Counter(o.get('status') for o in rows))}
    return {'version':'qualification-quote-comparison-1','rules':list(RULES),'registration':registration,'registrationVerified':bool(verified),
      'groups':groups,'admittedCases':cases,
      'notes':['Rules are unchanged from research-tools 1.1.0; entry-time signal features only.',
        'Selected means meeting that rule, not approved to trade. Deferred research stays visible.',
        'Skipped signals have no quote outcome. Missing quotes are not assigned zero or a loss.',
        'Groups overlap across rules; do not add them together. Sampling policies remain separate.',
        'Model and quote entry/exit clocks differ. Gross model returns are not net quote returns.',
        'No new threshold was fitted to the outcomes in these reports.']}
