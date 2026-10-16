"""Fixed descriptive review. Outcomes are never inputs to signal admission or models."""
from collections import Counter,defaultdict
from statistics import mean,median
VERSION='exit-availability-review-1'
OFFSETS=(30000,120000)

def classify(case,probe,h):
    if case is None:return 'not-admitted'
    if case['buy']['state']!='validated-buy-quote':return 'no-validated-buy'
    e=case['exits'][str(h)];state=e['state']
    if state=='validated-sell-quote':
        return 'late-validated-quote' if e.get('lateBeyond5s') or e.get('responseBeyond8s') else 'on-time-validated-quote'
    if state=='sell-quote-failed':
        o=next((o for o in (probe or {}).get('observations',[]) if o.get('leg')=='sell' and o.get('targetOffsetMs')==h),{})
        if o.get('httpStatus')==400 and e.get('providerCategory')=='quote-generation-failure-reported':return 'provider-reported-quote-failure'
        status=o.get('status');code=o.get('httpStatus')
        if status in ('timeout','network-or-json-error','rate-limited','access-denied') or (type(code) is int and code>=500):return 'transport-or-service-failure'
        return 'other-quote-failure'
    if state=='interrupted':return 'interrupted'
    if state in ('unfinished-at-cutoff','after-cutoff'):return 'pending-or-after-cutoff'
    if state in ('not-sampled','skip-time-unavailable'):return 'not-sampled'
    if state in ('incomplete-unrecorded','overdue-unrecorded','admitted-probe-not-exported','not-recorded'):return 'missing-observation'
    return 'invalid-evidence'

def review(rows):
    groups=defaultdict(list)
    for row in rows:
        ctx=row['supplementalEntryContext'];metadata=ctx.get('metadataProvenance') or {}
        key=(row['samplingPolicy'],row['cohort'],row['featureCaptureVersion'],metadata.get('version') or 'metadata-unrecorded')
        groups[key].append(row)
    result=[]
    for key,items in sorted(groups.items()):
        admitted=[r for r in items if r['decision']=='admitted'];horizons={}
        for h in OFFSETS:
            states=Counter(r['exitAvailability'][str(h)] for r in admitted)
            values=[r['targets'][str(h)]['returnPct'] for r in admitted if r['exitAvailability'][str(h)]=='on-time-validated-quote']
            horizons[str(h)]={'admitted':len(admitted),'states':dict(states),'onTimeReturned':len(values),
                'onTimePositive':sum(v>0 for v in values),'meanOnTimeQuotedChangePct':mean(values) if values else None,
                'medianOnTimeQuotedChangePct':median(values) if values else None,
                'meanOnTimeExcludingBestPct':(sum(values)-max(values))/(len(values)-1) if len(values)>1 else None}
        result.append({'samplingPolicy':key[0],'cohort':key[1],'featureCaptureVersion':key[2],
          'metadataVersion':key[3],'signals':len(items),'admitted':len(admitted),
          'buyStates':dict(Counter(r['buyQuoteState'] for r in admitted)),
          'metadataCoverage':{field:{'states':dict(Counter(((r['supplementalEntryContext'].get('metadataProvenance') or {}).get('fields',{}).get(field) or {}).get('state','not-recorded') for r in items)),
            'sources':dict(Counter(p['source'] for r in items if (p:=((r['supplementalEntryContext'].get('metadataProvenance') or {}).get('fields',{}).get(field) or {})).get('state')=='recorded'))}
            for field in ('organicScore','holderCount')},
          'excludedDecisions':dict(Counter(r['decision'] for r in items if r['decision']!='admitted')),'horizons':horizons})
    return {'version':VERSION,'primaryOffsetMs':30000,'secondaryOffsetMs':120000,'groups':result,
      'mode':'descriptive-offline-only','changesAdmissions':False,
      'limitations':['Provider-reported failure is not proof of permanent unsellability.',
        'Late quotes, failed buys, missing observations, transport failures and provider failures stay separate.',
        'Return summaries use only validated on-time quotes. All admitted watches remain in state counts.',
        'No failure or missing return is replaced with zero. No imputed P&L, model selection or live approval.',
        'Sampling is nonrandom; results cannot be generalized to unsampled signals.']}
