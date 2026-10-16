#!/usr/bin/env python3
"""Read original local exports, rebuild validated evidence and audit a fixed protocol."""
import argparse, collections, datetime as dt, gzip, hashlib, json, math, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research-dataset'))
from build import build,read,MAX_TOTAL_BYTES
from history import load_capture
from report import publish
PROTOCOL=json.loads(Path(__file__).with_name('protocol.json').read_text())
SCHEMAS={'baseline':'entry-features-1','early-activity':'entry-features-1','fast30-shadow':'fast-entry-features-1'}
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def eligibility(r):
 if r['samplingPolicy']!=PROTOCOL['samplingPolicy']:return 'different-sampling-policy'
 if not r['entrySchemaVerified'] or r['featureCaptureVersion']!=SCHEMAS.get(r['cohort']):return 'unverified-entry-schema'
 c=r['supplementalEntryContext'];m=c.get('metadataProvenance') or {}
 if c.get('state')!='recorded' or c.get('version')!=PROTOCOL['entryContextVersion']:return 'missing-or-invalid-entry-context'
 if m.get('version')!=PROTOCOL['metadataVersion']:return 'metadata-version-unrecorded'
 if any(m.get('fields',{}).get(f,{}).get('state') not in ('recorded','not-recorded') for f in ('organicScore','holderCount')):return 'invalid-metadata-provenance'
 return 'compatible'
def features(r):
 if eligibility(r)!='compatible':raise ValueError('Incompatible context')
 c=r['supplementalEntryContext'];p=c['predictors'];m=c['metadataProvenance']['fields'];legacy=r['predictors']
 out={k:p.get(k) for k in ('liquidityUsd','organicScore','holderCount','top10Pct','averageReportedTradeUsd')}
 out.update({k:legacy.get(k) for k in ('return30sPct','lastIntervalReturnPct')})
 out.update(marketAgeMs=p.get('marketObservedAtAgeMs'),securityAgeMs=p.get('securityCheckedAtAgeMs'),organicAgeMs=m['organicScore'].get('ageMs'),holderAgeMs=m['holderCount'].get('ageMs'))
 for k in ('mintAuthorityActive','freezeAuthorityActive'):out[k]=int(p[k]) if type(p.get(k)) is bool else None
 for k,v in [('qualificationRetain','retain'),('qualificationDefer','defer')]:out[k]=int(r['disposition']==v) if r['qualificationVersion']=='qualification-1' and r['disposition'] in ('retain','defer') else None
 if set(out)!=set(PROTOCOL['features']):raise ValueError('Feature protocol mismatch')
 if any(v is not None and (type(v) not in (int,float) or not math.isfinite(v)) for v in out.values()):raise ValueError('Invalid feature')
 return out
def labels(r,h=30000):
 state=r['exitAvailability'][str(h)];t=r['targets'][str(h)]
 if state=='on-time-validated-quote':
  if t['state']!='validated-sell-quote' or t['onTime'] is not True or type(t['returnPct']) not in (int,float) or not math.isfinite(t['returnPct']):raise ValueError('Inconsistent target')
  return {'positiveReturnedQuote':int(t['returnPct']>0),'exitQuoteAvailable':1}
 return {'positiveReturnedQuote':None,'exitQuoteAvailable':0 if state=='provider-reported-quote-failure' else None}
