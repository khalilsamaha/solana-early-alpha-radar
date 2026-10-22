"""Validate supplemental entry context; never replace the frozen legacy predictors."""
import math
VALUES = ('liquidityUsd','organicScore','top10Pct','marketCap','holderCount','buys5m','sells5m','volume5mUsd')
CLOCKS = ('marketObservedAt','securityCheckedAt','jupiterCheckedAt')
COUNTS = {'holderCount','buys5m','sells5m'}
def num(x): return type(x) in (int,float) and math.isfinite(x) and x >= 0
def integer(x): return num(x) and int(x)==x and x<=9007199254740991

def context(signal):
    raw=signal.get('entryContext')
    if raw is None or (isinstance(raw,dict) and raw.get('state')=='absent' and raw.get('data') is None):
        return {'state':'absent','version':None,'predictors':{}}
    invalid={'state':'invalid','version':None,'predictors':{}}
    if not isinstance(raw,dict) or raw.get('state')!='recorded' or not isinstance(raw.get('data'),dict): return invalid
    d=raw['data'];at=signal.get('signalAt')
    if (d.get('version')!='entry-context-1' or not integer(at) or at<=0 or d.get('signalAt')!=at
        or d.get('mint')!=signal.get('mint') or not signal.get('originalPool') or d.get('pairAddress')!=signal['originalPool']): return invalid
    values=d.get('values');clocks=d.get('clocks');authorities=d.get('authorities')
    if not all(isinstance(x,dict) for x in [values,clocks,authorities]): return invalid
    out={};states={};clock_states={}
    for k in VALUES:
        x=values.get(k)
        if not isinstance(x,dict): return invalid
        v=x.get('value');state=x.get('state')
        if state=='recorded':
            if not num(v) or (k in COUNTS and not integer(v)) or (k=='top10Pct' and v>100): return invalid
        elif state not in ('absent','invalid') or v is not None: return invalid
        out[k]=v;states[k]=state
    b,s,v=(out[k] for k in ('buys5m','sells5m','volume5mUsd'))
    n=b+s if b is not None and s is not None and integer(b+s) else None
    out['transactions5m']=n
    out['averageReportedTradeUsd']=v/n if n and v is not None and math.isfinite(v/n) else None
    for k in CLOCKS:
        x=clocks.get(k)
        if not isinstance(x,dict): return invalid
        t,age,ttl,state=(x.get(f) for f in ('at','ageMs','ttlMs','state'))
        if ttl is not None and (not integer(ttl) or ttl<=0): return invalid
        if t is None:
            if age is not None or state not in ('absent','invalid'): return invalid
        else:
            if not integer(t) or t<=0 or t>at or not num(age) or age!=at-t: return invalid
            expected='age-only' if ttl is None else 'stale' if age>ttl else 'within-ttl'
            if state!=expected: return invalid
        out[k+'AgeMs']=age;clock_states[k]=state
    for k in ('mintAuthority','freezeAuthority'):
        if k not in authorities or (authorities[k] is not None and type(authorities[k]) is not bool): return invalid
        out[k+'Active']=authorities[k]
    return {'state':'recorded','version':'entry-context-1','predictors':out,'valueStates':states,'clockStates':clock_states,
            **({'metadataProvenance':metadata(d['metadataProvenance'],out,at)} if 'metadataProvenance' in d else {}),
            'basis':'Supplemental entry-time context only; stale values remain labelled; no safety verdict or model activation.'}


def metadata(raw,values,at):
    if raw is None:return None
    fields={};sources={'jupiter:recent','jupiter:top-organic','jupiter:search'}
    for key in ('organicScore','holderCount'):
        item=raw.get('fields',{}).get(key) if isinstance(raw,dict) and isinstance(raw.get('fields'),dict) else None
        out={'state':'invalid','value':None,'source':None,'receivedAt':None,'appliedAt':None,'ageMs':None}
        if isinstance(raw,dict) and raw.get('version')=='metadata-provenance-1' and isinstance(item,dict):
            value,received,applied,age=(item.get(x) for x in ('value','receivedAt','appliedAt','ageMs'))
            if item.get('state') in ('not-recorded','invalid') and all(item.get(x) is None for x in ('value','source','receivedAt','appliedAt','ageMs')):
                out['state']=item['state']
            elif (item.get('state')=='recorded' and num(value) and (key!='holderCount' or integer(value))
                  and value==values.get(key) and isinstance(item.get('source'),str) and item['source'] in sources and integer(received) and integer(applied)
                  and 0<received<=applied<=at and num(age) and age==at-received):
                out={'state':'recorded','value':value,'source':item['source'],'receivedAt':received,'appliedAt':applied,'ageMs':age}
        fields[key]=out
    return {'version':'metadata-provenance-1' if isinstance(raw,dict) and raw.get('version')=='metadata-provenance-1' else None,'fields':fields}
