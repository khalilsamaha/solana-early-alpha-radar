// Bounded standalone replay of the installed statistics reader. Public timings only.
import {Worker} from 'node:worker_threads';
import {pathToFileURL} from 'node:url';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
export const PROFILE_VERSION='statistics-profile-1';
export const KINDS=['alerts','outcomes','research-entries','research-outcomes','research-events'];
const CODES=new Set(['read-timeout','wal-growth-limit','row-limit','row-size-limit','read-size-limit','statistics-read-failed','worker-memory-limit','worker-error','worker-timeout','source-mismatch']);
const number=x=>typeof x==='number'&&Number.isFinite(x)&&x>=0?x:null;
export function sanitize(value){
 const d=value&&typeof value==='object'?value:{};
 return {phase:typeof d.phase==='string'&&/^(opening|loading|complete|reading:(alerts|outcomes|research-entries|research-outcomes|research-events)|summary-after:(alerts|outcomes|research-entries|research-outcomes|research-events))$/.test(d.phase)?d.phase:'unknown',
  elapsedMs:number(d.elapsedMs),rawBytes:number(d.rawBytes),heapUsedBytes:number(d.heapUsedBytes),
  kinds:Object.fromEntries(KINDS.filter(k=>d.kinds?.[k]).map(k=>{const v=d.kinds[k];return [k,Object.fromEntries(['rows','rawBytes','returnedBytes','sqliteMs','parseMs','consumerMs'].map(f=>[f,number(v[f])]))];})),
  phases:Array.isArray(d.phases)?d.phases.slice(0,16).map(p=>({phase:typeof p.phase==='string'&&/^(opening|loading|complete|reading:(alerts|outcomes|research-entries|research-outcomes|research-events)|summary-after:(alerts|outcomes|research-entries|research-outcomes|research-events))$/.test(p.phase)?p.phase:'unknown',elapsedMs:number(p.elapsedMs)})):[]};
}
export async function profile(options,{timeoutMs=10000,workerFactory=o=>new Worker(WORKER,{...o,eval:true})}={}){
 return new Promise(resolve=>{
  let worker,timer,latest=null,terminal=null,settled=false,timedOut=false;
  const finish=()=>{if(settled)return;settled=true;clearTimeout(timer);
   resolve({format:PROFILE_VERSION,state:terminal?.ok===true?'completed':'stopped',
    error:terminal?.ok===true?null:CODES.has(terminal?.error)?terminal.error:'statistics-read-failed',
    reader:options.projectionSource?'statistics-projection-1':'installed-original',diagnostic:sanitize(latest),statisticsExported:false,databaseMode:'read-only',
    networkRequests:0,modelEvaluated:false,
    limitations:['Separate worker replay; cache and failure counters of the live statistics service are unchanged.',
      'Timings include instrumentation and local contention; one run is not a sustained benchmark.',
      'A stopped run reports partial diagnostic counts only, never partial statistics.']});};
  try{
   worker=workerFactory({workerData:options,env:{},execArgv:[],resourceLimits:{maxOldGenerationSizeMb:96,maxYoungGenerationSizeMb:8,stackSizeMb:4}});
   worker.on('message',m=>{if(timedOut)return;if(m?.diagnostic)latest=sanitize(m.diagnostic);if(typeof m?.ok==='boolean')terminal={ok:m.ok,error:m.error};});
   worker.on('error',e=>{if(!timedOut)terminal={ok:false,error:e.code==='ERR_WORKER_OUT_OF_MEMORY'?'worker-memory-limit':'worker-error'};});
   worker.on('exit',code=>{if(code!==0&&!timedOut&&terminal?.ok)terminal={ok:false,error:'worker-error'};finish();});
   timer=setTimeout(()=>{timedOut=true;terminal={ok:false,error:'worker-timeout'};void worker.terminate();},timeoutMs);
  }catch{terminal={ok:false,error:'worker-error'};finish();}
 });
}
// Fixed reader behavior mirrors stats-worker-1.1.0, including every existing cap.
const WORKER=String.raw`
const {parentPort,workerData}=require('node:worker_threads');
const {DatabaseSync}=require('node:sqlite');
const {performance}=require('node:perf_hooks');
const fs=require('node:fs');const {createHash}=require('node:crypto');
(async()=>{
 const start=performance.now();let db,phase='loading',phaseAt=start,deadline,walStart=0,lastPost=0,rawBytes=0;
 const kinds={},phases=[];
 const diagnostic=()=>({phase,elapsedMs:performance.now()-start,rawBytes,kinds,phases,heapUsedBytes:process.memoryUsage().heapUsed});
 const post=(force=false)=>{if(force||performance.now()-lastPost>=250){lastPost=performance.now();parentPort.postMessage({diagnostic:diagnostic()});}};
 const mark=p=>{const n=performance.now();if(phases.length<16)phases.push({phase,elapsedMs:n-phaseAt});phase=p;phaseAt=n;post(true);};
 const walSize=()=>{try{return fs.statSync(workerData.database+'-wal').size;}catch{return 0;}};
 const guard=()=>{if(performance.now()>deadline)throw Error('read-timeout');if(walSize()-walStart>64*1024*1024)throw Error('wal-growth-limit');};
 try{
  post(true);
  for(const [file,expected] of Object.entries(workerData.expected)){
   const s=fs.lstatSync(file);if(!s.isFile()||fs.realpathSync(file)!==file||s.size>2097152||createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==expected)throw Error('source-mismatch');
  }
  const {Radar}=await import(workerData.radarUrl);
  const projected=workerData.projectionSource?await import('data:text/javascript;base64,'+Buffer.from(workerData.projectionSource).toString('base64')):null;
  // The production 8s deadline starts after imports; the parent includes startup in its 10s watchdog.
  deadline=performance.now()+8000;mark('opening');walStart=walSize();
  db=new DatabaseSync(workerData.database,{readOnly:true,timeout:500});db.exec('PRAGMA query_only=ON; PRAGMA cache_size=-4096; BEGIN');
  db.prepare('SELECT COALESCE(MAX(seq),0) AS seq FROM events').get();const at=Date.now();
  function parse(row,kind){
   const k=kinds[kind];k.rows++;if(k.rows>100000)throw Error('row-limit');
   const returned=row.data===null?0:Buffer.byteLength(row.data);const size=row.rawBytes??returned;k.returnedBytes+=returned;k.rawBytes+=size;rawBytes+=size;
   if(size>262144)throw Error('row-size-limit');if(rawBytes>1024*1024*1024)throw Error('read-size-limit');
   if(k.rows%128===0){post();guard();}
   if(row.data===null)throw Error('statistics-read-failed');
   const t=performance.now();try{return JSON.parse(row.data);}finally{k.parseMs+=performance.now()-t;}
  }
  function begin(kind){if(!['alerts','outcomes','research-entries','research-outcomes','research-events'].includes(kind))throw Error('statistics-read-failed');
   mark('reading:'+kind);kinds[kind]||={rows:0,rawBytes:0,returnedBytes:0,sqliteMs:0,parseMs:0,consumerMs:0};}
  const storage={
   *events(kind){begin(kind);const t=performance.now();const it=(projected?projected.projectedStatement(db,kind):db.prepare('SELECT data FROM events WHERE kind=? ORDER BY seq')).iterate(kind);kinds[kind].sqliteMs+=performance.now()-t;
    try{while(true){const t=performance.now();const row=it.next();kinds[kind].sqliteMs+=performance.now()-t;if(row.done)break;
     const value=parse(row.value,kind);const yielded=performance.now();yield value;kinds[kind].consumerMs+=performance.now()-yielded;}}
    finally{it.return?.();}
    guard();mark('summary-after:'+kind);
   },
   readJsonl(kind,limit){begin(kind);const t=performance.now();const rows=db.prepare('SELECT data FROM events WHERE kind=? ORDER BY seq DESC LIMIT ?').all(kind,limit);kinds[kind].sqliteMs+=performance.now()-t;
    const result=rows.reverse().map(r=>parse(r,kind));guard();mark('summary-after:'+kind);return result;}
  };
  Radar.prototype.getStats.call({storage,config:{horizonToleranceMs:workerData.toleranceMs},candidates:new Map(),status:[],getHealth:()=>null},at);
  guard();db.exec('ROLLBACK');db.close();db=null;mark('complete');parentPort.postMessage({ok:true,diagnostic:diagnostic()});
 }catch(e){const codes=['read-timeout','wal-growth-limit','row-limit','row-size-limit','read-size-limit','source-mismatch'];
  parentPort.postMessage({ok:false,error:codes.includes(e.message)?e.message:'statistics-read-failed',diagnostic:diagnostic()});
 }finally{if(db)try{db.close();}catch{}parentPort.close();}
})();`;

