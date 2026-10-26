import test from 'node:test';
import assert from 'node:assert/strict';
import {projectHealth,collect,getJson,age} from './health.mjs';
const response=(body,status=200)=>new Response(JSON.stringify(body),{status});
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
