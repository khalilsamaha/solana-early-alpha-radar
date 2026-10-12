"""Descriptive paper/quote reconciliation. No market-time, decimals or fills inferred."""
import collections
import math
import statistics
from analyze import finite, timestamp, ALIASES
from join_quotes import atomic

VERSION='price-reconciliation-1'
HORIZONS=(30000,60000,120000)
PROTOCOL={'primaryOffsetMs':30000,'rebasedComparatorsMs':[60000,120000],
    'largeDifferencePercentagePoints':20,'closeReceiptToleranceMs':5000,
    'maximumScheduleDelayMs':5000,'maximumQuoteResponseMs':8000,
    'purpose':'diagnostic triage only; no strategy selection or root-cause attribution'}


def number_summary(values):
    values=[v for v in values if finite(v)]
    return {'count':len(values),'median':statistics.median(values) if values else None,
        'min':min(values) if values else None,'max':max(values) if values else None}


def entry_reference(e,source,signal):
    ev=source.get('priceEvidence');history_state='not-exported';latest=None
    if ev is not None:
        history_state='invalid'
        if isinstance(ev,dict) and ev.get('version')=='entry-price-projection-1' and ev.get('basis')=='provider-response-time' and ev.get('poolAddress')==e['pairAddress']:
            samples=ev.get('samples');n=ev.get('sourceSampleCount')
            if isinstance(samples,list) and len(samples)<=24 and type(n) is int and len(samples)<=n<=256 and ev.get('truncated')==(n>24):
                valid=all(isinstance(p,dict) and timestamp(p.get('at')) and p['at']<=e['entryAt'] and finite(p.get('price')) and p['price']>0 for p in samples)
                valid=valid and all(samples[i]['at']<samples[i+1]['at'] for i in range(len(samples)-1))
                if valid:
                    history_state='recorded' if samples else 'empty'
                    latest=samples[-1] if samples else None
    receipt=None;receipt_state='unavailable';receipt_sources=[]
    if latest:
        receipt=latest['at'];receipt_sources.append('entry.evidence.samples.last.at');receipt_state='recorded-local-receipt'
    # A matched immutable observer signal can supply an independent exported receipt.
    if signal:
        fc=signal.get('featureCapture') or {};features=signal.get('features') or {}
        clock=features.get('marketObservedAt');meta=(fc.get('sources') or {}).get('marketObservedAt') or {}
        expected='quality.lastObservedAt' if e['cohort']=='fast30-shadow' else 'evidence.inputs.marketObservedAt'
        if clock is not None:
            valid=(fc.get('version') in ('entry-features-1','fast-entry-features-1') and fc.get('signalAt')==e['entryAt']
                and meta.get('state')=='recorded' and meta.get('source')==expected and timestamp(clock) and clock<=e['entryAt'])
            if not valid:receipt_state='invalid-observer-receipt';receipt=None
            elif receipt is not None and clock!=receipt:receipt_state='conflicting-recorded-receipts';receipt=None
            else:receipt=clock;receipt_state='recorded-local-receipt';receipt_sources.append('observer.'+expected)
    match=(math.isclose(latest['price'],e['priceUsd'],rel_tol=1e-12,abs_tol=0) if latest else None)
    return {'paperEntryPriceUsd':e['priceUsd'],'signalAt':e['entryAt'],'historyState':history_state,
        'latestHistoryObservation':latest,'latestHistoryMatchesEntryPrice':match,
        'receiptState':receipt_state,'localReceiptAt':receipt,'receiptSources':receipt_sources,
        'localReceiptAgeAtSignalMs':e['entryAt']-receipt if receipt is not None else None,
        'providerMarketTimestamp':None,'providerFreshness':'not-established',
        'tokenDecimals':'not-verified','absoluteQuoteUnitPriceUsd':None}


