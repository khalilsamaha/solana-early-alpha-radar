import {parentPort,workerData} from 'node:worker_threads';
import {DatabaseSync} from 'node:sqlite';
import {performance} from 'node:perf_hooks';
import fs from 'node:fs';
import {Radar} from './radar.js';
const start=performance.now(),deadline=start+8000;
let db;
try {
 const wal=workerData.database+'-wal';
 const walSize=()=>{try{return fs.statSync(wal).size;}catch{return 0;}};
 const walStart=walSize();let rawBytes=0;const rowsRead={};
 function guard(){if(performance.now()>deadline)throw Error('read-timeout');if(walSize()-walStart>64*1024*1024)throw Error('wal-growth-limit');}
 db=new DatabaseSync(workerData.database,{readOnly:true,timeout:500});
 db.exec('PRAGMA query_only=ON; PRAGMA cache_size=-4096; BEGIN');
 const sourceMaxSeq=Number(db.prepare('SELECT COALESCE(MAX(seq),0) AS seq FROM events').get().seq),snapshotAt=Date.now();
 function parse(row,kind){
  rowsRead[kind]=(rowsRead[kind]||0)+1;
  if(rowsRead[kind]>100000)throw Error('row-limit');
  const size=Buffer.byteLength(row.data);if(size>262144)throw Error('row-size-limit');
  rawBytes+=size;if(rawBytes>1024*1024*1024)throw Error('read-size-limit');
  if(rowsRead[kind]%128===0)guard();
  return JSON.parse(row.data);
 }
 const storage={
  *events(kind){for(const r of db.prepare('SELECT data FROM events WHERE kind=? ORDER BY seq').iterate(kind))yield parse(r,kind);guard();},
  readJsonl(kind,limit){return db.prepare('SELECT data FROM events WHERE kind=? ORDER BY seq DESC LIMIT ?').all(kind,limit).reverse().map(r=>parse(r,kind));}
 };
 const context={storage,config:{horizonToleranceMs:workerData.toleranceMs},candidates:new Map(),status:[],getHealth:()=>null};
 const full=Radar.prototype.getStats.call(context,snapshotAt);
 guard();db.exec('ROLLBACK');db.close();db=null;
 const {health,status,totalCandidates,activeCandidates,...data}=full;
 parentPort.postMessage({ok:true,data,snapshotAt,sourceMaxSeq,computeMs:Math.round(performance.now()-start),rowsRead,rawBytes,workerHeapUsedBytes:process.memoryUsage().heapUsed});
} catch(e) {
 const allowed=new Set(['read-timeout','wal-growth-limit','row-limit','row-size-limit','read-size-limit']);
 parentPort.postMessage({ok:false,error:allowed.has(e.message)?e.message:'statistics-read-failed'});
} finally {if(db)try{db.close();}catch{}parentPort.close();}
