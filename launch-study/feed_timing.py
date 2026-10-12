"""Project bounded transport evidence. HTTP dates/Age are not price timestamps."""
import math
from collections import Counter
VERSION='feed-provenance-1'
NUMBERS=('priceUsd','queuedAt','requestStartedAt','headersAt','bodyAt','appliedAt','queueMs','headersMs','bodyMs','applyDelayMs','httpAgeSeconds','httpDateAt','previousBodyAt','repeatedPriceCount','priceUnchangedSince','repeatedValuesCount','valuesUnchangedSince')
ENUMS={'provider':{'dexscreener'},'endpoint':{'pairs-batch','tokens-batch','token-pairs'},
 'cfCacheStatus':{'HIT','MISS','DYNAMIC','BYPASS','EXPIRED','STALE','UPDATING','REVALIDATED'},
 'comparison':{'same-pool-within-45s','new-or-gapped'}}
def numeric(x):return type(x) in (int,float) and math.isfinite(x) and 0<=x<=2**53-1

def project(value):
 if not isinstance(value,dict):return None
 if value.get('version')!=VERSION:return {'state':'unsupported-version'}
 out={'version':VERSION,'providerPriceAt':None}
 for key in NUMBERS:out[key]=value.get(key) if numeric(value.get(key)) else None
 for key,choices in ENUMS.items():out[key]=value.get(key) if isinstance(value.get(key),str) and value[key] in choices else None
 out['clocksOrdered']=value.get('clocksOrdered') is True
 out['httpStatus']=value.get('httpStatus') if type(value.get('httpStatus')) is int and 100<=value['httpStatus']<=599 else None
 pair=value.get('pairAddress');out['pairAddress']=pair if isinstance(pair,str) and 1<=len(pair)<=128 and pair.isalnum() else None
 return out

def state(feed,row,kind):
 if not feed:return 'not-recorded'
 if feed.get('version')!=VERSION:return 'unsupported-version'
 pool=row.get('pairAddress') or row.get('candidate',{}).get('pairAddress') or row.get('entryPool')
 price=row.get('priceUsd',row.get('candidate',{}).get('priceUsd'))
 if not isinstance(pool,str) or not pool or not numeric(price) or price<=0 or feed.get('pairAddress')!=pool or feed.get('priceUsd')!=price:return 'binding-mismatch'
 clocks=[feed.get(k) for k in ('queuedAt','requestStartedAt','headersAt','bodyAt','appliedAt')]
 if not feed.get('clocksOrdered') or not all(numeric(x) for x in clocks) or clocks!=sorted(clocks):return 'invalid-clock-order'
 if feed.get('provider')!='dexscreener' or feed.get('endpoint') not in ENUMS['endpoint'] or feed.get('httpStatus')!=200:return 'invalid-transport'
 for key,left,right in [('queueMs',0,1),('headersMs',1,2),('bodyMs',2,3),('applyDelayMs',3,4)]:
  if feed.get(key)!=clocks[right]-clocks[left]:return 'duration-mismatch'
 at=row.get('at');sample=row.get('sampleAt')
 if not numeric(at) or clocks[-1]>at or (kind=='outcomes' and (not numeric(sample) or clocks[3]>sample or sample>at)):return 'clock-after-event'
 return 'recorded-local-timing'

def distribution(values):
 vals=sorted(v for v in values if numeric(v))
 return {'count':len(vals),'median':None if not vals else (vals[(len(vals)-1)//2]+vals[len(vals)//2])/2,
  'p95':vals[max(0,math.ceil(len(vals)*.95)-1)] if vals else None,'max':max(vals) if vals else None}

def summarize(capture):
 groups=[]
 for kind in ('entries','outcomes'):
  rows=[r.get('data',{}) for r in capture.get(kind,[])];states=Counter();valid=[]
  for row in rows:
   feed=project(row.get('feedEvidence'));s=state(feed,row,kind);states[s]+=1
   if s=='recorded-local-timing':valid.append(feed)
  groups.append({'kind':kind,'records':len(rows),'states':dict(states),
   'endpoints':dict(Counter(v['endpoint'] for v in valid)),
   'distributions':{k:distribution([v.get(k) for v in valid]) for k in ('queueMs','headersMs','bodyMs','applyDelayMs','httpAgeSeconds','repeatedPriceCount','repeatedValuesCount')},
   'recordsWithRepeatedPrice':sum((v.get('repeatedPriceCount') or 0)>0 for v in valid)})
 return {'version':'feed-timing-report-1','groups':groups,'limitations':[
  'HTTP Age and Date describe responses, not the provider price timestamp; upstream price freshness remains unknown.',
  'Repeated values can describe a quiet market, caching or aggregation; repetition alone is not proof of stale prices.',
  'Records share requests and tokens; summary counts are not independent HTTP requests.',
  'Only new entries and observed checkpoints carry evidence; historical records are not backfilled.']}
