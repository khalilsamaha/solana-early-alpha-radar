"""Join feed provenance to validated price/quote cases; descriptive, not causal."""
from collections import Counter, defaultdict
from analyze import ALIASES
from feed_timing import project, state, distribution

VERSION='paired-feed-audit-1'
PROTOCOL={'largeDifferencePercentagePoints':20,'closeReceiptMs':5000,'tightReceiptMs':1000,
          'shortLocalPipelineMs':1000,'purpose':'diagnostic-only; no eligibility or return changes'}

def evidence(row,kind,expected_price,expected_pool,expected_receipt=None):
    if row is None:return {'state':'source-record-unavailable','record':None}
    feed=project(row.get('feedEvidence'));status=state(feed,row,kind)
    if status=='recorded-local-timing':
        if feed['priceUsd']!=expected_price or feed['pairAddress']!=expected_pool:status='comparison-binding-mismatch'
        elif expected_receipt is None or not feed['bodyAt']<=expected_receipt<=feed['appliedAt']:status='comparison-clock-mismatch'
    if status!='recorded-local-timing':return {'state':status,'record':None}
    return {'state':status,'record':feed,'localPipelineMs':feed['appliedAt']-feed['queuedAt'],
            'reportedPriceUnchangedMs':feed['bodyAt']-feed['priceUnchangedSince']
                if feed.get('priceUnchangedSince') is not None and feed['priceUnchangedSince']<=feed['bodyAt'] else None,
            'recordAfterApplyMs':row['at']-feed['appliedAt'],'cacheEvidence':cache(feed)}

def cache(feed):
    if (feed.get('httpAgeSeconds') or 0)>0:return 'positive-http-age'
    if feed.get('cfCacheStatus')=='HIT':return 'cache-hit-without-positive-age'
    if feed.get('cfCacheStatus')=='MISS':return 'reported-cache-miss'
    return 'other-or-unknown'

def route_scope(buy,exit,pool):
    br=buy.get('route') or {};er=exit.get('route') or {}
    if br.get('tokenPools') is None or er.get('tokenPools') is None:return 'unavailable'
    if br['tokenPools']==[pool] and er['tokenPools']==[pool]:return 'original-only-token-pools'
    if br.get('originalPoolPresent') is True and er.get('originalPoolPresent') is True:return 'original-plus-other-token-pools'
    return 'original-pool-absent-in-at-least-one-leg'

def summarize(rows):
    paired=[r for r in rows if r['comparisonState']=='paired']
    strict=[r for r in paired if r['closeOriginalPoolOnTime']]
    timed=[r for r in strict if r['bothTimingsUsable']]
    large=[r for r in timed if r['largeDifference']]
    return {'records':len(rows),'comparisonStates':dict(Counter(r['comparisonState'] for r in rows)),
        'entryTimingStates':dict(Counter(r['entryTiming']['state'] for r in rows)),
        'checkpointTimingStates':dict(Counter(r['checkpointTiming']['state'] for r in rows)),
        'paired':len(paired),'largeDifferences':sum(r['largeDifference'] is True for r in paired),
        'closeOriginalPoolOnTime':len(strict),'closeOriginalPoolOnTimeWithBothTimings':len(timed),
        'largeCloseOriginalPoolOnTimeWithBothTimings':len(large),
        'largeWithBothLocalPipelinesWithin1s':sum(r['bothLocalPipelinesWithin1s'] is True for r in large),
        'largeWithBothCacheMiss':sum(r['entryTiming']['cacheEvidence']=='reported-cache-miss' and r['checkpointTiming']['cacheEvidence']=='reported-cache-miss' for r in large),
        'largeWithPositiveHttpAge':sum(r['entryTiming']['cacheEvidence']=='positive-http-age' or r['checkpointTiming']['cacheEvidence']=='positive-http-age' for r in large),
        'largeWithReceiptsWithin1s':sum(r['receiptsWithin1s'] is True for r in large),
        'largeRouteScopes':dict(Counter(r['routeScope'] for r in large)),
        'entryLocalPipelineMs':distribution([r['entryTiming']['localPipelineMs'] for r in timed]),
        'checkpointLocalPipelineMs':distribution([r['checkpointTiming']['localPipelineMs'] for r in timed])}

