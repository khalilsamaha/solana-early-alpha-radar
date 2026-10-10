"""Evidence explanations and frozen, entry-time-only shadow comparisons. No network."""
import collections
import hashlib
import json
from paper_model import finite, summary

VERSION = 'research-analysis-1'
RULES = [
    {'id':'history-ready-v1','definition':'Entry-time qualification.historyReady is true'},
    {'id':'known-liquidity-5000-v1','definition':'Entry-time reported liquidity is known and >= 5000 USD'},
    {'id':'qualified-liquidity-5000-v1','definition':'Known liquidity >= 5000 USD AND entry-time qualification disposition is retain'},
]
RULES_HASH = hashlib.sha256(json.dumps(RULES,sort_keys=True).encode()).hexdigest()
PRIMARY = (10000,100)
SCENARIOS = ((10000,100),(30000,100),(10000,300))


def features(row):
    c=row.get('candidate') or {};q=row.get('qualification') or {};m=q.get('metrics') or {}
    out={k:c.get(k) if finite(c.get(k)) else None for k in
         ('liquidityUsd','marketCap','organicScore','holderCount','top10Pct')}
    out.update({k:m.get(k) if finite(m.get(k)) else None for k in
        ('return30sPct','return60sPct','drawdownPct','liquidityChange30sPct','lastIntervalReturnPct',
         'unchangedForMs','averageReportedTradeUsd','transactions5m','volume5mUsd')})
    out['dexId']=c.get('dexId')[:64] if isinstance(c.get('dexId'),str) else None
    security=row.get('security') or (row.get('marketContext') or {}).get('security')
    out['security']=security if security in ('expired or unavailable','incomplete','adverse flags','limited checks complete') else None
    inputs=(row.get('evidence') or {}).get('inputs') or {}
    for name in ('marketObservedAt','securityCheckedAt','jupiterCheckedAt'):
        t=inputs.get(name);out[name]=t if finite(t) and t>0 and t<=row.get('at',0) else None
    out['basis']='recorded-at-entry; availability/freshness not independently verified'
    return out


def checkpoint(row):
    evidence=row.get('evidence') or {};attempt=evidence.get('lastAttempt') or {}
    follow=row.get('tokenFollowup') or {}
    return {'horizon':row.get('horizon'),'at':row.get('at'),'status':row.get('status'),
        'reasonCode':row.get('reasonCode'),'sampleAt':row.get('sampleAt'),
        'lastAttemptStatus':attempt.get('status'),
        'alternateFollowupStatus':follow.get('status'),
        'historyMaxSamples':(row.get('evidenceHistory') or {}).get('maxSamples')}


def rule_state(entry, rule):
    q=entry.get('qualification') or {};f=entry.get('entryFeatures') or {}
    if rule=='history-ready-v1':
        v=q.get('historyReady');return 'selected' if v is True else 'excluded' if v is False else 'unknown'
    liq=f.get('liquidityUsd')
    known=finite(liq) and liq>=0
    a='unknown' if not known else 'selected' if liq>=5000 else 'excluded'
    if rule=='known-liquidity-5000-v1':return a
    if rule!='qualified-liquidity-5000-v1':raise ValueError('Unknown comparison rule')
    b='selected' if q.get('disposition')=='retain' else 'excluded' if q.get('disposition')=='defer' else 'unknown'
    return 'excluded' if 'excluded' in (a,b) else 'unknown' if 'unknown' in (a,b) else 'selected'


def pool_evidence(entry,cutoff):
    ps=[p for p in entry.get('path',[]) if finite(p.get('at')) and entry['at']<=p['at']<=cutoff and finite(p.get('price')) and p['price']>0 and p.get('pairAddress')]
    original=[p for p in ps if p['pairAddress']==entry['pairAddress']]
    other=sorted({p['pairAddress'] for p in ps if p['pairAddress']!=entry['pairAddress']})
    return {'originalPool':entry['pairAddress'],'originalPoolSamples':len({p['at'] for p in original}),
        'lastOriginalPoolAt':max((p['at'] for p in original),default=None),
        'alternatePools':[{'pool':pool,'firstAt':min(p['at'] for p in ps if p['pairAddress']==pool),
                           'samples':len({p['at'] for p in ps if p['pairAddress']==pool})} for pool in other],
        'migrationVerified':False,'exitRouteVerified':False,
        'note':'Other-pool prices are observations only; no splicing into original-pool exits.'}


def evidence_state(entry,result,cutoff,pools):
    if result['status'] in ('observed-model','invalid'):return result['status']
    if result['status']=='pending':return 'policy-pending'
    age=cutoff-entry['at']
    five=any(c.get('horizon')=='5m' for c in entry.get('checkpoints',[]))
    if age<360000 and not five:return 'awaiting-checkpoint-evidence'
    return 'unresolved-with-alternate-pool' if pools['alternatePools'] else 'unresolved-original-pool-evidence'


def adjusted(row,bps):
    r=dict(row,costBpsPerSide=bps)
    if r['status']=='observed-model':r['netReturnPct']=(r['simulatedExitPrice']/r['simulatedEntryPrice']*(1-bps/10000)/(1+bps/10000)-1)*100
    return r


