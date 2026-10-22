#!/usr/bin/env python3
"""Freeze small offline models, then evaluate immutable JSON weights on later evidence."""
import argparse,collections,datetime as dt,gzip,json,math,sys,time,warnings
from pathlib import Path
import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import roc_auc_score
from audit import PROTOCOL,digest,eligibility,features,labels,load_sources,publish
VERSION='forward-model-1'
LEGACY={'baseline':['liquidityUsd','organicScore','top10Pct','return30sPct'],
 'early-activity':['return30sPct','return60sPct','lastIntervalReturnPct','averageReportedTradeUsd'],
 'fast30-shadow':['return30sPct','lastIntervalReturnPct','liquidityUsd']}
INDICATORS={'mintAuthorityActive','freezeAuthorityActive','qualificationRetain','qualificationDefer'}
def matrix(rows,cohort,variant):
 names=PROTOCOL['features'] if variant=='context' else LEGACY[cohort];out=[]
 for r in rows:
  f=features(r) if variant=='context' else r['predictors'];values=[]
  for k in names:
   v=f.get(k)
   if v is None:values.append(float('nan'))
   elif type(v) not in (int,float) or not math.isfinite(v):raise ValueError('Invalid feature')
   else:values.append(v if k in INDICATORS else math.copysign(math.log1p(abs(v)),v))
  out.append(values)
 return np.asarray(out,dtype=float).reshape(len(rows),len(names))
def fit(rows,y,cohort,variant):
 x=matrix(rows,cohort,variant);missing=np.isnan(x);med=np.array([np.median(x[~missing[:,i],i]) if (~missing[:,i]).any() else 0 for i in range(x.shape[1])]);z=np.concatenate([np.where(missing,med,x),missing.astype(float)],axis=1)
 center=z.mean(axis=0);scale=z.std(axis=0);scale[scale==0]=1
 cfg=PROTOCOL['classifier'];m=LogisticRegression(C=cfg['C'],solver=cfg['solver'],max_iter=cfg['maxIterations'],random_state=0,class_weight=None)
 with warnings.catch_warnings():warnings.simplefilter('error',ConvergenceWarning);m.fit((z-center)/scale,y)
 weights={'medians':med.tolist(),'center':center.tolist(),'scale':scale.tolist(),'coefficients':m.coef_[0].tolist(),'intercept':float(m.intercept_[0])}
 predicted=predict(rows,cohort,variant,weights)
 if not np.allclose(predicted,m.predict_proba((z-center)/scale)[:,1],rtol=0,atol=1e-12):raise ValueError('Serialized prediction mismatch')
 return weights
def predict(rows,cohort,variant,w):
 n=len(PROTOCOL['features'] if variant=='context' else LEGACY[cohort])
 for key,size in [('medians',n),('center',n*2),('scale',n*2),('coefficients',n*2)]:
  if not isinstance(w.get(key),list) or len(w[key])!=size or any(type(v) not in (int,float) or not math.isfinite(v) for v in w[key]):raise ValueError('Invalid model weights')
 if any(v<=0 for v in w['scale']) or type(w.get('intercept')) not in (int,float) or not math.isfinite(w['intercept']):raise ValueError('Invalid model scale or intercept')
 x=matrix(rows,cohort,variant);missing=np.isnan(x);z=np.concatenate([np.where(missing,w['medians'],x),missing.astype(float)],axis=1);logit=(z-w['center'])/w['scale']@np.array(w['coefficients'])+w['intercept']
 return 1/(1+np.exp(-np.clip(logit,-700,700)))
def freeze(data,registration,now=None):
 now=int(time.time()*1000) if now is None else now
 if registration.get('format')!='forward-protocol-registration-1' or registration.get('protocolSha256')!=digest(PROTOCOL) or type(registration.get('registeredAt')) is not int or not 0<registration['registeredAt']<=now:raise ValueError('Invalid protocol registration')
 if type(data['capturedAt']) is not int or data['capturedAt']>now:raise ValueError('Input cutoff is after freeze clock')
 cutoff=min(data['capturedAt'],now-PROTOCOL['holdout']['embargoMs']);rr=[r for r in data['rows'] if r['decision']=='admitted' and eligibility(r)=='compatible' and r['signalAt']<cutoff];groups=[]
 for c in PROTOCOL['cohorts']:
  for target in PROTOCOL['targets']:
   rows=[r for r in rr if r['cohort']==c and labels(r)[target] is not None and type(r['targets']['30000']['availableAt']) is int and r['targets']['30000']['availableAt']<=cutoff];y=[labels(r)[target] for r in rows];counts=collections.Counter(y);days={r['utcDay'] for r in rows};reasons=[]
   if len(rows)<PROTOCOL['minimumTrainingRowsPerTargetCohort']:reasons.append('training-count')
   if min(counts.get(0,0),counts.get(1,0))<PROTOCOL['minimumTrainingPerClass']:reasons.append('class-count')
   if len(days)<PROTOCOL['minimumTrainingUtcDays']:reasons.append('day-count')
   g={'cohort':c,'target':target,'trainingRows':len(rows),'classes':{str(k):v for k,v in counts.items()},'utcDays':len(days),'trainIdsSha256':digest([r['id'] for r in rows]),'blockingReasons':reasons,'models':None}
   if not reasons:g['models']={v:fit(rows,y,c,v) for v in ('legacy','context')};g['constantProbability']=float(np.mean(y))
   groups.append(g)
 result={'format':VERSION,'protocol':PROTOCOL,'protocolSha256':digest(PROTOCOL),'registration':registration,'frozenAt':now,'trainingCutoffAt':cutoff,'testNotBeforeAt':now+PROTOCOL['holdout']['embargoMs'],
  'sourceIdentity':data['sourceIdentity'],'seenTrainingMints':sorted({r['mint'] for r in rr}),'groups':groups,'modelFrozen':any(g['models'] for g in groups),'liveUseAllowed':False,'sklearnVersion':sklearn.__version__,
  'limitations':['Local freeze time is not independent proof of an untouched holdout; preserve this artifact and reviewed commit before gathering test outcomes.',
   'Weights are research JSON, not a live trading model. No pickle or executable model deserialization.',
   'Failed/missing labels remain unknown as specified. Quote availability excludes transport and late observations.',
   'No search or refit; blocked targets remain blocked rather than inventing labels.']}
 return result