def reconcile(capture,quotes,joined):
    # Callers must supply freshly recomputed join output, never uploaded derived summaries.
    raw={x['eventId']:x['data'] for x in capture['entries']}
    signals={x['seq']:x for x in quotes['signals']}
    outcomes={(x['kind'],x['data'].get('entryId'),ALIASES.get(x['data'].get('horizon'))):x['data'] for x in capture['outcomes']}
    rows=[]
    for e in joined['cases']:
        s=signals.get(e['observer']['seq']) if e['observer']['state']=='matched' else None
        reference=entry_reference(e,raw[e['entryId']],s)
        horizons={};rebased={}
        for h in HORIZONS:
            x=e['quote']['exits'][str(h)];paper=e['outcomes'][str(h//1000)+'s']
            valid_paper=paper['state']=='observed';valid_quote=x['state']=='validated-sell-quote'
            point={'paperState':paper['state'],'quoteState':x['state'],'state':'unpaired',
                'paperPriceUsd':None,'paperReturnPct':None,'quotedChangePct':None,'differencePercentagePoints':None,
                'paperLocalReceiptAt':paper['sampleAt'],'quoteResponseAt':x.get('responseAt'),
                'paperMinusQuoteReceiptMs':None,'oppositeSigns':None,'largeDifference':None,
                'closeReceipts':None,'originalPoolReported':None,'quoteOnTime':None,
                'buyOriginalPoolReported':(e['quote']['buy'].get('route') or {}).get('originalPoolPresent'),
                'providerCategory':x.get('providerCategory')}
            if valid_paper:
                point['paperReturnPct']=paper['grossPriceChangePct']
                kind='fast-shadow-outcomes' if e['entryKind']=='fast-shadow-entries' else 'research-outcomes'
                point['paperPriceUsd']=outcomes[(kind,e['entryId'],str(h//1000)+'s')]['priceUsd']
            if valid_quote:
                point.update(quotedChangePct=x['quotedChangePct'],originalPoolReported=x['route']['originalPoolPresent'],
                    tokenRouteChanged=x['tokenRouteChanged'],quoteOnTime=not x['lateBeyond5s'] and not x['responseBeyond8s'])
            if valid_paper and valid_quote:
                delta=paper['sampleAt']-x['responseAt'];diff=paper['grossPriceChangePct']-x['quotedChangePct']
                point.update(state='paired',paperMinusQuoteReceiptMs=delta,differencePercentagePoints=diff,
                    oppositeSigns=paper['grossPriceChangePct']*x['quotedChangePct']<0,
                    largeDifference=abs(diff)>=PROTOCOL['largeDifferencePercentagePoints'],
                    closeReceipts=abs(delta)<=PROTOCOL['closeReceiptToleranceMs'])
                point['triage']='large-disagreement-close-receipts-original-pool' if point['largeDifference'] and point['closeReceipts'] and point['originalPoolReported'] and point['buyOriginalPoolReported'] is True and point['quoteOnTime'] else 'other-paired'
            horizons[str(h)]=point
        # Rebase BOTH paths at 30s: fixed token quantity cancels; no decimals assumed.
        anchor=horizons['30000']
        for h in (60000,120000):
            endpoint=horizons[str(h)]
            value={'state':'unavailable','anchorOffsetMs':30000,'endOffsetMs':h,
                'paperChangePct':None,'quotedProceedsChangePct':None,'differencePercentagePoints':None}
            if anchor['state']=='paired' and endpoint['state']=='paired':
                pa=anchor['paperPriceUsd'];pb=endpoint['paperPriceUsd']
                qa=atomic(e['quote']['exits']['30000']['outputAtomic']);qb=atomic(e['quote']['exits'][str(h)]['outputAtomic'])
                if pa>0 and pb>0:
                    pp=(pb/pa-1)*100;qp=(qb-qa)/qa*100;diff=pp-qp
                    value.update(state='paired-rebased',paperChangePct=pp,quotedProceedsChangePct=qp,differencePercentagePoints=diff,
                        largeDifference=abs(diff)>=PROTOCOL['largeDifferencePercentagePoints'],
                        bothReceiptsClose=anchor['closeReceipts'] and endpoint['closeReceipts'],
                        bothOriginalPoolReported=anchor['originalPoolReported'] is True and endpoint['originalPoolReported'] is True,
                        bothQuotesOnTime=anchor['quoteOnTime'] and endpoint['quoteOnTime'])
                    value['entryDisagreementAndRebasedDisagreement']=anchor['largeDifference'] and value['largeDifference']
            rebased[str(h)]=value
        rows.append({'entryId':e['entryId'],'sourceSeq':e['sourceSeq'],'observerSeq':e['observer']['seq'],'mint':e['mint'],
            'cohort':e['cohort'],'samplingPolicy':e['observer']['samplingPolicy'],'observerDecision':e['observer']['decision'],
            'entryReference':reference,'buyState':e['quote']['buy']['state'],
            'signalToBuyRequestMs':e['quote']['buy'].get('signalToRequestMs'),
            'signalToBuyResponseMs':e['quote']['buy'].get('signalToResponseMs'),
            'horizons':horizons,'rebased':rebased})
    groups=collections.defaultdict(list)
    for r in rows:groups[(r['cohort'],r['samplingPolicy'] or 'unknown')].append(r)
    def summarize(rs):
        hs={};re={}
        for h in HORIZONS:
            ps=[r['horizons'][str(h)] for r in rs];paired=[p for p in ps if p['state']=='paired']
            hs[str(h)]={'states':dict(collections.Counter(p['state'] for p in ps)),
                'quoteStates':dict(collections.Counter(p['quoteState'] for p in ps)),
                'paired':len(paired),'oppositeSigns':sum(p['oppositeSigns'] for p in paired),
                'largeDifferences':sum(p['largeDifference'] for p in paired),
                'largeCloseOriginalPoolOnTime':sum(p.get('triage')=='large-disagreement-close-receipts-original-pool' for p in paired),
                'paperMinusQuoteReceiptMs':number_summary([p['paperMinusQuoteReceiptMs'] for p in paired])}
        for h in (60000,120000):
            ps=[r['rebased'][str(h)] for r in rs];valid=[p for p in ps if p['state']=='paired-rebased']
            re[str(h)]={'paired':len(valid),'unavailable':len(ps)-len(valid),
                'largeDifferences':sum(p['largeDifference'] for p in valid),
                'largeCloseOriginalPoolOnTime':sum(p['largeDifference'] and p['bothReceiptsClose'] and p['bothOriginalPoolReported'] and p['bothQuotesOnTime'] for p in valid),
                'entryAndRebasedDisagreement':sum(p['entryDisagreementAndRebasedDisagreement'] for p in valid)}
        return {'entries':len(rs),'admitted':sum(r['observerDecision']=='admitted' for r in rs),
            'entryHistoryStates':dict(collections.Counter(r['entryReference']['historyState'] for r in rs)),
            'entryReceiptStates':dict(collections.Counter(r['entryReference']['receiptState'] for r in rs)),
            'entryHistoryPriceMismatches':sum(r['entryReference']['latestHistoryMatchesEntryPrice'] is False for r in rs),
            'horizons':hs,'rebased':re}
    return {'version':VERSION,'sourceIdentity':joined['sourceIdentity'],'commonWindow':joined['commonWindow'],
        'protocol':PROTOCOL,'summary':summarize(rows),
        'groups':[{'cohort':k[0],'samplingPolicy':k[1],**summarize(v)} for k,v in sorted(groups.items())],
        'cases':rows,'limitations':[
            'Local receipts are not underlying exchange timestamps. Close receipt times do not prove simultaneous market data.',
            'No token decimals are inferred, no absolute quoted token unit price is calculated, and no quote becomes a fill.',
            'Rebased quoted proceeds compare two separate hypothetical sells of the same fixed token quantity. They are not a new trade or exit policy.',
            'A persistent rebased disagreement cannot be attributed solely to the initial price reference; its cause remains unverified.',
            'Large/close diagnostic thresholds classify evidence, not safety, profitability or signal eligibility.',
            'Missing projected entry history in older reports remains not-exported; a fresh read can project retained immutable history.',
            'Quote failures are provider evidence, not proof of permanent unsellability. No missing return is imputed.']}
