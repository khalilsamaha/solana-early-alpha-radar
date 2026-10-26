import {Worker} from 'node:worker_threads';
import {monitorEventLoopDelay} from 'node:perf_hooks';
import {acquireCompactLease} from './stats-compact-runtime.js';
export const STATS_WORKER_VERSION='stats-compact-worker-1.0.0';
const unavailable=()=>Object.assign(new Error('Statistics temporarily unavailable'),{statusCode:503});
const ERRORS=new Set(['read-timeout','wal-growth-limit','row-limit','row-size-limit','read-size-limit','source-replaced','cache-version','cache-source-alias','source-row-invalid','source-mismatch','source-index-mismatch','source-index-required','refresh-budget','statistics-read-failed','worker-memory-limit','worker-error','worker-exited','worker-timeout','worker-start-failed','worker-result-invalid','cache-busy','cache-path','stopped']);
export class StatsService {
 constructor(database,toleranceMs,{clock=Date.now,workerFactory=(options)=>new Worker(new URL('./stats-worker.js',import.meta.url),options),leaseFactory=acquireCompactLease,timeoutMs=10000,jobTimeoutMs=130000,requestWaitMs=5000,refreshMs=30000,maxAgeMs=120000,autoStart=true,tickMs=1000}={}){
  Object.assign(this,{database,toleranceMs,clock,workerFactory,leaseFactory,timeoutMs,jobTimeoutMs,requestWaitMs,refreshMs,maxAgeMs});
  this.cache=null;this.pending=null;this.worker=null;this.closed=false;this.retryAt=0;this.error=null;this.attempts=0;this.successes=0;this.failures=0;this.progress=null;
  this.monitor=monitorEventLoopDelay({resolution:20});this.monitor.enable();this.monitorStartedAt=clock();
  if(autoStart){this.background=setInterval(()=>this.tick(),tickMs);this.background.unref();queueMicrotask(()=>this.tick());}
 }
 tick(){if(!this.closed&&!this.pending&&this.clock()>=this.retryAt&&(!this.cache||this.clock()-this.cache.snapshotAt>=this.refreshMs))void this.refresh().catch(()=>{});}
 health(){
  const now=this.clock(),count=Number(this.monitor.count);
  return {version:STATS_WORKER_VERSION,refreshing:Boolean(this.pending),snapshotAt:this.cache?.snapshotAt??null,
   ageMs:this.cache?Math.max(0,now-this.cache.snapshotAt):null,stale:!this.cache||now-this.cache.snapshotAt>60000,
   refreshMs:this.refreshMs,maxAgeMs:this.maxAgeMs,lastAttemptAt:this.lastAttemptAt??null,lastSuccessAt:this.lastSuccessAt??null,
   lastComputeMs:this.cache?.computeMs??null,lastRefreshElapsedMs:this.cache?.refreshElapsedMs??null,lastRoundTripMs:this.roundTripMs??null,workerHeapUsedBytes:this.cache?.workerHeapUsedBytes??null,
   attempts:this.attempts,successes:this.successes,failures:this.failures,lastError:this.error,retryAt:this.retryAt||null,
   sourceMaxSeq:this.cache?.sourceMaxSeq??null,rowsRead:this.cache?.rowsRead??null,reconciliation:this.cache?.reconciliation??null,progress:this.progress,
   eventLoop:{since:this.monitorStartedAt,samples:count,p95Ms:count?this.monitor.percentile(95)/1e6:null,maxMs:count?this.monitor.max/1e6:null},
   limits:{oneWorker:true,timeoutMs:this.timeoutMs,jobTimeoutMs:this.jobTimeoutMs,requestWaitMs:this.requestWaitMs,transactionDeadlineMs:8000,workerOldGenerationMiB:96,workerYoungGenerationMiB:8,rowLimitPerKind:100000,rawReadLimitMiB:1024}};
 }
 refresh(){
  if(this.pending)return this.pending;
  if(this.closed||this.clock()<this.retryAt)return Promise.reject(unavailable());
  this.attempts++;this.lastAttemptAt=this.clock();this.progress=null;
  let worker,timer,jobTimer,lease,message=null,settled=false,forcedError=null;
  const promise=new Promise((resolve,reject)=>{
   const finish=(error)=>{
    if(settled)return;settled=true;clearTimeout(timer);clearTimeout(jobTimer);this.worker=null;this.pending=null;
    try{lease?.release();}catch{error=error||'cache-busy';}
    this.roundTripMs=Math.max(0,this.clock()-this.lastAttemptAt);
    if(!error&&message?.ok===true){
     const valid=message.data&&typeof message.data==='object'&&!Array.isArray(message.data)&&Number.isFinite(message.snapshotAt)&&message.snapshotAt>0&&message.snapshotAt<=this.clock()&&this.clock()-message.snapshotAt<=this.maxAgeMs&&Number.isSafeInteger(message.sourceMaxSeq)&&message.sourceMaxSeq>=0;
     if(!valid)error='worker-result-invalid';
    }
    if(!error&&message?.ok===true){this.cache=message;this.successes++;this.lastSuccessAt=this.clock();this.error=null;this.retryAt=0;resolve(message);}
    else {this.failures++;this.error=ERRORS.has(error||message?.error)?error||message.error:'worker-exited';this.retryAt=this.clock()+30000;if(['source-replaced','source-mismatch','cache-version','cache-source-alias'].includes(this.error))this.cache=null;reject(unavailable());}
   };
   const stop=()=>{if(settled||forcedError)return;forcedError='worker-timeout';void worker.terminate();};
   const arm=()=>{clearTimeout(timer);timer=setTimeout(stop,this.timeoutMs);timer.unref();};
   try{
    lease=this.leaseFactory(this.database);
    worker=this.workerFactory({workerData:{database:this.database,cache:lease.cache,toleranceMs:this.toleranceMs},env:{},execArgv:[],
     resourceLimits:{maxOldGenerationSizeMb:96,maxYoungGenerationSizeMb:8,stackSizeMb:4}});
    this.worker=worker;
    worker.on('message',value=>{
     if(settled||forcedError)return;
     if(value?.progress&&['opening','reconciling','summarizing'].includes(value.progress.phase)&&Number.isFinite(value.progress.elapsedMs)){
      this.progress={phase:value.progress.phase,elapsedMs:value.progress.elapsedMs,at:this.clock()};arm();
     }else if(typeof value?.ok==='boolean')message=value;
    });
    worker.on('error',e=>{message={ok:false,error:e.code==='ERR_WORKER_OUT_OF_MEMORY'?'worker-memory-limit':'worker-error'};});
    worker.on('exit',code=>finish(this.closed?'stopped':forcedError||(code!==0?(message?.error||'worker-exited'):null)));
    arm();jobTimer=setTimeout(stop,this.jobTimeoutMs);jobTimer.unref();
   }catch(e){queueMicrotask(()=>finish(ERRORS.has(e.message)?e.message:'worker-start-failed'));}
  });
  this.pending=promise;promise.catch(()=>{});return promise;
 }
 async get(){
  if(this.closed)throw unavailable();
  const hadCache=Boolean(this.cache);this.tick();
  if(!this.cache){
   if(!this.pending)throw unavailable();
   let timer;
   try{await Promise.race([this.pending,new Promise((_,reject)=>{timer=setTimeout(()=>reject(unavailable()),this.requestWaitMs);timer.unref();})]);}
   finally{clearTimeout(timer);}
  }
  if(this.closed||!this.cache||this.clock()-this.cache.snapshotAt>this.maxAgeMs)throw unavailable();
  return {...this.cache.data,statistics:{...this.health(),servedFromCache:hadCache}};
 }
 async close(){this.closed=true;clearInterval(this.background);this.monitor.disable();if(this.worker)await this.worker.terminate();if(this.pending)await this.pending.catch(()=>{});}
}