def seal(artifact):return {**artifact,'artifactSha256':digest(artifact)}
def read_artifact(path):
 with gzip.open(path,'rb') as f:raw=f.read(8*1024*1024+1)
 if len(raw)>8*1024*1024:raise ValueError('Artifact cap')
 a=json.loads(raw);h=a.pop('artifactSha256',None)
 if h!=digest(a) or a.get('format')!=VERSION or a.get('protocol')!=PROTOCOL or a.get('protocolSha256')!=digest(PROTOCOL):raise ValueError('Artifact integrity or protocol mismatch')
 return a
def stats(rows,prob,target):
 pairs=[(r,float(p),labels(r)[target]) for r,p in zip(rows,prob) if labels(r)[target] is not None]
 y=np.array([v for r,p,v in pairs]);p=np.array([p for r,p,v in pairs]);clip=np.clip(p,1e-15,1-1e-15)
 return {'labelled':len(y),'unknown':len(rows)-len(y),'positiveLabels':int(y.sum()),'brier':float(np.mean((p-y)**2)) if len(y) else None,'logLoss':float(np.mean(-(y*np.log(clip)+(1-y)*np.log(1-clip)))) if len(y) else None,'rocAuc':float(roc_auc_score(y,p)) if len(set(y))==2 else None,
 'calibration':[{'low':lo,'high':hi,'n':sum(lo<=p<hi or hi==1 and p==1 for _,p,_ in pairs),'meanProbability':float(np.mean([p for _,p,_ in pairs if lo<=p<hi or hi==1 and p==1])) if any(lo<=p<hi or hi==1 and p==1 for _,p,_ in pairs) else None,'observedPositiveFraction':float(np.mean([y for _,p,y in pairs if lo<=p<hi or hi==1 and p==1])) if any(lo<=p<hi or hi==1 and p==1 for _,p,_ in pairs) else None} for lo,hi in [(0,.25),(.25,.5),(.5,.75),(.75,1)]]}
def outcomes(rows,h=30000):
 valid=[r for r in rows if r['exitAvailability'][str(h)]=='on-time-validated-quote'];v=[r['targets'][str(h)]['returnPct'] for r in valid]
 def avg(values):return float(np.mean(values)) if values else None
 by_mint={m:[r['targets'][str(h)]['returnPct'] for r in valid if r['mint']==m] for m in sorted({r['mint'] for r in valid})};by_day={d:[r['targets'][str(h)]['returnPct'] for r in valid if r['utcDay']==d] for d in sorted({r['utcDay'] for r in valid})}
 best_mint=max(by_mint,key=lambda k:sum(by_mint[k])) if by_mint else None;best_day=max(by_day,key=lambda k:sum(by_day[k])) if by_day else None
 return {'watches':len(rows),'states':dict(collections.Counter(r['exitAvailability'][str(h)] for r in rows)),'onTimeReturned':len(v),'meanQuotedPct':avg(v),'medianQuotedPct':float(np.median(v)) if v else None,'lossAtLeast50':sum(x<=-50 for x in v),
  'meanWithoutBestTokenPct':avg([r['targets'][str(h)]['returnPct'] for r in valid if r['mint']!=best_mint]),'meanWithoutBestDayPct':avg([r['targets'][str(h)]['returnPct'] for r in valid if r['utcDay']!=best_day]),
  'illustrativeCostStressMeanPct':{str(c):avg([((1+x/100)*(1-c/100)/(1+c/100)-1)*100 for x in v]) for c in PROTOCOL['costSensitivity']['eachSidePct']}}
