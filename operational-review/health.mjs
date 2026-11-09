// Only two loopback reads; never fetch statistics, candidates, or research outcomes.
import {pathToFileURL} from 'node:url';
const num=x=>typeof x==='number'&&Number.isFinite(x)&&x>=0?x:null;
const bool=x=>typeof x==='boolean'?x:null;
const version=x=>typeof x==='string'&&/^[a-zA-Z0-9][a-zA-Z0-9.-]{0,63}$/.test(x)?x:null;
const count=x=>Number.isSafeInteger(x)&&x>=0?x:null;
export function projectLaunchRegistry(value){
 if(!value||typeof value!=='object'||Array.isArray(value))return {state:'unavailable'};
 const retained=count(value.retained),maxRows=count(value.limits?.maxRows),retentionDays=count(value.limits?.retentionDays);
 if(value.version!=='launch-registry-1'||retained===null||maxRows===null||maxRows===0||retentionDays===null||retentionDays===0)return {state:'unavailable'};
 return {state:'read',version:value.version,retained,limits:{maxRows,retentionDays},
  sinceRestart:Object.fromEntries(['inserted','duplicate','rejected','capacityDropped','pruned','errors'].map(k=>[k,count(value.sinceRestart?.[k])]))};
}
export function age(at,now){return num(at)!==null&&at>0?(at>now?null:(now-at)/1000):null;}
export function projectHealth(h,now){
 const n=h.notifications&&typeof h.notifications==='object'&&!Array.isArray(h.notifications)?h.notifications:null,m=h.statisticsReader||{},w=h.statisticsWorker||{};
 return {state:'read',ready:bool(h.ready),scannerVersion:version(h.scannerVersion),uptimeSeconds:num(h.uptimeSeconds),
  lastMarketAgeSeconds:age(h.lastMarketAt,now),lastLoopAgeSeconds:age(h.lastLoopAt,now),
  futureClockDetected:[h.lastMarketAt,h.lastLoopAt].some(x=>num(x)!==null&&x>now),
  versions:Object.fromEntries(['feedEvidenceVersion','entryContextVersion','metadataProvenanceVersion'].map(k=>[k,version(h[k])])),
  memory:Object.fromEntries(['heapUsedBytes','heapLimitBytes','rssBytes'].map(k=>[k,num(m[k])])),
  statistics:{version:version(w.version),hasError:typeof w.lastError==='string'&&w.lastError.length>0,
    attempts:num(w.attempts),failures:num(w.failures),eventLoopP95Ms:num(w.eventLoop?.p95Ms),eventLoopMaxMs:num(w.eventLoop?.maxMs)},
  notifications:Object.fromEntries(['pending','failed','sent'].map(k=>[k,n===null?null:Object.hasOwn(n,k)?num(n[k]):0])),
  launchRegistry:projectLaunchRegistry(h.launchRegistry),
  providers:Object.fromEntries(['dex','jupiter','helius','pumpportal'].map(k=>{const p=h.providers?.[k]||{};return [k,{
    state:['disabled','error','waiting','stale','ok'].includes(p.state)?p.state:'unknown',
    consecutiveFailures:num(p.failures),lastSuccessAgeSeconds:age(p.lastSuccessAt,now)}];}))};
}
export async function getJson(url,headers,fetcher=fetch){
 const response=await fetcher(url,{method:'GET',headers,redirect:'error',signal:AbortSignal.timeout(5000)});
 if(![200,503].includes(response.status))throw new Error('http');
 if(!response.body)throw new Error('body');
 let size=0;const chunks=[];const reader=response.body.getReader();
 try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>262144)throw new Error('cap');chunks.push(value);}}
 finally{await reader.cancel().catch(()=>{});}
 return {status:response.status,data:JSON.parse(Buffer.concat(chunks).toString('utf8'))};
}
export async function collect(env=process.env,fetcher=fetch){
 const port=env.DASHBOARD_PORT||'8787';
 if(!/^\d{1,5}$/.test(port)||Number(port)<1||Number(port)>65535)return {state:'invalid-port'};
 const base=`http://127.0.0.1:${Number(port)}`;
 let readiness,health;
 try{const r=await getJson(base+'/readyz',{},fetcher);readiness={state:'read',httpStatus:r.status,ready:bool(r.data.ready)};}
 catch{readiness={state:'unavailable'};}
 if(!env.DASHBOARD_TOKEN)health={state:'authentication-not-configured'};
 else try{const r=await getJson(base+'/api/health',{authorization:`Bearer ${env.DASHBOARD_TOKEN}`},fetcher);
  if(r.status!==200)throw new Error('http');health=projectHealth(r.data,Date.now());}
 catch{health={state:'unavailable'};}
 return {state:'collected',readiness,health,externalRequests:0};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{console.log(JSON.stringify(await collect()));}catch{console.log(JSON.stringify({state:'unavailable'}));}
}
