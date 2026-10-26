import {parentPort,workerData} from 'node:worker_threads';
import {performance} from 'node:perf_hooks';
import {setTimeout as delay} from 'node:timers/promises';
import {Radar} from './radar.js';
import {compactSummaryRow} from './stats-memory.js';
import {CompactStore,IDENTITY_INDEX} from './stats-compact-store.js';
import {cacheProvenance} from './stats-compact-runtime.js';
const started=performance.now();let store;
const progress=phase=>parentPort.postMessage({progress:{phase,elapsedMs:Math.round(performance.now()-started)}});
try{
 progress('opening');
 store=new CompactStore({source:workerData.database,cache:workerData.cache,compact:compactSummaryRow,...cacheProvenance()});
 if(store.identityIndex!==IDENTITY_INDEX)throw Error('source-index-required');
 let readRows=0,reusedRows=0,batches=0,validationMs=0;
 for(;;){
  if(performance.now()-started>120000)throw Error('refresh-budget');
  progress('reconciling');const batch=store.step();batches++;readRows+=batch.readRows;reusedRows+=batch.reusedRows;
  if(batch.phase==='validation-required'){
   progress('summarizing');const at=performance.now();
   const result=store.validateAndSummarize((storage,now)=>Radar.prototype.getStats.call({storage,config:{horizonToleranceMs:workerData.toleranceMs},candidates:new Map(),status:[],getHealth:()=>null},now));
   validationMs=performance.now()-at;
   if(result.complete){
    if(performance.now()-started>120000)throw Error('refresh-budget');
    const {health,status,totalCandidates,activeCandidates,...data}=result.result;
    parentPort.postMessage({ok:true,data,snapshotAt:result.snapshotAt,sourceMaxSeq:result.sourceMaxSeq,
     computeMs:Math.round(validationMs),refreshElapsedMs:Math.round(performance.now()-started),rowsRead:result.counts,rawBytes:result.rawBytes,
     reconciliation:{batches,readRows:readRows+result.catchupReadRows,reusedRows,removedRows:result.catchupRemovedRows},
     workerHeapUsedBytes:process.memoryUsage().heapUsed});
    break;
   }
  }
  await delay(10);
 }
}catch(e){
 const allowed=new Set(['read-timeout','wal-growth-limit','row-limit','row-size-limit','read-size-limit','source-replaced','cache-version','cache-source-alias','source-row-invalid','source-mismatch','source-index-mismatch','source-index-required','refresh-budget']);
 parentPort.postMessage({ok:false,error:allowed.has(e.message)?e.message:'statistics-read-failed'});
}finally{try{store?.close();}catch{}parentPort.close();}