def paired_interval(rows,rich,base,target):
 days=sorted({r['utcDay'] for r in rows if labels(r)[target] is not None})
 if len(days)<PROTOCOL['holdout']['minimumUtcDays']:return {'state':'insufficient-days','days':len(days)}
 sums=[];counts=[]
 for d in days:
  differences=[(float(a)-labels(r)[target])**2-(float(b)-labels(r)[target])**2 for r,a,b in zip(rows,rich,base) if r['utcDay']==d and labels(r)[target] is not None];sums.append(sum(differences));counts.append(len(differences))
 rng=np.random.default_rng(0);indices=rng.integers(0,len(days),size=(2000,len(days)));vals=np.array(sums)[indices].sum(axis=1)/np.array(counts)[indices].sum(axis=1)
 return {'state':'descriptive-day-block-bootstrap','days':len(days),'replicates':2000,'meanBrierDifference':sum(sums)/sum(counts),'interval95':np.quantile(vals,[.025,.975]).tolist(),'negativeFavorsContext':True}
def evaluate(data,artifact):
 if artifact['sourceIdentity']!=data['sourceIdentity'] or artifact['protocolSha256']!=digest(PROTOCOL):raise ValueError('Source or protocol mismatch')
 seen=set(artifact['seenTrainingMints']);groups=[]
 for g in artifact['groups']:
  c=g['cohort'];target=g['target'];excluded=collections.Counter();rows=[];test_mints=set()
  for r in sorted(data['rows'],key=lambda x:(x['signalAt'],x['seq'])):
   if r['cohort']!=c or r['decision']!='admitted':continue
   reason=eligibility(r)
   if reason!='compatible':excluded[reason]+=1
   elif r['signalAt']<artifact['testNotBeforeAt']:excluded['before-freeze-plus-embargo']+=1
   elif r['mint'] in seen:excluded['token-seen-in-training-period']+=1
   elif r['mint'] in test_mints:excluded['repeat-forward-token']+=1
   else:rows.append(r);test_mints.add(r['mint'])
  out={'cohort':c,'target':target,'excluded':dict(excluded),'forwardWatches':len(rows),'allForwardOutcomes':{str(h):outcomes(rows,h) for h in (30000,120000)}}
  if not g['models']:out['state']='model-not-frozen-insufficient-training';groups.append(out);continue
  pred={v:predict(rows,c,v,g['models'][v]) for v in ('legacy','context')};pred['constant']=np.full(len(rows),g['constantProbability'])
  valid=[r for r in rows if labels(r)[target] is not None];days={r['utcDay'] for r in valid}
  out['state']='forward-minimum-reached-not-promotion' if len(valid)>=PROTOCOL['holdout']['minimumValidLabelsPerTargetCohort'] and len(days)>=PROTOCOL['holdout']['minimumUtcDays'] else 'insufficient-forward-evidence'
  out['metrics']={v:stats(rows,p,target) for v,p in pred.items()};out['selectedOutcomes']={v:{str(h):outcomes([r for r,p in zip(rows,pp) if p>=.5],h) for h in (30000,120000)} for v,pp in pred.items()}
  out['contextBrierDifference']={v:paired_interval(rows,pred['context'],pred[v],target) for v in ('legacy','constant')}
  out['predictions']=[{'id':r['id'],'signalAt':r['signalAt'],'label':labels(r)[target],'exitState':r['exitAvailability']['30000'],'probabilities':{v:float(p[i]) for v,p in pred.items()}} for i,r in enumerate(rows)]
  groups.append(out)
 return {'format':'forward-comparison-1','artifactSha256':digest(artifact),'capturedAt':data['capturedAt'],'groups':groups,'liveUseAllowed':False,'modelRefitted':False,
  'limitations':['Same immutable weights used for all reports. Overlapping exports are not independent experiments; deduplicate before combining.',
   'Future rows sharing any admitted training-period token are excluded; losses and unknown outcomes remain visible for admitted forward watches.',
   'Uncertainty intervals are descriptive with few days, nonrandom sampling and repeated looks; minimum counts do not authorize promotion.',
   'Cost stress is illustrative on returned quotes only; failure-adjusted net profit and actual execution remain unmeasured.']}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['freeze','evaluate']);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--source',type=Path,action='append');g.add_argument('--history-dir',type=Path);p.add_argument('--registration',type=Path);p.add_argument('--artifact',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();data,inputs=load_sources(a.source,a.history_dir)
 if a.command=='freeze':
  if not a.registration or a.artifact:p.error('freeze requires --registration and no --artifact')
  with gzip.open(a.registration,'rb') as f:raw=f.read(16385)
  if len(raw)>16384:raise ValueError('Registration cap')
  result=freeze(data,json.loads(raw));result['inputs']=inputs;result=seal(result)
 else:
  if not a.artifact or a.registration:p.error('evaluate requires --artifact and no --registration')
  result=evaluate(data,read_artifact(a.artifact));result['inputs']=inputs
 publish(a.output,result)
 if a.command=='freeze':print('Offline freeze complete; modelFrozen=',result['modelFrozen'],'liveUseAllowed=False. Report:',a.output.resolve())
 else:print('Offline evaluation complete; modelRefitted=False; liveUseAllowed=False. Report:',a.output.resolve())
if __name__=='__main__':
 try:main()
 except Exception as e:raise SystemExit('Forward model stopped: '+type(e).__name__+': '+str(e))
