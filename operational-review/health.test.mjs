import test from 'node:test';
import assert from 'node:assert/strict';
import {projectHealth,projectLaunchRegistry,collect,getJson,age} from './health.mjs';
const response=(body,status=200)=>new Response(JSON.stringify(body),{status});
const registry=()=>({version:'launch-registry-1',retained:12,limits:{maxRows:20,retentionDays:30},
 sinceRestart:{inserted:2,duplicate:1,rejected:0,capacityDropped:3,pruned:0,errors:0}});
test('launch health preserves full capacity and cumulative counters using an allowlist',()=>{
 const input=registry();input.retained=20;input.private='secret';input.limits.path='secret';input.sinceRestart.rawError='secret';
 input.coverage={sourceIdentity:'secret'};
 const result=projectHealth({ready:true,launchRegistry:input},1000);
 assert.equal(result.ready,true);
 assert.deepEqual(result.launchRegistry,{state:'read',version:'launch-registry-1',retained:20,
  limits:{maxRows:20,retentionDays:30},sinceRestart:registry().sinceRestart});
 assert(!JSON.stringify(result).includes('secret'));
});
test('invalid or missing launch identity and capacity never become available',()=>{
 for(const value of [undefined,null,[],{},'registry'])assert.deepEqual(projectLaunchRegistry(value),{state:'unavailable'});
 const wrong=registry();wrong.version='future-version';assert.equal(projectLaunchRegistry(wrong).state,'unavailable');
 for(const field of ['retained','maxRows','retentionDays']){
  for(const value of [undefined,null,true,'12',-1,1.5,NaN,Infinity,Number.MAX_SAFE_INTEGER+1,...(field==='retained'?[]:[0])]){
   const input=registry();(field==='retained'?input:input.limits)[field]=value;
   assert.deepEqual(projectLaunchRegistry(input),{state:'unavailable'});
  }
 }
 const empty=registry();empty.retained=0;assert.equal(projectLaunchRegistry(empty).retained,0);
});
test('missing and invalid launch counters stay unknown while valid zero survives',()=>{
 for(const value of [undefined,null,true,'0',-1,.5,NaN,Infinity,Number.MAX_SAFE_INTEGER+1]){
  const input=registry();input.sinceRestart.capacityDropped=value;
  const result=projectLaunchRegistry(input);
  assert.equal(result.state,'read');assert.equal(result.sinceRestart.capacityDropped,null);assert.equal(result.sinceRestart.errors,0);
 }
 const input=registry();delete input.sinceRestart;
 assert(Object.values(projectLaunchRegistry(input).sinceRestart).every(x=>x===null));
});
test('health exports allowlisted operational fields, never error text or research outcomes',()=>{
 const r=projectHealth({ready:true,lastLoopAt:900,lastMarketAt:800,notifications:{sent:1},
  providers:{dex:{state:'error',lastError:'secret',lastSuccessAt:700}},
  statisticsWorker:{lastError:'private path'},research:{profit:999},private:'secret'},1000);
 assert.equal(r.lastLoopAgeSeconds,.1);assert.equal(r.notifications.pending,0);
 assert.equal(r.statistics.hasError,true);assert.equal(r.providers.dex.state,'error');
 assert(!JSON.stringify(r).includes('secret'));assert(!JSON.stringify(r).includes('private'));assert(!JSON.stringify(r).includes('profit'));
});
test('future clocks and absent notification evidence never become fresh or zero',()=>{
 assert.equal(age(1001,1000),null);const r=projectHealth({lastMarketAt:1001},1000);
 assert.equal(r.futureClockDetected,true);assert.equal(r.notifications.failed,null);
});
test('only fixed loopback readiness and authenticated health reads with redirects refused',async()=>{
 const calls=[];const fetcher=async(url,options)=>{calls.push({url,options});return response(url.endsWith('readyz')?{ready:true}:{ready:true});};
 const r=await collect({DASHBOARD_PORT:'8787',DASHBOARD_TOKEN:'secret'},fetcher);
 assert.equal(r.health.state,'read');assert.deepEqual(calls.map(c=>c.url),['http://127.0.0.1:8787/readyz','http://127.0.0.1:8787/api/health']);
 assert.equal(calls[0].options.headers.authorization,undefined);assert.equal(calls[1].options.headers.authorization,'Bearer secret');
 assert(calls.every(c=>c.options.redirect==='error'&&c.options.method==='GET'&&c.options.signal));assert(!JSON.stringify(r).includes('secret'));
});
test('invalid port makes no request, absent token does not guess authentication',async()=>{
 let n=0;const f=async()=>{n++;return response({ready:false},503);};
 assert.equal((await collect({DASHBOARD_PORT:'https://other'},f)).state,'invalid-port');assert.equal(n,0);
 const r=await collect({},f);assert.equal(n,1);assert.equal(r.readiness.httpStatus,503);assert.equal(r.health.state,'authentication-not-configured');
});
test('body cap, malformed JSON and authorization failures remain unavailable',async()=>{
 await assert.rejects(()=>getJson('http://127.0.0.1',{},async()=>new Response('x'.repeat(262145))));
 const r=await collect({DASHBOARD_TOKEN:'x'},async()=>new Response('private error',{status:401}));
 assert.equal(r.readiness.state,'unavailable');assert.equal(r.health.state,'unavailable');assert(!JSON.stringify(r).includes('private'));
 await assert.rejects(()=>getJson('http://127.0.0.1',{},async()=>new Response('{invalid')));
});
