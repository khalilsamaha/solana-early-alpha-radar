import {Worker} from 'node:worker_threads';
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const ERRORS=new Set(['read-timeout','wal-growth-limit','row-limit','row-size-limit','read-size-limit','source-replaced','cache-version','cache-source-alias','source-row-invalid','worker-timeout','worker-memory-limit','cache-busy','source-mismatch']);
export async function benchmark(options,{watchdogMs=10000,workerFactory=o=>new Worker(WORKER,{...o,eval:true})}={}){
 return new Promise(resolve=>{
  let w,timer,done=false,timedOut=false,terminal=null,progress=null;
  const arm=()=>{clearTimeout(timer);timer=setTimeout(()=>{timedOut=true;terminal={state:'stopped',error:'worker-timeout'};void w.terminate();},watchdogMs);};
  const finish=()=>{if(done)return;done=true;clearTimeout(timer);resolve({format:'statistics-compact-benchmark-1',capturedAt:new Date().toISOString(),state:terminal?.state||'stopped',error:terminal?.error&&ERRORS.has(terminal.error)?terminal.error:terminal?.state==='completed'||terminal?.state==='paused'?null:'benchmark-failed',diagnostic:progress,sourceMode:'read-only',derivedCacheMode:'read-write',statisticsExported:false,modelEvaluated:false,networkRequests:0});};
  try{
   w=workerFactory({workerData:options,env:{},execArgv:[],resourceLimits:{maxOldGenerationSizeMb:96,maxYoungGenerationSizeMb:8,stackSizeMb:4}});
   w.on('message',m=>{if(timedOut||done)return;if(m.progress){progress=m.progress;arm();}if(m.terminal)terminal=m.terminal;});
   w.on('error',e=>{if(!timedOut)terminal={state:'stopped',error:e.code==='ERR_WORKER_OUT_OF_MEMORY'?'worker-memory-limit':'benchmark-failed'};});
   w.on('exit',code=>{if(code!==0&&!timedOut&&terminal?.state!=='stopped')terminal={state:'stopped',error:'benchmark-failed'};finish();});arm();
  }catch{terminal={state:'stopped',error:'benchmark-failed'};finish();}
 });
}
const WORKER=String.raw`
const {workerData:o,parentPort}=require('node:worker_threads');
const {performance}=require('node:perf_hooks');
const fs=require('node:fs');
const {createHash}=require('node:crypto');
(async()=>{
 const started=performance.now(),rounds=[];let store,batches=0,readRows=0,reusedRows=0,lastPost=0;
 const post=(phase,force=false)=>{if(force||performance.now()-lastPost>250){lastPost=performance.now();parentPort.postMessage({progress:{phase,elapsedMs:performance.now()-started,batches,readRows,reusedRows,heapUsedBytes:process.memoryUsage().heapUsed,rounds}});}};
 const stop=(state,error)=>{parentPort.postMessage({terminal:{state,error}});};
 try{
  post('opening',true);
  for(const [file,hash] of Object.entries(o.expected)){
   const s=fs.lstatSync(file);if(!s.isFile()||fs.realpathSync(file)!==file||s.size>2097152||createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==hash)throw Error('source-mismatch');
  }
  const {CompactStore}=await import('data:text/javascript;base64,'+Buffer.from(o.storeSource).toString('base64'));
  const {compactSummaryRow}=await import(o.compactUrl),{Radar}=await import(o.radarUrl);
  store=new CompactStore({source:o.database,cache:o.cache,compact:compactSummaryRow,provenance:createHash('sha256').update(JSON.stringify(o.expected)).update(o.storeSource).digest('hex')});
  for(let round=0;round<2;round++){
   const began=performance.now(),readStart=readRows,reuseStart=reusedRows;let retries=0;
   while(true){
    if(performance.now()-started>=o.budgetMs){post('budget-paused',true);stop('paused',null);return;}
    post(round?'warm-reconciliation':'initial-build');
    const batch=store.step();batches++;readRows+=batch.readRows;reusedRows+=batch.reusedRows;
    if(batch.phase==='validation-required'){
     post('validating-and-summarizing',true);const summarizeAt=performance.now();
     const result=store.validateAndSummarize((storage,now)=>Radar.prototype.getStats.call({storage,config:{horizonToleranceMs:o.toleranceMs},candidates:new Map(),status:[],getHealth:()=>null},now));
     if(result.complete){rounds.push({round:round?'warm':'initial-or-resumed',elapsedMs:performance.now()-began,validationAndSummaryMs:performance.now()-summarizeAt,readRows:readRows-readStart,reusedRows:reusedRows-reuseStart,snapshotAt:result.snapshotAt,sourceMaxSeq:result.sourceMaxSeq,counts:result.counts,originalBytes:result.rawBytes});break;}
     if(++retries>=2){post('source-changing',true);stop('paused',null);return;}
    }
    await new Promise(r=>setTimeout(r,10));
   }
  }
  post('complete',true);stop('completed',null);
 }catch(e){post('stopped',true);stop('stopped',e.message);}
 finally{if(store)try{store.close();}catch{}parentPort.close();}
})();`;
function privateFile(file){const s=fs.lstatSync(file);if(!s.isFile()||s.isSymbolicLink()||s.uid!==process.getuid()||(s.mode&0o077)||s.nlink!==1)throw Error('cache-path');}
export async function cli(){
 const manifest=JSON.parse(process.argv[2]),storeSource=Buffer.from(process.argv[3]||'','base64').toString('utf8');
 if(!storeSource||Buffer.byteLength(storeSource)>32768)throw Error('candidate-cap');
 const expected={};
 for(const [name,hash] of Object.entries(manifest)){
  if(!/^src\/[a-zA-Z0-9/_.-]+\.js$/.test(name)||name.includes('..')||!/^[0-9a-f]{64}$/.test(hash))throw Error('manifest');
  expected['/app/'+name]=hash;
 }
 if(Object.keys(expected).length<5||Object.keys(expected).length>80)throw Error('manifest');
 for(const [file,hash] of Object.entries(expected)){const s=fs.lstatSync(file);if(!s.isFile()||fs.realpathSync(file)!==file||s.size>2097152||createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==hash)throw Error('source-mismatch');}
 const {readConfig}=await import('file:///app/src/config.js'),config=readConfig(process.env);
 const data=path.resolve(config.dataDir);if(fs.realpathSync(data)!==data||!Number.isFinite(config.horizonToleranceMs))throw Error('data-path');
 const directory=path.join(data,'statistics-cache-lab-1');
 fs.mkdirSync(directory,{mode:0o700,recursive:true});const ds=fs.lstatSync(directory);
 if(!ds.isDirectory()||ds.isSymbolicLink()||ds.uid!==process.getuid()||(ds.mode&0o077))throw Error('cache-path');
 const lock=path.join(directory,'active.lock');let fd;
 try{fd=fs.openSync(lock,'wx',0o600);}catch(e){if(e.code==='EEXIST')throw Error('cache-busy');throw e;}
 try{
  fs.writeSync(fd,String(process.pid));const cache=path.join(directory,'compact.sqlite');
  try{fs.closeSync(fs.openSync(cache,'wx',0o600));}catch(e){if(e.code!=='EEXIST')throw e;}
  privateFile(cache);
  for(const suffix of ['-journal','-wal','-shm'])if(fs.existsSync(cache+suffix))privateFile(cache+suffix);
  const report=await benchmark({database:path.join(data,'radar.sqlite'),cache,storeSource,expected,toleranceMs:config.horizonToleranceMs,radarUrl:'file:///app/src/core/radar.js',compactUrl:'file:///app/src/core/stats-memory.js',budgetMs:120000});
  report.cacheBytes=fs.statSync(cache).size;console.log(JSON.stringify(report));
 }finally{fs.closeSync(fd);fs.unlinkSync(lock);}
}
if(process.argv[1]==='-'||(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)){
 try{await cli();}catch(e){console.log(JSON.stringify({format:'statistics-compact-benchmark-1',state:'unavailable',error:ERRORS.has(e.message)?e.message:'local-benchmark-unavailable',statisticsExported:false,modelEvaluated:false,networkRequests:0}));process.exitCode=1;}
}