def assess(data,registration=None):
 rows=data['rows'];cohorts=[]
 for cohort in PROTOCOL['cohorts']:
  rr=[r for r in rows if r['cohort']==cohort];eligible=[r for r in rr if eligibility(r)=='compatible'];admitted=[r for r in eligible if r['decision']=='admitted']
  target={}
  for name in PROTOCOL['targets']:
   labelled=[(r,labels(r)[name]) for r in admitted if labels(r)[name] is not None];counts=collections.Counter(y for r,y in labelled);days={r['utcDay'] for r,y in labelled};reasons=[]
   if len(labelled)<PROTOCOL['minimumTrainingRowsPerTargetCohort']:reasons.append('too-few-labelled-watches')
   if min(counts.get(0,0),counts.get(1,0))<PROTOCOL['minimumTrainingPerClass']:reasons.append('too-few-examples-in-one-or-both-classes')
   if len(days)<PROTOCOL['minimumTrainingUtcDays']:reasons.append('too-few-distinct-utc-days')
   target[name]={'labelled':len(labelled),'unknown':len(admitted)-len(labelled),'classes':dict(counts),'utcDays':len(days),'fitGuardsPassed':not reasons,'blockingReasons':reasons}
  cohorts.append({'cohort':cohort,'signals':len(rr),'compatibleSignals':len(eligible),'compatibleAdmitted':len(admitted),
   'excluded':dict(collections.Counter(eligibility(r) for r in rr if eligibility(r)!='compatible')),
   'metadataStates':{f:dict(collections.Counter(r['supplementalEntryContext']['metadataProvenance']['fields'][f]['state'] for r in eligible)) for f in ('organicScore','holderCount')},
   'featurePresent':{f:sum(features(r)[f] is not None for r in admitted) for f in PROTOCOL['features']},
   'exitStates':{str(h):dict(collections.Counter(r['exitAvailability'][str(h)] for r in admitted)) for h in (30000,120000)},'targets':target})
 if registration is not None:
  if registration.get('format')!='forward-protocol-registration-1' or registration.get('protocolSha256')!=digest(PROTOCOL) or type(registration.get('registeredAt')) is not int or registration['registeredAt']<=0:raise ValueError('Registration mismatch')
 return {'format':'forward-readiness-1','capturedAt':data['capturedAt'],'sourceIdentity':data['sourceIdentity'],
  'protocol':PROTOCOL,'protocolSha256':digest(PROTOCOL),'registration':registration,'cohorts':cohorts,
  'allAdmitted':data['summary']['admitted'],'modelTrained':False,'liveUseAllowed':False,
  'evidencePeriod':'development-and-collection; no frozen model or forward performance result',
  'limitations':['Protocol registration is local and does not prove an untouched holdout. Preserve the reviewed Git commit.',
   'This command checks data and labels only. It does not fit, select, freeze, activate or evaluate a model.',
   'Minimum counts are fit guards, not statistical sufficiency. Collection alone need not produce enough failure labels.',
   'Do not broaden the failure definition, change thresholds or combine cohorts merely to pass a guard.',
   'Receipt ages are not provider measurement ages. Missing values remain missing.',
   'Quotes are not fills or net profit. Skipped signals are not labelled or assigned returns.']}
def load_sources(paths=None,history_dir=None):
 if paths:
  if len(paths)>16:raise ValueError('At most 16 original exports')
  inputs=[];total=0
  for path in paths:
   item=read(path);total+=item[1]['bytes']
   if total>MAX_TOTAL_BYTES:raise ValueError('Combined input cap exceeded')
   inputs.append(item)
  reports=[x for x,_ in inputs];provenance=[m for _,m in inputs]
 else:reports,provenance,_=load_capture(history_dir)
 return build(reports),provenance

def main():
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
 reg=sub.add_parser('register');reg.add_argument('--output',type=Path,required=True)
 a=sub.add_parser('audit');g=a.add_mutually_exclusive_group(required=True);g.add_argument('--source',type=Path,action='append');g.add_argument('--history-dir',type=Path);a.add_argument('--registration',type=Path);a.add_argument('--output',type=Path,required=True)
 args=p.parse_args()
 if args.command=='register':
  registration={'format':'forward-protocol-registration-1','protocolSha256':digest(PROTOCOL),'registeredAt':int(dt.datetime.now(dt.timezone.utc).timestamp()*1000),'modelFrozen':False,'liveUseAllowed':False}
  publish(args.output,registration);print('Protocol registered; no model frozen:',args.output);return
 data,provenance=load_sources(args.source,args.history_dir);registration=None
 if args.registration:
  if args.registration.stat().st_size>16384:raise ValueError('Registration size cap')
  with gzip.open(args.registration,'rb') as f:raw=f.read(16385)
  if len(raw)>16384:raise ValueError('Registration decoded size cap')
  registration=json.loads(raw)
 result=assess(data,registration);result['inputs']=provenance;publish(args.output,result)
 for c in result['cohorts']:print(c['cohort'],'compatible watches:',c['compatibleAdmitted'],'targets:',json.dumps(c['targets']))
 print('Readiness audit only. No model trained. Report:',args.output.resolve())
if __name__=='__main__':
 try:main()
 except Exception as e:raise SystemExit('Forward study stopped: '+type(e).__name__+': '+str(e))