def audit(capture,joined,reconciliation):
    # Inputs are recomputed by build(), not trusted uploaded summaries.
    entries={(r['kind'],r['eventId']):r['data'] for r in capture['entries']}
    outcomes={(r['kind'],r['data'].get('entryId'),ALIASES.get(r['data'].get('horizon'))):r['data'] for r in capture['outcomes']}
    recon={r['entryId']:r for r in reconciliation['cases']};rows=[];cutoff=joined['commonWindow']['cutoffAt']
    for case in joined['cases']:
        if case['observer'].get('decision')!='admitted':continue
        ref=recon[case['entryId']];source=entries[(case['entryKind'],case['entryId'])]
        ent=evidence(source,'entries',case['priceUsd'],case['pairAddress'],ref['entryReference']['localReceiptAt'])
        kind='fast-shadow-outcomes' if case['entryKind']=='fast-shadow-entries' else 'research-outcomes'
        for h in ('30000','60000','120000'):
            point=ref['horizons'][h];paper=case['outcomes'][str(int(h)//1000)+'s'];quote=case['quote']['exits'][h]
            raw=outcomes.get((kind,case['entryId'],str(int(h)//1000)+'s'))
            if point['paperState']!='observed':end={'state':'paper-'+point['paperState'],'record':None}
            elif raw is None or raw.get('at',cutoff+1)>cutoff:end={'state':'source-record-unavailable','record':None}
            else:end=evidence(raw,'outcomes',point['paperPriceUsd'],case['pairAddress'],point['paperLocalReceiptAt'])
            both=ent['state']==end['state']=='recorded-local-timing'
            strict=point.get('closeReceipts') is True and point.get('originalPoolReported') is True and point.get('buyOriginalPoolReported') is True and point.get('quoteOnTime') is True
            delta=point.get('paperMinusQuoteReceiptMs')
            rows.append({'entryId':case['entryId'],'observerSeq':case['observer']['seq'],'mint':case['mint'],
                'cohort':case['cohort'],'samplingPolicy':case['observer']['samplingPolicy'],'horizonMs':int(h),
                'comparisonState':point['state'],'paperState':point['paperState'],'quoteState':point['quoteState'],
                'signalToBuyRequestMs':ref['signalToBuyRequestMs'],'signalToBuyResponseMs':ref['signalToBuyResponseMs'],
                'paperReturnPct':point['paperReturnPct'],'quotedChangePct':point['quotedChangePct'],
                'differencePercentagePoints':point['differencePercentagePoints'],'largeDifference':point['largeDifference'],
                'paperMinusQuoteReceiptMs':delta,'receiptsWithin1s':abs(delta)<=1000 if delta is not None else None,
                'closeOriginalPoolOnTime':strict,'routeScope':route_scope(case['quote']['buy'],quote,case['pairAddress']),
                'entryTiming':ent,'checkpointTiming':end,'bothTimingsUsable':both,
                'bothLocalPipelinesWithin1s':ent['localPipelineMs']<=1000 and end['localPipelineMs']<=1000 if both else None})
    groups=defaultdict(list)
    for row in rows:
        record=row['checkpointTiming'].get('record') or {}
        groups[(row['horizonMs'],row['cohort'],row['samplingPolicy'] or 'unknown',record.get('endpoint') or 'unknown',row['checkpointTiming'].get('cacheEvidence','unknown'))].append(row)
    return {'version':VERSION,'sourceIdentity':joined['sourceIdentity'],'commonWindow':joined['commonWindow'],
        'protocol':PROTOCOL,'admittedWatches':joined['admitted'],
        'horizons':{str(h):summarize([r for r in rows if r['horizonMs']==h]) for h in (30000,60000,120000)},
        'groups':[{'horizonMs':k[0],'cohort':k[1],'samplingPolicy':k[2],'checkpointEndpoint':k[3],'checkpointCacheEvidence':k[4],**summarize(v)} for k,v in sorted(groups.items())],
        'cases':rows,'limitations':[
          'Sub-second local clocks do not establish upstream price age or simultaneous market state.',
          'HTTP cache MISS does not rule out upstream caching, aggregation or price-source differences.',
          'Original-only token pools refers only to reported token-touching route legs; other conversion legs and route costs can remain.',
          'Unquoted, missing, gapped and invalid evidence is retained without fabricated returns.',
          'These are admitted nonrandom watches. Entry repeats across horizons, shared requests and repeated mints are not independent samples.',
          'No fees are inferred or subtracted, no quote is a fill, and no diagnostic group is a validated trading filter.']}
