"""Bounded pool evidence and backward-only response-clock comparisons, offline."""
import collections
from timing_analysis import finite, distribution, timing_distribution
VERSION='pool-timing-evidence-1'
MAX_PRIOR_AGE_MS=20000

def points_for(entry,outcomes,cutoff):
    points={};alternates=[];available=False;partial=False
    for holder in [entry,*outcomes]:
        path=holder.get('pathEvidence')
        if not path or path.get('version')!=VERSION:continue
        available=True;partial |= bool(path.get('partialHistory'))
        rows=path.get('points',[])
        if not isinstance(rows,list) or len(rows)>8:raise ValueError('Path point bound exceeded')
        extras=[path[k] for k in ['firstAlternate','alternateAtCheckpoint'] if path.get(k)]
        for x in [*rows,*extras]:
            if not isinstance(x,dict) or not isinstance(x.get('pairAddress'),str) or not x['pairAddress']:raise ValueError('Invalid path pool')
            if not all(finite(x.get(k)) for k in ['sampleAt','recordedAt','priceUsd']):raise ValueError('Invalid path numbers')
            if not(entry['at']<=x['sampleAt']<=x['recordedAt']<=holder['at']<=cutoff) or x['priceUsd']<=0:raise ValueError('Invalid path clock or price')
            if x['recordedAt']-x['sampleAt']>45000:raise ValueError('Stale path response')
            key=(x['pairAddress'],x['sampleAt'])
            if key in points and points[key]['priceUsd']!=x['priceUsd']:raise ValueError('Conflicting path point')
            if key not in points or x['recordedAt']<points[key]['recordedAt']:points[key]=x
        alt=path.get('alternateAtCheckpoint')
        if alt:
            ms={'30s':30000,'60s':60000,'120s':120000,'300s':300000}.get(holder.get('horizon'))
            if not ms or alt['pairAddress']==entry['pairAddress'] or not entry['at']+ms<=alt['sampleAt']<=alt['recordedAt']<=entry['at']+ms+30000:raise ValueError('Invalid alternate checkpoint')
            alternates.append({'horizon':holder['horizon'],'originalStatus':holder['status'],'originalCoverage':holder.get('coverage'),'observation':alt,'crossPoolReturnComputed':False})
    return sorted(points.values(),key=lambda x:(x['recordedAt'],x['sampleAt'])),alternates,available,partial

def path_analysis(data,joined=None):
    entries={e['id']:e for e in data['fast-shadow-entries']};by_entry=collections.defaultdict(list)
    for o in data['fast-shadow-outcomes']:
        if o['entryId'] in entries:by_entry[o['entryId']].append(o)
    paths={};pool_cases=[];aligned=[];groups=collections.defaultdict(list)
    for eid,e in entries.items():
        pts,alts,available,partial=points_for(e,by_entry[eid],data['cutoffAt']);paths[eid]=(pts,available,partial)
        pool_cases.append({'entryId':eid,'state':'recorded' if available else 'legacy-unavailable','partialHistory':partial,
            'distinctObservedPools':sorted({x['pairAddress'] for x in pts}),'alternateCheckpoints':alts})
    for c in (joined or {}).get('cases',[]):
        if c['joinState']!='matched' or c['sourceIdentityState']!='matched':continue
        e=entries[c['entryId']];pts,available,partial=paths[c['entryId']]
        for h in c['horizons']:
            if h['targetOffsetMs']==0:continue
            row={'entryId':c['entryId'],'seq':c['seq'],'targetOffsetMs':h['targetOffsetMs'],
                'state':'path-unavailable' if not available else 'quote-unavailable','partialHistory':partial,
                'quoteState':h['quoteState'],'priorPriceChangePct':None,'quotedChangePct':h['quotedChangePct']}
            if available and h['quoteState']=='validated-quote':
                request=h['quoteRequestAt']
                before=[p for p in pts if p['pairAddress']==e['pairAddress'] and p['recordedAt']<=request and request-p['sampleAt']<=MAX_PRIOR_AGE_MS]
                row['state']='no-recent-prior-original-pool-response'
                if before:
                    p=max(before,key=lambda x:(x['sampleAt'],x['recordedAt']));change=(p['priceUsd']/e['priceUsd']-1)*100
                    row.update(state='prior-response-paired',priorObservation=p,quoteRequestAt=request,priorAgeAtQuoteRequestMs=request-p['sampleAt'],
                        priorPriceChangePct=change,differencePercentagePoints=change-h['quotedChangePct'],oppositeSigns=change*h['quotedChangePct']<0,
                        withinFiveSeconds=request-p['sampleAt']<=5000)
            aligned.append(row);groups[str(h['targetOffsetMs'])].append(row)
    summary={}
    for k,rs in groups.items():
        paired=[x for x in rs if x['state']=='prior-response-paired']
        summary[k]={'cases':len(rs),'states':dict(collections.Counter(x['state'] for x in rs)),'paired':len(paired),
            'withinFiveSeconds':sum(x['withinFiveSeconds'] for x in paired),'oppositeSigns':sum(x['oppositeSigns'] for x in paired),
            'priorAgeAtQuoteRequestMs':timing_distribution([x['priorAgeAtQuoteRequestMs'] for x in paired]),
            'paperMinusQuotePercentagePoints':distribution([x['differencePercentagePoints'] for x in paired])}
    return {'version':VERSION,'maximumPriorAgeMs':MAX_PRIOR_AGE_MS,'poolCases':pool_cases,'alignmentCases':aligned,'alignmentGroups':summary,
        'poolSummary':{'entries':len(pool_cases),'states':dict(collections.Counter(c['state'] for c in pool_cases)),
            'entriesWithAlternateCheckpoint':sum(bool(c['alternateCheckpoints']) for c in pool_cases),
            'missingOriginalWithAlternate':sum(a['originalStatus']=='missing' for c in pool_cases for a in c['alternateCheckpoints'])},
        'limitations':['Only received observations already captured by the scanner; no new requests or reconstructed legacy prices.',
            'Alternative pool prices are separate evidence; no migration inference or cross-pool return substitution.',
            'Alignment uses only observations recorded before the quote request, at most 20 seconds old. No interpolation or identical-time claim.',
            'Paper entry price and quoted buy valuation still differ. Differences are not measured slippage or profit; response time is not exchange time.']}
