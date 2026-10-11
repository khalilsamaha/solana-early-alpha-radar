"""Registered fixed exit comparisons. No best-exit optimization or trade execution."""
import collections
from timing_analysis import finite, distribution
PROTOCOL={'id':'fixed-short-exits-1','primaryOffsetMs':30000,'comparisonOffsetsMs':[60000,120000],
    'maximumScheduleDelayMs':5000,'requestAllowanceMs':8000,'additionalProceedsHaircutBps':[0,100,300],
    'basis':'Fixed quantity quote observations; no trades, stop simulation or best-exit selection'}
OFFSETS=[30000,60000,120000]

def fixed_exits(data,quotes,joined):
    reg=data.get('fixedExitRegistration');cutoff=quotes.get('capturedAt')
    valid=(isinstance(reg,dict) and all(reg.get(k)==v for k,v in PROTOCOL.items())
        and finite(reg.get('registeredAt')) and finite(cutoff) and reg['registeredAt']<=data['cutoffAt'])
    groups=collections.defaultdict(list);cases=[];paired=collections.defaultdict(list)
    for c in joined['cases']:
        period=('unverified-source' if c['sourceIdentityState']!='matched' else
                'exploratory' if not valid or c['signalAt']<reg['registeredAt'] else 'forward')
        outcomes=[]
        for h in c['horizons']:
            target=h['targetOffsetMs']
            if target not in OFFSETS:continue
            state='buy-unavailable';value=None
            if c['buyState']=='validated-quote':
                due=c['buyResponseAt']+target
                if h['quoteState']=='validated-quote':
                    state='on-time-quote' if h['quoteScheduleDelayMs']<=PROTOCOL['maximumScheduleDelayMs'] else 'late-quote';value=h['quotedChangePct']
                elif h['quoteState']=='not-recorded':
                    state='pending' if cutoff<=due+PROTOCOL['maximumScheduleDelayMs']+PROTOCOL['requestAllowanceMs'] else 'missing-exit'
                else:state='failed-or-invalid-exit'
            item={'targetOffsetMs':target,'state':state,'quoteState':h['quoteState'],'quotedChangePct':value,'scheduleDelayMs':h.get('quoteScheduleDelayMs')}
            if value is not None and state=='on-time-quote':
                item['additionalProceedsHaircutPct']={str(bps):((1+value/100)*(1-bps/10000)-1)*100 for bps in PROTOCOL['additionalProceedsHaircutBps']}
            outcomes.append(item);groups[f"{period}/{c['samplingPolicy']}/{c['cohort']}/{target}"].append(item)
        cases.append({'sourceIdentity':c['sourceIdentity'],'seq':c['seq'],'entryId':c['entryId'],'period':period,'cohort':c['cohort'],
                      'samplingPolicy':c['samplingPolicy'],'outcomes':outcomes})
        if len(outcomes)==3 and all(x['state']=='on-time-quote' for x in outcomes):
            paired[f"{period}/{c['samplingPolicy']}/{c['cohort']}"].append({x['targetOffsetMs']:x['quotedChangePct'] for x in outcomes})
    summary={}
    for k,rs in groups.items():
        usable=[x for x in rs if x['state']=='on-time-quote']
        summary[k]={'admitted':len(rs),'states':dict(collections.Counter(x['state'] for x in rs)),
            'quotedChangePct':distribution([x['quotedChangePct'] for x in usable]),
            'additionalProceedsHaircuts':{str(b):distribution([x['additionalProceedsHaircutPct'][str(b)] for x in usable]) for b in PROTOCOL['additionalProceedsHaircutBps']}}
    pairs={k:{'completeCases':len(rs),'return60Minus30PercentagePoints':distribution([r[60000]-r[30000] for r in rs]),
        'return120Minus30PercentagePoints':distribution([r[120000]-r[30000] for r in rs])} for k,rs in paired.items()}
    return {'version':PROTOCOL['id'],'registration':reg,'registrationValid':valid,'protocol':PROTOCOL,'groups':summary,'cases':cases,'completeCaseComparisons':pairs,
        'limitations':['30 seconds is the registered primary exit; 60 and 120 seconds are fixed comparators. No hindsight best-exit selection.',
            'Forward means signal at or after persisted registration with matching database identity. Historical replay remains exploratory.',
            'Failures, late quotes, pending observations and missing exits are retained and excluded explicitly from numerical averages, never assigned zero.',
            'Complete-case comparisons omit failed/missing paths and may be biased; consult full admission denominators.',
            'Haircuts are additional proceeds stress scenarios, not measured fees or a net execution model. Quotes may already reflect some fees.',
            'No fills, wallet simulation, stop-loss enforcement or profitability claim. Cohort admission is capacity-limited and not random.']}