export async function cli(){
 // Container paths are fixed. Only readConfig's numeric tolerance is passed into an env-empty worker.
 const manifest=JSON.parse(process.argv[2]);
 const projectionSource=process.argv[3]?Buffer.from(process.argv[3],'base64').toString('utf8'):null;
 if(projectionSource&&Buffer.byteLength(projectionSource)>16384)throw Error('projection-cap');
 const expected={};
 for(const [name,hash] of Object.entries(manifest)){
  if(!/^src\/[a-zA-Z0-9/_.-]+\.js$/.test(name)||name.includes('..')||!(/^[0-9a-f]{64}$/).test(hash))throw Error('manifest');
  expected['/app/'+name]=hash;
 }
 if(Object.keys(expected).length<5||Object.keys(expected).length>80)throw Error('manifest');
 for(const [file,hash] of Object.entries(expected)){const st=fs.lstatSync(file);if(!st.isFile()||fs.realpathSync(file)!==file||st.size>2097152||createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==hash)throw Error('source-mismatch');}
 const {readConfig}=await import('file:///app/src/config.js');const config=readConfig(process.env);
 if(typeof config.dataDir!=='string'||!Number.isFinite(config.horizonToleranceMs))throw Error('config');
 const result=await profile({database:config.dataDir.replace(/\/$/,'')+'/radar.sqlite',radarUrl:'file:///app/src/core/radar.js',expected,projectionSource,toleranceMs:config.horizonToleranceMs});
 console.log(JSON.stringify({...result,capturedAt:new Date().toISOString()}));
}
if(process.argv[1]==='-'||(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)){
 try{await cli();}catch{console.log(JSON.stringify({format:PROFILE_VERSION,state:'unavailable',error:'local-profile-unavailable',statisticsExported:false,networkRequests:0,modelEvaluated:false}));process.exitCode=1;}
}
