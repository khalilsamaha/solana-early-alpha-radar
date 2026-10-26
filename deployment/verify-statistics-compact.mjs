// Bounded local API acceptance check. Never exports statistics, tokens or credentials.
import fs from 'node:fs';
import path from 'node:path';
import {gzipSync} from 'node:zlib';
import {performance} from 'node:perf_hooks';
import {pathToFileURL} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';
const allowed=new Set(['read-timeout','wal-growth-limit','row-limit','row-size-limit','read-size-limit','source-replaced','cache-version','source-mismatch','source-index-mismatch','source-index-required','refresh-budget','statistics-read-failed','worker-memory-limit','worker-error','worker-exited','worker-timeout','worker-start-failed','worker-result-invalid','cache-busy','cache-path','stopped']);
function summary(w={}){return {version:w.version==='stats-compact-worker-1.0.0'?w.version:'other-or-missing',snapshotAt:w.snapshotAt,ageMs:w.ageMs,refreshing:w.refreshing===true,attempts:w.attempts,successes:w.successes,failures:w.failures,lastComputeMs:w.lastComputeMs,lastRefreshElapsedMs:w.lastRefreshElapsedMs,lastError:w.lastError==null?null:allowed.has(w.lastError)?w.lastError:'unclassified'};}
export async function observe({read,now=()=>performance.now(),sleep=delay,budgetMs=180000}){
 const report={format:'statistics-compact-acceptance-1',capturedAt:new Date().toISOString(),state:'observing',samples:[],modelEvaluated:false,remoteRequests:0};
 const started=now();let ready=true;const snapshots=new Set();
 while(now()-started<budgetMs){
  const [health,readiness]=await Promise.all([read('/api/health'),read('/readyz')]);
  const stats=await read('/api/stats'),w=summary(health.body?.statisticsWorker),s=stats.body?.statistics;
  ready&&=readiness.status===200;
  if(stats.status===200&&s?.version==='stats-compact-worker-1.0.0'&&Number.isFinite(s.snapshotAt)&&s.snapshotAt>0&&Number.isFinite(s.ageMs)&&s.ageMs>=0&&s.ageMs<=120000)snapshots.add(s.snapshotAt);
  report.samples.push({at:new Date().toISOString(),healthHttp:health.status,healthElapsedMs:health.elapsedMs,readyHttp:readiness.status,statisticsHttp:stats.status,statisticsElapsedMs:stats.elapsedMs,statistics:w});
  if(ready&&snapshots.size>=2&&health.status===200&&stats.status===200&&w.version==='stats-compact-worker-1.0.0'&&Number.isFinite(w.ageMs)&&w.ageMs>=0&&w.ageMs<=120000){report.state='passed';break;}
  await sleep(5000);
 }
 if(report.state!=='passed')report.state='needs-review';
 report.distinctServedSnapshots=snapshots.size;report.readyThroughout=ready;return report;
}
export async function cli(){
 const port=Number(process.env.DASHBOARD_PORT||8787);
 if(!Number.isSafeInteger(port)||port<1||port>65535||!process.env.DASHBOARD_TOKEN)throw Error('Local dashboard configuration required');
 const base=`http://127.0.0.1:${port}`,headers={Authorization:`Bearer ${process.env.DASHBOARD_TOKEN}`};
 async function read(route){const start=performance.now();try{const r=await fetch(base+route,{headers,redirect:'error',signal:AbortSignal.timeout(8000)});const text=await r.text();if(text.length>2097152)throw Error('response-cap');return {status:r.status,elapsedMs:Math.round(performance.now()-start),body:r.ok?JSON.parse(text):null};}catch{return {status:null,elapsedMs:Math.round(performance.now()-start),body:null};}}
 console.log('Observing readiness, statistics and background refresh for about three minutes at most...');
 const report=await observe({read});
 const file=path.resolve(`radar-statistics-acceptance-${new Date().toISOString().replace(/[-:.]/g,'')}-${process.pid}.json.gz`);
 fs.writeFileSync(file,gzipSync(JSON.stringify(report)),{flag:'wx',mode:0o600});
 console.log('Acceptance:',report.state);console.log('Upload:',file);process.exitCode=report.state==='passed'?0:1;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)await cli();
