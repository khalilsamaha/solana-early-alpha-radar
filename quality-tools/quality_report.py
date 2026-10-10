#!/usr/bin/env python3
"""Read-only shadow report and offline fixed-quantity quote movements."""
import argparse,collections,datetime,gzip,json,math,os,signal,sqlite3,statistics,subprocess,time
from pathlib import Path
VERSION='research-quality-report-3'
from timing_analysis import analyze_timing
from joined_analysis import join_quotes
from entry_shadows import entry_shadows, missing_diagnostics
def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def load(p):
 with (gzip.open(p,'rb') if str(p).endswith('.gz') else open(p,'rb')) as f:raw=f.read(48*1024*1024+1)
 if len(raw)>48*1024*1024:raise ValueError('Input size cap reached')
 return json.loads(raw)
def live_database(project):
 def cmd(args):return subprocess.run(args,cwd=project,check=True,capture_output=True,text=True,timeout=10).stdout.strip()
 cid=cmd(['docker','compose','ps','-q','radar'])
 if not cid or '\n' in cid:raise ValueError('Expected one running radar container')
 info=json.loads(cmd(['docker','inspect',cid]))[0];mounts=[m for m in info.get('Mounts',[]) if m.get('Destination')=='/app/data' and m.get('Type') in ('bind','volume')]
 if not info.get('State',{}).get('Running') or len(mounts)!=1:raise ValueError('Running data mount unavailable')
 return Path(mounts[0]['Source']).resolve(strict=True)/'radar.sqlite'
def capture(path,hours=24,budget=10):
 path=Path(path).resolve(strict=True);identity=path.stat();start=time.monotonic();deadline=start+budget;wal=Path(str(path)+'-wal');size=wal.stat().st_size if wal.exists() else 0
 def guard():
  if time.monotonic()>deadline:raise TimeoutError('Read budget exceeded')
  if wal.exists() and wal.stat().st_size-size>64*1024*1024:raise RuntimeError('WAL growth limit reached')
 def expired(*_):raise TimeoutError('Read deadline exceeded')
 old=signal.getsignal(signal.SIGALRM);signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,budget+1)
 db=None;result={};total_bytes=0;now=int(time.time()*1000)
 try:
  db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1);db.execute('PRAGMA query_only=ON');db.execute('PRAGMA cache_size=-4096');db.execute('PRAGMA mmap_size=0')
  db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000);db.execute('BEGIN')
  reg=db.execute("SELECT data FROM kv WHERE key='fast-shadow-registration'").fetchone()
  result['registration']=json.loads(reg[0]) if reg else None
  followup=db.execute("SELECT data FROM kv WHERE key='fast-followup-registration'").fetchone()
  result['followupRegistration']=json.loads(followup[0]) if followup else None
  evidence=db.execute("SELECT data FROM kv WHERE key='fast-evidence-registration'").fetchone()
  result['evidenceRegistration']=json.loads(evidence[0]) if evidence else None
  for kind,cap in [('fast-shadow-entries',3000),('fast-shadow-outcomes',12000),('fast-shadow-links',6000)]:
   result[kind]=[]
   for raw,size_bytes in db.execute('SELECT CASE WHEN length(CAST(data AS BLOB))<=262144 THEN data END,length(CAST(data AS BLOB)) FROM events INDEXED BY events_at WHERE kind=? AND at>=? AND at<=? ORDER BY at LIMIT ?',(kind,now-hours*3600000,now,cap+1)):
    guard();total_bytes+=size_bytes
    if total_bytes>48*1024*1024:raise RuntimeError('Aggregate read size limit reached')
    if len(result[kind])>=cap or size_bytes>262144:raise RuntimeError('Event cap reached; narrow hours')
    result[kind].append(json.loads(raw))
  guard()
 finally:
  if db:db.close()
  signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
 current=path.stat()
 if (current.st_dev,current.st_ino)!=(identity.st_dev,identity.st_ino):raise RuntimeError('Source replaced during capture')
 result.update(sourceIdentity=f'{identity.st_dev}:{identity.st_ino}',cutoffAt=now,windowStartAt=now-hours*3600000,readSeconds=round(time.monotonic()-start,3))
 return result

def shadow_summary(data):
 entries=data['fast-shadow-entries'];outcomes={};links=data['fast-shadow-links'];now=data['cutoffAt']
 for o in data['fast-shadow-outcomes']:
  key=(o['entryId'],o['horizon'])
  if key in outcomes:raise ValueError('Duplicate shadow outcome')
  outcomes[key]=o
 horizons={}
 for horizon,ms in [('30s',30000),('60s',60000),('120s',120000),('300s',300000)]:
  counts=collections.Counter();values=[]
  for e in entries:
   o=outcomes.get((e['id'],horizon))
   state='pending' if not o and now<=e['at']+ms+30000 else 'overdue' if not o else 'missing' if o.get('status')!='observed' else 'gapped' if o.get('coverage')!='sampled' else 'invalid' if not finite(o.get('returnPct')) else 'observed'
   counts[state]+=1
   if state=='observed':values.append(o['returnPct'])
  horizons[horizon]={'states':dict(counts),'meanGrossPriceChangePct':statistics.mean(values) if values else None,'medianGrossPriceChangePct':statistics.median(values) if values else None}
 entry_ids={e['id'] for e in entries};groups={}
 for cohort in ['baseline','early-activity']:
  rows=[r for r in links if r['entryId'] in entry_ids and r['cohort']==cohort]
  groups[cohort]={'linkedEntries':len(rows),'medianLeadMs':statistics.median(r['leadMs'] for r in rows) if rows else None}
 return {'entries':len(entries),'horizons':horizons,'laterEntryLinks':groups,'basis':'sampled original-pool price changes, no execution or cost model; unlinked is not a failure'}