def loss_case(entry,row):
    ps=sorted([p for p in entry['path'] if p.get('pairAddress')==entry['pairAddress'] and
        row['simulatedEntryAt']<=p['at']<=row['simulatedExitAt'] and finite(p.get('price')) and p['price']>0],key=lambda p:p['at'])
    by_time={}
    for p in ps:by_time.setdefault(p['at'],p)
    ps=list(by_time.values())
    trigger=next((p for p in ps if p['at']==row['triggerAt']),None)
    steps=[{'fromAt':a['at'],'toAt':b['at'],'gapMs':b['at']-a['at'],
            'returnPct':(b['price']/a['price']-1)*100,
            'liquidityBeforeUsd':a.get('liquidityUsd'),'liquidityAfterUsd':b.get('liquidityUsd')} for a,b in zip(ps,ps[1:])]
    return {'entryId':entry['id'],'mint':entry.get('mint'),'symbol':entry.get('symbol'),'cohort':entry['cohort'],
        'policy':row['policy'],'netReturnPct':row['netReturnPct'],'exitReason':row['exitReason'],
        'entryDelayActualMs':row['entryDelayActualMs'],
        'triggerReturnPct':(trigger['price']/row['simulatedEntryPrice']-1)*100 if trigger else None,
        'triggerAt':row['triggerAt'],'exitAt':row['simulatedExitAt'],
        'largestObservedStepDown':min(steps,key=lambda p:p['returnPct'],default=None),
        'entryFeatures':entry.get('entryFeatures',{}),
        'triggerObservation':trigger,'exitObservation':ps[-1] if ps else None,
        'note':'Observed price collapse, not a verified rug, manipulation, or executable fill.'}


def analyze(report,registration=None):
    entries=report['entries'];cutoff=report['cutoffMs'];by_id={e['id']:e for e in entries}
    rows=report['evaluation']['results'];pools={e['id']:pool_evidence(e,cutoff) for e in entries}
    reg=registration or report.get('shadowRegistration')
    if reg is not None and (reg.get('rulesSha256')!=RULES_HASH or not finite(reg.get('registeredAtMs'))):
        raise ValueError('Shadow registration does not match frozen rules')
    registered=reg.get('registeredAtMs') if reg else None
    coverage=[];losses=[]
    for row in rows:
        if row['delayMs']!=10000:continue
        e=by_id[row['entryId']];p=pools[e['id']]
        coverage.append({'entryId':e['id'],'cohort':e['cohort'],'policy':row['policy'],
            'modelStatus':row['status'],'modelReason':row['reason'],
            'evidenceState':evidence_state(e,row,cutoff,p),'alternatePoolSeen':bool(p['alternatePools']),
            'ageMs':cutoff-e['at'],'fiveMinuteCheckpointRecorded':any(c.get('horizon')=='5m' for c in e.get('checkpoints',[]))})
        r=adjusted(row,100)
        if r['status']=='observed-model' and r['netReturnPct']<=-50:losses.append(loss_case(e,r))
    groups={};coverage_groups={}
    for cohort in sorted({e['cohort'] for e in entries}):
        for policy in report['evaluation']['policies']:
            key=cohort+'/'+policy['id']
            cr=[r for r in coverage if r['cohort']==cohort and r['policy']==policy['id']]
            coverage_groups[key]=dict(collections.Counter(r['evidenceState'] for r in cr))
        for period in ('exploratory','prospective'):
            es=[e for e in entries if e['cohort']==cohort and ((registered is not None and e['at']>=registered)==(period=='prospective'))]
            for rule in RULES:
                buckets={b:{e['id'] for e in es if rule_state(e,rule['id'])==b} for b in ('selected','excluded','unknown')}
                for bucket,ids in buckets.items():
                    for delay,bps in SCENARIOS:
                        for policy in report['evaluation']['policies']:
                            rr=[adjusted(r,bps) for r in rows if r['entryId'] in ids and r['delayMs']==delay and r['policy']==policy['id']]
                            groups[f'{period}/{cohort}/{rule["id"]}/{bucket}/{policy["id"]}/delay{delay}/cost{bps}']=summary(rr)
    return {'version':VERSION,'codeSha256':hashlib.sha256(__import__('pathlib').Path(__file__).read_bytes()).hexdigest(),
        'registration':reg,'rules':RULES,'rulesSha256':RULES_HASH,
        'poolEvidence':pools,'evidenceCoverage':coverage_groups,'scenarioEvidence':coverage,
        'severeLossCases':losses,'shadowGroups':groups,
        'featureAvailability':{c:{k:sum(e.get('entryFeatures',{}).get(k) is not None for e in entries if e['cohort']==c)
            for k in ('liquidityUsd','organicScore','top10Pct','security','return30sPct','return60sPct')}
            for c in sorted({e['cohort'] for e in entries})},
        'decision':'research-only; no automatic approval for real-money use',
        'notes':['Model statuses are unchanged. Awaiting-checkpoint-evidence is a provisional explanation, not an observed return.',
            'Six minutes is an archive-maturity allowance, not a trading delay or a guarantee of future data.',
            'Alternate pool presence is not proof that migration caused missing original-pool evidence.',
            'Shadow comparisons filter existing entry opportunities; they do not simulate waiting to enter later.',
            'Entry features absent from old exports remain unknown; future snapshots never fill entry-time features.',
            'Selected, excluded and unknown outcomes all remain visible; rejected winners are not hidden.',
            'Prospective means after host registration, not statistical independence. Rolling reports overlap; deduplicate entryId.',
            'Pool age and security freshness may be unavailable in stored entry records. No safety inference from missing fields.']}
