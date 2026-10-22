"""Two fixed, independent Fast30 entry hypotheses, with explicit forward registration."""
import collections
from timing_analysis import analyze_timing, finite, distribution
VERSION='fast-evidence-1'
RULES=[{'id':'known-liquidity-5000-v1','field':'liquidityUsd','operator':'gte','threshold':5000},
       {'id':'return30-at-most-50-v1','field':'return30sPct','operator':'lte','threshold':50}]

def evaluate(features,rule):
    v=features.get(rule['field'])
    if not finite(v):return 'unknown'
    passed=v>=rule['threshold'] if rule['operator']=='gte' else v<=rule['threshold']
    return 'selected' if passed else 'excluded'

def entry_shadows(data,joined=None):
    reg=data.get('evidenceRegistration');registered=bool(reg and reg.get('id')==VERSION and reg.get('rules')==RULES and finite(reg.get('registeredAt')))
    cohorts=collections.defaultdict(list);cases=[]
    for e in data['fast-shadow-entries']:
        saved=e.get('shadowEvaluation');period='exploratory'
        features={'liquidityUsd':e.get('liquidityUsd'),'return30sPct':e.get('decision',{}).get('return30sPct')}
        if saved:
            valid=(registered and saved.get('version')==VERSION and saved.get('registeredAt')==reg['registeredAt']
                and saved.get('featureAt')==e['at'] and e['at']>=reg['registeredAt'] and isinstance(saved.get('features'),dict)
                and all(saved['features'].get(k)==v for k,v in features.items())
                and saved.get('groups')=={r['id']:evaluate(features,r) for r in RULES})
            period='forward' if valid else 'invalid-registration-or-features'
        elif registered and e['at']>=reg['registeredAt']:period='missing-forward-evaluation'
        followup=e.get('followup',{});policy=followup.get('policy','legacy-unprioritized')+'/'+('admitted' if followup.get('admitted') else 'not-admitted')
        groups={r['id']:evaluate(features,r) if period not in ['invalid-registration-or-features','missing-forward-evaluation'] else 'unknown' for r in RULES}
        cases.append({'entryId':e['id'],'period':period,'followupPolicy':policy,'features':features,'groups':groups})
        for rule,group in groups.items():cohorts[f'{period}/{policy}/{rule}/{group}'].append(e)
    summaries={};quote_cases=(joined or {}).get('cases',[])
    for name,entries in cohorts.items():
        ids={e['id'] for e in entries};subset={**data,'fast-shadow-entries':entries,
            'fast-shadow-outcomes':[o for o in data['fast-shadow-outcomes']if o['entryId']in ids],
            'fast-shadow-links':[l for l in data['fast-shadow-links']if l['entryId']in ids]}
        quote_groups=collections.defaultdict(list)
        for c in quote_cases:
            if c['entryId'] not in ids or c['joinState']!='matched':continue
            for h in c['horizons']:
                quote_groups[f"{c['samplingPolicy']}/{c['sourceIdentityState']}/{h['targetOffsetMs']}"].append(h)
        summaries[name]={'paper':analyze_timing(subset)['all'],'quotes':{
            k:{'probes':len(v),'states':dict(collections.Counter(h['quoteState']for h in v)),
               'quotedChangePct':distribution([h['quotedChangePct']for h in v if h['quotedChangePct']is not None])}
            for k,v in quote_groups.items()}}
    return {'version':VERSION,'registration':reg,'registrationValid':registered,'rules':RULES,'groups':summaries,'entries':cases,
        'limitations':['Hypotheses specified after inspecting earlier reports; exploratory results are not validation.',
          'Forward evidence starts at persisted scanner registration; groups do not change admissions or notifications.',
          'Rules are independent, not a combined trading strategy. Unknown values stay separate.',
          'Eventual cohort links and subsequent outcomes are never entry features.',
          'Quotes sample only admitted watches; skipped entries have no inferred quote return.']}

def missing_diagnostics(data):
    groups=collections.defaultdict(collections.Counter);cases=[]
    entries={e['id']:e for e in data['fast-shadow-entries']}
    for o in data['fast-shadow-outcomes']:
        if o['entryId']not in entries:continue
        e=entries[o['entryId']];policy=e.get('followup',{}).get('policy','legacy-unprioritized')
        if o.get('status')=='observed' and o.get('coverage')=='sampled':continue
        d=o.get('diagnostics');code=o.get('reasonCode') or ('observed-gapped-path' if o.get('status')=='observed' else 'legacy-unspecified')
        groups[f"{policy}/{o['horizon']}"][code]+=1
        cases.append({'entryId':o['entryId'],'horizon':o['horizon'],'status':o.get('status'),'coverage':o.get('coverage'),
            'reasonCode':code,'diagnostics':d,'historicalReason':o.get('reason')})
    return {'groups':{k:dict(v)for k,v in groups.items()},'cases':cases,
        'note':'Recorded evidence, not inferred root cause. Existing missing records cannot be retrospectively classified.'}
