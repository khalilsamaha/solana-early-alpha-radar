"""Offline Fast30 price/quote joins. Exact identity; no interpolation or inferred fills."""
import collections
import math
from timing_analysis import analyze_timing, distribution, timing_distribution, finite

USDC='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
OFFSETS={30000:'30s',60000:'60s',120000:'120s'}

def atomic(v):
    if not isinstance(v,str) or not v.isascii() or not v.isdecimal() or len(v)>20:
        raise ValueError('Invalid atomic amount')
    n=int(v)
    if not 0<n<=2**64-1: raise ValueError('Atomic amount outside u64')
    return n

def clocks(o,signal):
    return all(finite(o.get(k)) for k in ['startedAt','receivedAt']) and signal<=o['startedAt']<=o['receivedAt']

def join_quotes(data,quotes):
    if quotes.get('format')!='quote-observer-report-0.2.0': raise ValueError('Unsupported quote report')
    if len(quotes.get('probes',[]))>1000: raise ValueError('Too many probes')
    # Validate stored price arithmetic/pools/windows with the existing reader first.
    analyze_timing(data)
    entries={e['id']:e for e in data['fast-shadow-entries']}
    outcomes={(o['entryId'],o['horizon']):o for o in data['fast-shadow-outcomes']}
    source=data.get('sourceIdentity');other=quotes.get('sourceIdentity')
    source_state='matched' if source and source==other else 'mismatch' if source and other else 'unavailable-legacy'
    cases=[];seen=set();groups=collections.defaultdict(list)
    for p in quotes.get('probes',[]):
        s=p['signal'];key=(other,s['seq'])
        if key in seen: raise ValueError('Duplicate source/sequence probe')
        seen.add(key)
        obs=p.get('observations',[])
        if len(obs)>5:raise ValueError('Too many quote observations')
        buys=[o for o in obs if o.get('leg')=='buy'];buy=buys[0] if len(buys)==1 else None
        e=entries.get(s.get('entryId'));match='matched'
        if s.get('cohort')!='fast30-shadow':match='cohort-not-in-fast-report'
        elif source_state=='mismatch':match='source-mismatch'
        elif e is None:match='entry-outside-price-export'
        elif e.get('mint')!=s.get('mint') or e.get('pairAddress')!=s.get('originalPool') or e.get('at')!=s.get('signalAt') or e.get('priceUsd')!=s.get('entryPriceUsd'):
            match='entry-identity-mismatch'
        bvalid=False
        if buy and buy.get('status')=='quoted':
            try:
                bvalid=(clocks(buy,s['signalAt']) and buy['inputMint']==USDC==p['baseMint'] and buy['outputMint']==s['mint']
                        and atomic(buy['inAmount'])==atomic(p['inputAtomic']) and atomic(buy['outAmount'])>0)
            except (KeyError,ValueError,TypeError):pass
        sells={}
        for o in obs:
            if o.get('leg')!='sell':continue
            offset=o.get('targetOffsetMs')
            if offset not in [0,*OFFSETS] or offset in sells:raise ValueError('Invalid or duplicate exit target')
            sells[offset]=o
        rows=[]
        for offset in [0,*OFFSETS]:
            o=sells.get(offset);h=OFFSETS.get(offset);po=outcomes.get((s.get('entryId'),h))
            row={'targetOffsetMs':offset,'quoteState':'not-recorded','paperState':match if match!='matched' else 'no-corresponding-checkpoint' if h is None else 'not-recorded',
                 'quotedChangePct':None,'paperChangePct':None,'differencePercentagePoints':None}
            if o:
                row.update(quoteState=o.get('status','invalid'),quoteRequestAt=o.get('startedAt'),quoteResponseAt=o.get('receivedAt'),
                    quoteInputAtomic=o.get('inAmount'),quoteOutputAtomic=o.get('outAmount'),
                    tokenPools=o.get('tokenPools'),originalPoolInRoute=o.get('originalPoolInRoute'),
                    router=o.get('router'),routePlan=o.get('routePlan'),reportedPriceImpactPct=o.get('priceImpactPercentagePoints'),
                    reportedFeeBps=o.get('feeBps'),reportedFeeMint=o.get('feeMint'),reportedSlippageBps=o.get('slippageBps'))
                if o.get('status')=='quoted':
                    try:
                        if not bvalid or not clocks(o,buy['receivedAt']) or o['startedAt']<buy['receivedAt']+offset or o['inputMint']!=s['mint'] or o['outputMint']!=USDC or atomic(o['inAmount'])!=atomic(buy['outAmount']):raise ValueError()
                        row.update(quoteState='validated-quote',quotedChangePct=(atomic(o['outAmount'])-atomic(buy['inAmount']))/atomic(buy['inAmount'])*100,
                            signalToQuoteRequestMs=o['startedAt']-s['signalAt'],buyResponseToQuoteRequestMs=o['startedAt']-buy['receivedAt'],
                            quoteScheduleDelayMs=o['startedAt']-buy['receivedAt']-offset,
                            routeChangedSinceBuy=(o['tokenPools']!=buy['tokenPools']) if isinstance(o.get('tokenPools'),list) and isinstance(buy.get('tokenPools'),list) else None)
                    except (ValueError,KeyError,TypeError):row['quoteState']='invalid-quantity-mint-or-clock'
            if match=='matched' and po and h:
                row.update(paperState=po.get('status','invalid'),paperObservedAt=po.get('sampleAt'),paperPriceUsd=po.get('priceUsd'),
                    paperCoverage=po.get('coverage'),paperReason=po.get('reasonCode',po.get('reason')))
                if po.get('status')=='observed':
                    good=(po.get('coverage')=='sampled' and po.get('pairAddress')==e['pairAddress'] and finite(po.get('sampleAt'))
                          and e['at']+offset<=po['sampleAt']<=e['at']+offset+30000 and finite(po.get('priceUsd')) and po['priceUsd']>0
                          and finite(po.get('returnPct')) and finite(e.get('priceUsd')) and e['priceUsd']>0
                          and math.isclose(po['returnPct'],(po['priceUsd']/e['priceUsd']-1)*100,abs_tol=1e-8))
                    row['paperState']='validated-price' if good else 'gapped-or-invalid'
                    if good:row['paperChangePct']=po['returnPct']
            if row['quoteState']=='validated-quote' and row['paperState']=='validated-price':
                row.update(differencePercentagePoints=row['paperChangePct']-row['quotedChangePct'],
                    oppositeSigns=row['paperChangePct']*row['quotedChangePct']<0,
                    paperMinusQuoteReceiptMs=po['sampleAt']-o['receivedAt'],
                    comparison='different clocks and entry valuations; not measured slippage')
            rows.append(row)
            group=f"{p.get('samplingPolicy','legacy')}/{s['cohort']}/{source_state}/{offset}"
            groups[group].append(row)
        cases.append({'sourceIdentity':other,'seq':s['seq'],'entryId':s.get('entryId'),'mint':s.get('mint'),'cohort':s['cohort'],
            'samplingPolicy':p.get('samplingPolicy','legacy'),'sourceIdentityState':source_state,'joinState':match,
            'signalAt':s.get('signalAt'),'paperEntryPriceUsd':e.get('priceUsd') if match=='matched' else None,
            'paperEntryObservedAt':e.get('quality',{}).get('lastObservedAt') if match=='matched' else None,
            'buyState': 'validated-quote' if bvalid else 'invalid-quantity-mint-or-clock' if buy and buy.get('status')=='quoted' else buy.get('status') if buy else 'not-recorded',
            'buyRequestAt':buy.get('startedAt') if buy else None,'buyResponseAt':buy.get('receivedAt') if buy else None,
            'buyInputAtomic':buy.get('inAmount') if buy else None,'fixedTokenQuantityAtomic':buy.get('outAmount') if buy else None,
            'buyRoutePlan':buy.get('routePlan') if buy else None,'buyReportedPriceImpactPct':buy.get('priceImpactPercentagePoints') if buy else None,
            'buyUnitPriceUsd':None,'buyUnitPriceUnavailableReason':'Token decimals are not present in this quote export; atomic quantity is not whole tokens.',
            'horizons':rows})
    summary={}
    for k,rows in groups.items():
        summary[k]={'probes':len(rows),'quoteStates':dict(collections.Counter(r['quoteState'] for r in rows)),
            'paperStates':dict(collections.Counter(r['paperState'] for r in rows)),
            'quotedChangePct':distribution([r['quotedChangePct'] for r in rows if r['quotedChangePct'] is not None]),
            'paired':sum(r['differencePercentagePoints'] is not None for r in rows),
            'oppositeSigns':sum(r.get('oppositeSigns',False) for r in rows),
            'paperMinusQuoteReceiptMs':timing_distribution([r['paperMinusQuoteReceiptMs'] for r in rows if 'paperMinusQuoteReceiptMs' in r])}
    return {'version':'joined-price-quotes-1','sourceIdentityState':source_state,'groups':summary,'cases':cases,
        'limitations':['Fast30 exact entry joins only; other cohorts and missing/failed quotes retained explicitly.',
          'Legacy exports lack source identity; those joins are provisional, not verified provenance.',
          'No interpolation, identical-time claim, execution simulation, net profit or fee attribution.',
          'Zero-offset sell requests are delayed by request spacing; provider receipt time is not exchange time.']}