def quote_movements(report):
 if report.get('format')!='quote-observer-report-0.2.0':raise ValueError('Unsupported quote report')
 probes=report.get('probes',[])
 if len(probes)>1000:raise ValueError('Use a quote export with at most 1000 probes')
 groups=collections.defaultdict(list);cases=[];seen=set()
 for p in probes:
  s=p['signal'];key=(report.get('sourceIdentity'),s['seq'])
  if key in seen:raise ValueError('Duplicate probe')
  seen.add(key);obs=p.get('observations',[])
  if len(obs)>5:raise ValueError('Too many observations')
  buys=[o for o in obs if o.get('leg')=='buy' and o.get('status')=='quoted'];buy=buys[0] if len(buys)==1 else None
  sells={}
  for o in obs:
   if o.get('leg')!='sell':continue
   target=o.get('targetOffsetMs')
   if target in sells:raise ValueError('Duplicate sell offset')
   sells[target]=o
  intervals=[]
  for a,b in [(0,30000),(30000,60000),(60000,120000)]:
   x,y=sells.get(a),sells.get(b);item={'fromTargetMs':a,'toTargetMs':b,'state':'unavailable','quotedProceedsChangePct':None}
   if not x or not y:item['reason']='one or both sell observations not recorded'
   elif x.get('status')!='quoted' or y.get('status')!='quoted':item['reason']='one or both sell quotes failed'
   else:
    try:
     assert buy and x['inputMint']==y['inputMint']==s['mint'] and x['outputMint']==y['outputMint']==p['baseMint']
     assert x['inAmount']==y['inAmount']==buy['outAmount']
     n,d=int(y['outAmount']),int(x['outAmount']);assert n>0 and d>0
     assert x['startedAt']<y['startedAt'] and x['receivedAt']>=x['startedAt'] and y['receivedAt']>=y['startedAt']
     item.update(state='observed-quote-movement',quotedProceedsChangePct=(n-d)/d*100,fromRequestAt=x['startedAt'],toRequestAt=y['startedAt'],
       elapsedRequestMs=y['startedAt']-x['startedAt'],fromSignalMs=x['startedAt']-s['signalAt'],toSignalMs=y['startedAt']-s['signalAt'],
       bothIncludeOriginalPool=x.get('originalPoolInRoute') is True and y.get('originalPoolInRoute') is True)
    except (KeyError,ValueError,TypeError,AssertionError):item['reason']='quantity, mint, amount or clock validation failed'
   intervals.append(item)
   group=f"{p.get('samplingPolicy','legacy')}/{s['cohort']}/{s.get('featureCapture',{}).get('version','legacy')}/{a}-{b}"
   groups[group].append(item)
  cases.append({'seq':s['seq'],'entryId':s['entryId'],'cohort':s['cohort'],'symbol':s.get('symbol'),'intervals':intervals})
 summary={}
 for k,rows in groups.items():
  vals=[r['quotedProceedsChangePct'] for r in rows if r['state']=='observed-quote-movement']
  summary[k]={'admitted':len(rows),'observed':len(vals),'unavailable':len(rows)-len(vals),'meanPct':statistics.mean(vals) if vals else None,'medianPct':statistics.median(vals) if vals else None}
 return {'groups':summary,'cases':cases,'note':'Same hypothetical token quantity, quote proceeds between actual requests. Quotes are not fills or exit recommendations; failed/missing intervals excluded explicitly. Offset 0 is delayed by request spacing.'}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',type=Path);p.add_argument('--shadow-report',type=Path);p.add_argument('--quotes',type=Path);p.add_argument('--hours',type=int,choices=range(1,25),default=24);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.project and a.shadow_report:p.error('Project and shadow-report are mutually exclusive')
 if not a.project and not a.shadow_report and not a.quotes:p.error('Supply project, shadow-report and/or quotes')
 report={'format':VERSION,'capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 data=None;quotes=load(a.quotes) if a.quotes else None
 if a.project:data=capture(live_database(a.project),a.hours)
 elif a.shadow_report:data=load(a.shadow_report)['shadowCapture']
 if data is not None:
  report['shadowCapture']=data;report['shadowSummary']=shadow_summary(data);report['evidenceAnalysis']=analyze_timing(data)
  report['missingDiagnostics']=missing_diagnostics(data)
  if quotes is not None:report['joinedEvidence']=join_quotes(data,quotes)
  report['entryShadows']=entry_shadows(data,report.get('joinedEvidence'))
 if quotes is not None:report['quoteMovements']=quote_movements(quotes)
 raw=json.dumps(report,allow_nan=False,separators=(',',':')).encode()
 if len(raw)>48*1024*1024:raise ValueError('Output too large')
 compressed=gzip.compress(raw,mtime=0);fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 try:
  with os.fdopen(fd,'wb') as f:
   f.write(compressed);f.flush();os.fsync(f.fileno())
   if os.geteuid()==0 and os.environ.get('SUDO_UID'):os.fchown(f.fileno(),int(os.environ['SUDO_UID']),int(os.environ['SUDO_GID']))
 except BaseException:a.output.unlink(missing_ok=True);raise
 print(json.dumps(report['shadowSummary'] if 'shadowSummary' in report else {'quoteMovementGroups':len(report['quoteMovements']['groups'])},indent=2));print('Upload: '+str(a.output.resolve()))
 if 'joinedEvidence' in report:print('Joined source identity: '+report['joinedEvidence']['sourceIdentityState'])
 if 'entryShadows' in report:print('Entry shadow periods: '+json.dumps(dict(collections.Counter(e['period'] for e in report['entryShadows']['entries']))))
if __name__=='__main__':
 try:main()
 except Exception as e:raise SystemExit('Quality report stopped: '+type(e).__name__+'; no complete report published.')
