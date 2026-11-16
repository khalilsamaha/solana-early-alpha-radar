// Full image-contained application probe. Only synthetic IPC and loopback HTTP.
import fs from 'node:fs';
import {DatabaseSync} from 'node:sqlite';
import {verify} from './verify.mjs';

const scenario=process.argv[2];
if(!['normal','sequence-gap','missing-endpoint'].includes(scenario))throw Error('runtime-probe-case');
const identity=verify();
process.umask(0o077);
Object.assign(process.env,{PUMPPORTAL_SOURCE:'shared',PUMPPORTAL_SOCKET:'/r1-ipc/discovery.sock',
  DATA_DIR:'/r1-data',DASHBOARD_HOST:'127.0.0.1',DASHBOARD_PORT:'8787',
  RESEARCH_ENABLED:'false',NOTIFICATIONS_ENABLED:'false',OPERATIONAL_NOTIFICATIONS:'false',
  RESEARCH_NOTIFICATIONS:'false',MAX_CANDIDATES:'10'});
for(const key of ['PUMPPORTAL_API_KEY','JUPITER_API_KEY','HELIUS_API_KEY','TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID','DASHBOARD_TOKEN'])
  if(process.env[key])throw Error('runtime-probe-credential');
if(fs.existsSync('.env')||fs.readdirSync('/r1-data').length)throw Error('runtime-probe-nonempty-input');
let upstreamAttempts=0,blockedFetches=0,applicationStarted=false,storageClosed=false,radarStopped=false;
let health=null,candidates=null,failure=false,refused=false,emitted=false,fixtureIndexPrepared=false;
const originalFetch=globalThis.fetch;
globalThis.WebSocket=class{constructor(){upstreamAttempts++;throw Error('runtime-probe-upstream-forbidden');}};
globalThis.fetch=(input,options)=>{
  const url=new URL(typeof input==='string'?input:input.url);
  if(url.origin==='http://127.0.0.1:8787'&&['/healthz','/api/health','/api/candidates'].includes(url.pathname))
    return originalFetch(input,options);
  blockedFetches++;return Promise.reject(Error('runtime-probe-public-http-forbidden'));
};
// Keep application logs out of the fixed result protocol. Unexpected stderr is
// still captured/bounded by the parent, and nonzero exit cannot pass acceptance.
console.log=()=>{};
const {Storage}=await import('./scanner/src/core/storage.js');
const {Radar}=await import('./scanner/src/core/radar.js');
// Production has a separately provisioned covering index. Prepare it only in
// this brand-new fixture database; never migrate an existing database here.
if(scenario!=='missing-endpoint'){
  const {CREATE_IDENTITY_INDEX}=await import('./scanner/src/core/stats-compact-store.js');
  const fixture=new Storage('/r1-data');
  try{fixture.db.exec(CREATE_IDENTITY_INDEX);fixtureIndexPrepared=true;}finally{fixture.close();}
}
const close=Storage.prototype.close,stop=Radar.prototype.stop;
Storage.prototype.close=function(){const result=close.call(this);storageClosed=true;return result;};
Radar.prototype.stop=async function(){await stop.call(this);radarStopped=true;};

function emit(){
  if(emitted)return;emitted=true;
  let persistedLaunches=null,persistedCandidates=null;
  if(applicationStarted&&storageClosed&&radarStopped){
    try{
      const db=new DatabaseSync('/r1-data/radar.sqlite',{readOnly:true});
      try{
        persistedLaunches=Number(db.prepare('SELECT count(*) AS n FROM launch_registry').get().n);
        persistedCandidates=Number(db.prepare('SELECT count(*) AS n FROM candidates').get().n);
      }finally{db.close();}
    }catch{failure=true;}
  }
  const noStorage=!fs.existsSync('/r1-data/radar.sqlite');
  const expected=scenario==='normal'?{requests:3,launches:2,candidates:3}:{requests:0,launches:0,candidates:0};
  const complete=scenario==='missing-endpoint'
    ?refused&&!applicationStarted&&noStorage&&upstreamAttempts===0&&blockedFetches===0
    :applicationStarted&&storageClosed&&radarStopped&&health?.providers.pumpportal.enabled===true&&
      health.providers.pumpportal.state==='error'&&health.providers.pumpportal.requests===expected.requests&&
      health.providers.pumpportal.failures===1&&health.launchRegistry.retained===expected.launches&&
      candidates?.length===expected.candidates&&persistedLaunches===expected.launches&&
      persistedCandidates===expected.candidates&&upstreamAttempts===0&&fixtureIndexPrepared&&
      health.statisticsWorker.successes>0&&health.statisticsWorker.lastError===null;
  if(!complete||failure)process.exitCode=1;
  process.stdout.write(JSON.stringify({schema:1,kind:'full-scanner-runtime-probe',identity,case:scenario,
    outcome:complete&&!failure?(refused?'startup-refused-before-storage':'application-gap-and-shutdown-confirmed'):'runtime-unconfirmed',
    application_entrypoint_started:applicationStarted,upstream_attempts:upstreamAttempts,
    blocked_public_http_attempts:blockedFetches,public_http_connections_opened:0,
    loopback_http_checked:health!==null,overall_ready:health?.ready??null,provider_enabled:health?.providers.pumpportal.enabled??null,
    provider_state:health?.providers.pumpportal.state??null,discovery_messages:health?.providers.pumpportal.requests??0,
    discovery_gaps:health?.providers.pumpportal.failures??0,candidates:candidates?.length??0,
    persisted_candidates:persistedCandidates,persisted_launches:persistedLaunches,
    fixture_index_prepared:fixtureIndexPrepared,statistics_worker_succeeded:(health?.statisticsWorker.successes??0)>0,
    storage_created:!noStorage,storage_closed:storageClosed,radar_stopped:radarStopped,
    activation_authorized:false})+'\n');
}
process.once('beforeExit',emit);
try{
  await import('./scanner/src/index.js');applicationStarted=true;
  if(scenario==='missing-endpoint')throw Error('runtime-probe-started-unexpectedly');
  const deadline=performance.now()+12000;
  while(performance.now()<deadline){
    try{
      const alive=await globalThis.fetch('http://127.0.0.1:8787/healthz',{signal:AbortSignal.timeout(500)});
      if(!alive.ok)throw Error('not-alive');
      const response=await globalThis.fetch('http://127.0.0.1:8787/api/health',{signal:AbortSignal.timeout(500)});
      const current=await response.json();
      if(current.providers.pumpportal.failures===1&&current.statisticsWorker.successes>0&&current.statisticsWorker.lastError===null){
        health=current;
        candidates=await(await globalThis.fetch('http://127.0.0.1:8787/api/candidates',{signal:AbortSignal.timeout(500)})).json();
        break;
      }
    }catch{}
    await new Promise(resolve=>setTimeout(resolve,20));
  }
  if(health===null)throw Error('runtime-probe-evidence-deadline');
}catch(error){
  if(scenario==='missing-endpoint'&&!applicationStarted&&error.code==='ENOENT'&&error.path==='/r1-ipc/discovery.sock')refused=true;
  else failure=true;
}finally{
  if(applicationStarted)process.kill(process.pid,'SIGTERM');
  else emit();
}
