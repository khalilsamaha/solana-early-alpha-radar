import {Worker} from 'node:worker_threads';
import {monitorEventLoopDelay} from 'node:perf_hooks';
export const STATS_WORKER_VERSION='stats-worker-1.1.0';
const unavailable=()=>Object.assign(new Error('Statistics temporarily unavailable'),{statusCode:503});
export class StatsService {
 constructor(database,toleranceMs,{clock=Date.now,workerFactory=(options)=>new Worker(new URL('./stats-worker.js',import.meta.url),options),timeoutMs=10000,refreshMs=30000,maxAgeMs=120000}={}){
  Object.assign(this,{database,toleranceMs,clock,workerFactory,timeoutMs,refreshMs,maxAgeMs});
  this.cache=null;this.pending=null;this.worker=null;this.closed=false;this.retryAt=0;this.error=null;this.attempts=0;this.successes=0;this.failures=0;
  this.monitor=monitorEventLoopDelay({resolution:20});this.monitor.enable();this.monitorStartedAt=clock();
 }
 health(){
  const now=this.clock(),count=Number(this.monitor.count);
  return {version:STATS_WORKER_VERSION,refreshing:Boolean(this.pending),snapshotAt:this.cache?.snapshotAt??null,
   ageMs:this.cache?Math.max(0,now-this.cache.snapshotAt):null,stale:!this.cache||now-this.cache.snapshotAt>60000,
   refreshMs:this.refreshMs,maxAgeMs:this.maxAgeMs,lastAttemptAt:this.lastAttemptAt??null,lastSuccessAt:this.lastSuccessAt??null,
   lastComputeMs:this.cache?.computeMs??null,lastRoundTripMs:this.roundTripMs??null,workerHeapUsedBytes:this.cache?.workerHeapUsedBytes??null,
   attempts:this.attempts,successes:this.successes,failures:this.failures,lastError:this.error,retryAt:this.retryAt||null,
   sourceMaxSeq:this.cache?.sourceMaxSeq??null,rowsRead:this.cache?.rowsRead??null,
   eventLoop:{since:this.monitorStartedAt,samples:count,p95Ms:count?this.monitor.percentile(95)/1e6:null,maxMs:count?this.monitor.max/1e6:null},
   limits:{oneWorker:true,timeoutMs:this.timeoutMs,workerOldGenerationMiB:96,workerYoungGenerationMiB:8,rowLimitPerKind:100000,rawReadLimitMiB:1024}};
 }
 refresh(){
  if(this.pending)return this.pending;
  if(this.closed||this.clock()<this.retryAt)return Promise.reject(unavailable());
  this.attempts++;this.lastAttemptAt=this.clock();
  let worker,timer,message=null,settled=false;
  const promise=new Promise((resolve,reject)=>{
   const finish=(error)=>{
    if(settled)return;settled=true;clearTimeout(timer);this.worker=null;this.pending=null;
    this.roundTripMs=Math.max(0,this.clock()-this.lastAttemptAt);
    if(!error&&message?.ok===true){this.cache=message;this.successes++;this.lastSuccessAt=this.clock();this.error=null;this.retryAt=0;resolve(message);}
    else {this.failures++;this.error=error||message?.error||'worker-exited';this.retryAt=this.clock()+30000;reject(unavailable());}
   };
   try{
    worker=this.workerFactory({workerData:{database:this.database,toleranceMs:this.toleranceMs},env:{},execArgv:[],
     resourceLimits:{maxOldGenerationSizeMb:96,maxYoungGenerationSizeMb:8,stackSizeMb:4}});
    this.worker=worker;
    worker.on('message',value=>{message=value;});
    worker.on('error',e=>{message={ok:false,error:e.code==='ERR_WORKER_OUT_OF_MEMORY'?'worker-memory-limit':'worker-error'};});
    worker.on('exit',code=>finish(this.closed?'stopped':code!==0?(message?.error||'worker-exited'):null));
    timer=setTimeout(()=>{message={ok:false,error:'worker-timeout'};void worker.terminate();},this.timeoutMs);timer.unref();
   }catch{queueMicrotask(()=>finish('worker-start-failed'));}
  });
  this.pending=promise;promise.catch(()=>{});return promise;
 }
 async get(){
  if(this.closed)throw unavailable();
  const hadCache=Boolean(this.cache);
  if(!this.cache||this.clock()-this.cache.snapshotAt>=this.refreshMs){
   if(!this.pending&&this.clock()>=this.retryAt)this.refresh();
   if(!this.cache){if(!this.pending)throw unavailable();await this.pending;}
  }
  if(!this.cache||this.clock()-this.cache.snapshotAt>this.maxAgeMs)throw unavailable();
  return {...this.cache.data,statistics:{...this.health(),servedFromCache:hadCache}};
 }
 async close(){this.closed=true;this.monitor.disable();if(this.worker)await this.worker.terminate();if(this.pending)await this.pending.catch(()=>{});}
}
