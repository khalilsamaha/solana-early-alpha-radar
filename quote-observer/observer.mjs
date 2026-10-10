// Separate, walletless signal observer. Scanner database is opened read-only.
import fs from 'node:fs';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {fileURLToPath} from 'node:url';
import {observe,requestQuote,address,USDC,pause} from './quote-check.mjs';
import {entryFeatures, FEATURE_CAPTURE, ACTIVITY_SHADOW} from './entry-features.mjs';
export const VERSION='quote-observer-0.6.0';
export const LIMITS={pollMs:2000,maxSignalAgeMs:15000,oneActive:true,admissionsPerHour:6,admissionsPer24h:144,requestsPerAdmission:5,spacingMs:10000,retentionDays:7};
export const SAMPLING={id:'three-cohort-budgets-v3',cohorts:['baseline','early-activity','fast30-shadow'],perCohortHour:2,perCohortDay:48,minimumCohortSpacingMs:1800000,borrowing:false};
export function samplingCapacity(s,now,recent=[]){
  const own=recent.filter(r=>r.cohort===s.cohort&&r.at>now-86400000);
  const latest=own.length?Math.max(...own.map(r=>r.at)):null;
  return {cohort:s.cohort,hourUsed:own.filter(r=>r.at>now-3600000).length,dayUsed:own.length,
    nextCohortAdmissionAt:latest===null?now:Math.max(now,latest+SAMPLING.minimumCohortSpacingMs)};
}
export function samplingDecision(s,now,recent=[]){
  const c=samplingCapacity(s,now,recent);
  if(c.hourUsed>=SAMPLING.perCohortHour)return 'cohort-hour-budget';
  if(c.dayUsed>=SAMPLING.perCohortDay)return 'cohort-day-budget';
  if(now<c.nextCohortAdmissionAt)return 'cohort-spacing';
  return 'admitted';
}
export function transientFailure(r){return ['timeout','network-or-json-error'].includes(r.status)||(r.status==='http-error'&&r.httpStatus>=500);}
const numeric=x=>typeof x==='number'&&Number.isFinite(x)?x:null;
const short=x=>typeof x==='string'?x.slice(0,96):null;
export function signalRecord(row){
  let r;try{r=JSON.parse(row.data);}catch{return {error:'invalid-event'};}
  if(!r||typeof r!=='object')return {error:'invalid-event'};
  let cohort;
  if(row.kind==='alerts'){
    if(r.engineVersion!=='0.2.9')return {error:'unsupported-version'};
    const parts=String(r.id).split(':');
    if(parts.length!==3||Number(parts[1])!==r.at)return {error:'later-alert'};
    cohort='baseline';
  }else if(row.kind==='fast-shadow-entries'){
    if(r.cohort!=='fast30-shadow'||r.version!=='fast30-shadow-1'||r.ruleId!=='fast30-shadow-1')return {error:'unsupported-version'};
    cohort='fast30-shadow';
  }else{
    if(r.cohort!=='early-activity')return {error:'other-cohort'};
    if(r.version!=='research-0.2.9')return {error:'unsupported-version'};
    cohort='early-activity';
  }
  const c=r.candidate||{},mint=r.mint||c.mint;
  if(!address(mint)||mint===USDC||!Number.isSafeInteger(r.at)||r.at<=0||r.at!==row.at)return {error:'invalid-event'};
  const q=r.qualification||{},m=q.metrics||{},inputs=r.evidence?.inputs||{};
  return {eventId:short(r.id),entryId:short(r.id),seq:row.seq,cohort,mint,signalAt:r.at,
    originalPool:address(c.pairAddress||r.pairAddress)?c.pairAddress||r.pairAddress:null,
    entryPriceUsd:numeric(c.priceUsd??r.priceUsd),symbol:short(c.symbol||r.symbol),
    ...entryFeatures(r),basis:'entry record only; no later enrichment'};
}
export function admission(s,{now,busy,blockedUntil=0,halted=false,recent=[],sameMint=false,nextRequestAt=0}){
  if(s.error)return s.error;
  if(s.signalAt>now)return 'future-timestamp';
  if(now-s.signalAt>LIMITS.maxSignalAgeMs)return 'stale-signal';
  if(halted)return 'provider-halted';
  if(now<blockedUntil)return 'provider-cooldown';
  if(sameMint)return 'mint-already-sampled-24h';
  if(busy)return 'observer-busy';
  if(recent.filter(t=>t>now-3600000).length>=6)return 'hour-budget';
  if(recent.filter(t=>t>now-86400000).length>=144)return 'day-budget';
  if(Math.max(now,nextRequestAt)-s.signalAt>15000)return 'spacing-would-expire-signal';
  return 'admitted';
}
export function openLedger(file){
  const db=new DatabaseSync(file);db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=1000;
    CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS signals(seq INTEGER PRIMARY KEY, at INTEGER, cohort TEXT, mint TEXT, decision TEXT NOT NULL, detected INTEGER NOT NULL, data TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS signals_at ON signals(detected);
    CREATE TABLE IF NOT EXISTS probes(seq INTEGER PRIMARY KEY, at INTEGER NOT NULL,mint TEXT NOT NULL,state TEXT NOT NULL,data TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS probes_at ON probes(at);
    CREATE TABLE IF NOT EXISTS incidents(at INTEGER,kind TEXT,detail TEXT);`);return db;
}
const get=(db,k,fallback=null)=>{const r=db.prepare('SELECT v FROM meta WHERE k=?').get(k);return r?JSON.parse(r.v):fallback;};
const put=(db,k,v)=>db.prepare('INSERT INTO meta VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v').run(k,JSON.stringify(v));
export function sourceRows(source,cursor){
  // Indexed, bounded statements finish before any network request. Never hold a read transaction during a watch.
  const rows=[];
  for(const kind of ['alerts','research-entries','fast-shadow-entries']){if(!Number.isSafeInteger(cursor[kind]))continue;rows.push(...source.prepare("SELECT seq,kind,at,CASE WHEN length(data)<=32768 THEN data ELSE '{}' END AS data FROM events INDEXED BY events_kind_seq WHERE kind=? AND seq>? ORDER BY seq LIMIT 200").all(kind,cursor[kind]));}
  return rows.sort((a,b)=>a.seq-b.seq);
}
export function recover(db,now){
  for(const row of db.prepare("SELECT * FROM probes WHERE state='running'").all()){
    const r=JSON.parse(row.data);r.state='interrupted-restart';r.finishedAt=now;
    r.incompleteReason='Observer restarted; historical quotes are never retried or reconstructed';
    db.prepare('UPDATE probes SET state=?,data=? WHERE seq=?').run(r.state,JSON.stringify(r),row.seq);
  }
}
export class Observer {
  constructor(source,ledger,{now=Date.now,quote=requestQuote,sleep=pause,log=console.log,signal}={}){Object.assign(this,{source,db:ledger,now,quote,sleep,log,signal});this.active=null;this.lastPrune=0;this.lastStatus=0;this.failures=0;}
  init(identity){
    const old=get(this.db,'sourceIdentity');if(old&&old!==identity)throw Error('Source database changed; preserve reports and review cursor before reinstalling');
    put(this.db,'sourceIdentity',identity);put(this.db,'limits',LIMITS);put(this.db,'version',VERSION);const n=this.now();
    if(get(this.db,'samplingRegistration')?.id!==SAMPLING.id){const prior=get(this.db,'samplingRegistration');if(prior)put(this.db,'previousSamplingRegistration',prior);const reg={...SAMPLING,registeredAt:n};put(this.db,'samplingRegistration',reg);this.db.prepare('INSERT INTO incidents VALUES(?,?,?)').run(n,'sampling-registration',JSON.stringify(reg));}
    if(!get(this.db,'featureCaptureRegistration'))put(this.db,'featureCaptureRegistration',{id:FEATURE_CAPTURE,registeredAt:n,shadow:ACTIVITY_SHADOW});
    if(!get(this.db,'cursor')){
      const max=this.source.prepare('SELECT coalesce(max(seq),0) AS n FROM events').get().n;
      put(this.db,'cursor',{'alerts':max,'research-entries':max,'fast-shadow-entries':max});put(this.db,'registeredAt',n);
      this.db.prepare('INSERT INTO incidents VALUES(?,?,?)').run(n,'registration','Start at current event tail; pre-existing signals not sampled');
    }
    const cursor=get(this.db,'cursor');
    if(!Number.isSafeInteger(cursor['fast-shadow-entries'])){
      cursor['fast-shadow-entries']=this.source.prepare('SELECT coalesce(max(seq),0) AS n FROM events').get().n;
      put(this.db,'cursor',cursor);put(this.db,'fastFeedRegistration',{at:n,startSeq:cursor['fast-shadow-entries']});
      this.db.prepare('INSERT INTO incidents VALUES(?,?,?)').run(n,'fast-feed-registration','New feed starts at tail; existing cursors and budgets preserved');
    }
    recover(this.db,n);
    this.db.prepare('INSERT INTO incidents VALUES(?,?,?)').run(n,'observer-start',JSON.stringify({previousPollAt:get(this.db,'lastPollAt'),note:'Events retained during downtime are classified by age; pruned events cannot be recovered'}));
    // Also respect spacing after a crash, even if the previous request was interrupted.
    put(this.db,'nextRequestAt',Math.max(get(this.db,'nextRequestAt',0),n+10000));
  }
  async runProbe(s){
    let failure;let networkRequests=0;
    const save=async r=>{
      r.requests=networkRequests;r.format=VERSION;r.mode='automatic-signal-watch';r.signal=s;r.sampling='Independent rolling cohort budgets; no borrowing; first fresh arrival after cohort spacing; not random';r.samplingPolicy=SAMPLING.id;
      r.limitations=r.limitations.filter(x=>!x.startsWith('No scanner signal'));
      r.limitations.push(...(r.limitations.includes('Signal-linked quote observations; not fills or paper-outcome replacements.')?[]:['Signal-linked quote observations; not fills or paper-outcome replacements.']));
      const buy=r.observations.find(o=>o.leg==='buy');r.signalToBuyRequestMs=buy?.startedAt?buy.startedAt-s.signalAt:null;
      r.signalToBuyResponseMs=buy?.receivedAt?buy.receivedAt-s.signalAt:null;
      for(const o of r.observations){if(o.startedAt)o.signalOffsetMs=o.startedAt-s.signalAt;
        o.tokenPools=(o.routePlan||[]).filter(p=>p.inputMint===s.mint||p.outputMint===s.mint).map(p=>p.pool);
        o.originalPoolInRoute=s.originalPool&&o.status==='quoted'?o.tokenPools.includes(s.originalPool):null;
        o.largeReportedImpact=typeof o.priceImpactPercentagePoints==='number'?Math.abs(o.priceImpactPercentagePoints)>=5:null;}
      this.db.prepare('INSERT INTO probes VALUES(?,?,?,?,?) ON CONFLICT(seq) DO UPDATE SET state=excluded.state,data=excluded.data').run(s.seq,s.detectedAt,s.mint,r.state,JSON.stringify(r));
    };
    const wrapped=async(a,b,amount,opts)=>{
      const due=get(this.db,'nextRequestAt',0);await this.sleep(Math.max(0,due-this.now()),this.signal);
      if(this.signal?.aborted)return {status:'interrupted',startedAt:this.now(),receivedAt:this.now(),latencyMs:0};
      if(a===USDC&&this.now()-s.signalAt>15000)return {status:'signal-expired-before-request',startedAt:this.now(),receivedAt:this.now(),latencyMs:0};
      put(this.db,'nextRequestAt',this.now()+10000);
      networkRequests++;const r=await this.quote(a,b,amount,opts);
      if(r.status==='rate-limited')put(this.db,'blockedUntil',this.now()+900000);
      if(['access-denied','unexpected-transaction-rejected'].includes(r.status))put(this.db,'halted',r.status);
      if(transientFailure(r)){this.failures++;if(this.failures>=3)put(this.db,'blockedUntil',this.now()+60000);}else this.failures=0;
      this.log(JSON.stringify({at:this.now(),seq:s.seq,leg:a===USDC?'buy':'sell',status:r.status,latencyMs:r.latencyMs}));return r;
    };
    try{await observe({mint:s.mint,watch:true,usdcAtomic:'10000000'},{quote:wrapped,now:this.now,sleep:this.sleep,save,signal:this.signal});}
    catch(e){failure=e;}
    this.active=null;if(failure){this.fatal=failure;}
  }
  tick(){
    if(this.fatal)throw this.fatal;
    const cursor=get(this.db,'cursor');
    const maxSeq=this.source.prepare('SELECT coalesce(max(seq),0) AS n FROM events').get().n;
    if(maxSeq<Math.max(...Object.values(cursor)))throw Error('Source sequence rewound; preserve reports and review cursor');
    const rows=sourceRows(this.source,cursor);
    for(const row of rows){
      const s=signalRecord(row),n=this.now();s.seq=row.seq;s.detectedAt=n;
      const recent=this.db.prepare('SELECT p.at,p.mint,s.cohort FROM probes p LEFT JOIN signals s ON s.seq=p.seq WHERE p.at>?').all(n-86400000);
      let reason=admission(s,{now:n,busy:!!this.active,halted:!!get(this.db,'halted'),blockedUntil:get(this.db,'blockedUntil',0),recent:recent.map(r=>r.at),sameMint:recent.some(r=>r.mint===s.mint),nextRequestAt:get(this.db,'nextRequestAt',0)});
      if(reason==='admitted')reason=samplingDecision(s,n,recent);
      s.samplingPolicy=SAMPLING.id;s.samplingCapacity=samplingCapacity(s,n,recent);
      this.db.exec('BEGIN IMMEDIATE');
      try{
        this.db.prepare('INSERT INTO signals VALUES(?,?,?,?,?,?,?)').run(row.seq,row.at,s.cohort||null,s.mint||null,reason,n,JSON.stringify(s));
        cursor[row.kind]=row.seq;put(this.db,'cursor',cursor);
        if(reason==='admitted'){this.db.prepare('INSERT INTO probes VALUES(?,?,?,?,?)').run(row.seq,n,s.mint,'running',JSON.stringify({state:'running',samplingPolicy:SAMPLING.id,signal:s,observations:[],startedAt:n}));}
        this.db.exec('COMMIT');
      }catch(e){this.db.exec('ROLLBACK');throw e;}
      if(reason==='admitted'){this.active=this.runProbe(s);}
    }
    if(this.now()-this.lastStatus>=10000){put(this.db,'lastPollAt',this.now());this.lastStatus=this.now();}
    if(this.now()-this.lastPrune>=3600000){
      const cutoff=this.now()-7*86400000;
      for(const table of ['signals','probes'])this.db.prepare(`DELETE FROM ${table} WHERE ${table==='signals'?'detected':'at'}<?`).run(cutoff);
      this.db.prepare('DELETE FROM incidents WHERE at<?').run(cutoff);this.lastPrune=this.now();
    }
  }
}
async function main(){
  const config=JSON.parse(fs.readFileSync('/etc/solana-radar-quotes.json','utf8'));
  const stat=fs.statSync(config.database);const identity=`${stat.dev}:${stat.ino}`;
  const source=new DatabaseSync(config.database,{readOnly:true});source.exec('PRAGMA query_only=ON; PRAGMA busy_timeout=200; PRAGMA cache_size=-2048; PRAGMA mmap_size=0');
  const file=path.join(config.reports,'observer.sqlite'),db=openLedger(file),controller=new AbortController();
  process.once('SIGTERM',()=>controller.abort());process.once('SIGINT',()=>controller.abort());
  const obs=new Observer(source,db,{signal:controller.signal});obs.init(identity);
  console.log(JSON.stringify({version:VERSION,state:'observing',limits:LIMITS}));
  try{while(!controller.signal.aborted){
    const current=fs.statSync(config.database);if(`${current.dev}:${current.ino}`!==identity)throw Error('Source replaced');
    const used=['','-wal'].reduce((n,s)=>n+(fs.existsSync(file+s)?fs.statSync(file+s).size:0),0);
    if(used>256*1024*1024)throw Error('Observer storage cap reached; export and review');
    obs.tick();await pause(2000,controller.signal);
  }}finally{controller.abort();if(obs.active)await obs.active;source.close();db.close();}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(e=>{console.error('Observer stopped:',e.message);process.exitCode=1;});
