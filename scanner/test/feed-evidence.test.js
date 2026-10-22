import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
import {transportEvidence,attachFeed,applyFeed} from '../src/core/feed-evidence.js';
import {HttpClient} from '../src/core/http.js';
import {getTokenPairs} from '../src/adapters/dexscreener.js';
import {Research} from '../src/core/research.js';
import {Storage} from '../src/core/storage.js';
import {Radar} from '../src/core/radar.js';import {readConfig} from '../src/config.js';
const T=1800000000000;
function market(at,extra={}){const m={mint:'token',pairAddress:'pool',priceUsd:1,liquidityUsd:20000,volume:{m5:5000},txns:{m5:{buys:70,sells:30}},...extra};return attachFeed(m,transportEvidence({status:200,headers:new Headers()},at-30,at-20,at-10,at),'tokens-batch');}
function store(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'feed-'));const s=new Storage(dir);t.after(()=>{s.close();fs.rmSync(dir,{recursive:true,force:true});});return s;}
test('transport records clocks and only bounded cache metadata, never price freshness or arbitrary headers',()=>{
 const h=new Headers({'Age':'45','Date':'Mon, 12 Oct 2026 06:00:00 GMT','CF-Cache-Status':'HIT','Authorization':'private','Set-Cookie':'private','X-Cache':'private'});
 const e=transportEvidence({status:200,headers:h},10,20,50,60);
 assert.equal(e.queueMs,10);assert.equal(e.headersMs,30);assert.equal(e.bodyMs,10);assert.equal(e.httpAgeSeconds,45);assert.equal(e.providerPriceAt,null);assert.equal(e.cfCacheStatus,'HIT');assert.ok(!JSON.stringify(e).includes('private'));
 h.set('Age','-1');h.set('Date','bad');h.set('CF-Cache-Status','private');const unknown=transportEvidence({status:200,headers:h},50,20,10,60);
 assert.equal(unknown.clocksOrdered,false);assert.equal(unknown.queueMs,null);assert.equal(unknown.httpAgeSeconds,null);assert.equal(unknown.httpDateAt,null);assert.equal(unknown.cfCacheStatus,null);
});
test('HTTP evidence adds no fetches, preserves body and options, and callback failures cannot fail market reads',async t=>{
 let calls=0,evidence;const body=[{ok:true}];
 t.mock.method(globalThis,'fetch',async(url,options)=>{calls++;assert.equal(options.headers.Authorization,'secret');assert.equal(options.recordEvidence,undefined);return {ok:true,status:200,headers:new Headers(),json:async()=>body};});
 const client=new HttpClient({dexRpm:600000},{success(){},failure(){assert.fail('unexpected failure');}});
 assert.equal(await client.json('dex','https://example.invalid',{headers:{Authorization:'secret'}},e=>{evidence=e;}),body);
 assert.equal(evidence.httpStatus,200);assert.ok(evidence.clocksOrdered);assert.equal(evidence.providerPriceAt,null);
 assert.equal(await client.json('dex','https://example.invalid',{headers:{Authorization:'secret'}},()=>{throw Error('diagnostic');}),body);assert.equal(calls,2);
});
test('HTTP failures do not emit successful feed evidence or add retries',async t=>{
 let calls=0,records=0;t.mock.method(globalThis,'fetch',async()=>{calls++;return {ok:false,status:503,headers:new Headers()};});
 const client=new HttpClient({dexRpm:120},{success(){assert.fail();},failure(){}});
 await assert.rejects(client.json('dex','https://example.invalid',{},()=>records++),/503/);assert.equal(records,0);assert.equal(calls,1);
});
test('batch provenance follows actual endpoint and pool without changing batch size or missing observations',async()=>{
 let calls=0;const raw=(mint,pool)=>({chainId:'solana',baseToken:{address:mint},pairAddress:pool,priceUsd:'1'});
 const result=await getTokenPairs([{mint:'a'},{mint:'b',paperEntry:{pairAddress:'original'}},{mint:'missing'}],{json:async(_,url,options,record)=>{calls++;record(transportEvidence({status:200,headers:new Headers()},1,2,3,4));return url.includes('/tokens/')?[raw('a','other')]:{pairs:[raw('b','original')]};}});
 assert.equal(calls,2);assert.equal(result.get('a').market.feedEvidence.endpoint,'tokens-batch');assert.equal(result.get('b').market.feedEvidence.endpoint,'pairs-batch');assert.equal(result.get('b').market.feedEvidence.pairAddress,'original');assert.equal(result.get('missing').market,null);
});
test('repeated prices and selected values differ; pool switches, gaps and backwards clocks reset comparison',()=>{
 const m1=market(T),a=applyFeed(null,m1,T+5);const m2=market(T+15000,{volume:{m5:6000}}),b=applyFeed({...m1,feedEvidence:a},m2,T+15007);
 assert.equal(b.repeatedPriceCount,1);assert.equal(b.repeatedValuesCount,0);assert.equal(b.priceUnchangedSince,T);assert.equal(b.applyDelayMs,7);
 const c=applyFeed({...m2,feedEvidence:b},market(T+30000,{volume:{m5:6000}}),T+30009);assert.equal(c.repeatedPriceCount,2);assert.equal(c.repeatedValuesCount,1);
 for(const next of [market(T+60001),market(T-1),market(T+16000,{pairAddress:'other'})])assert.equal(applyFeed({...m2,feedEvidence:b},next,next.feedEvidence.bodyAt).comparison,'new-or-gapped');
 assert.equal(applyFeed(null,m1,T-1).clocksOrdered,false);assert.equal(applyFeed(null,{priceUsd:1},T),null);
});
test('research entries and observed checkpoints preserve their own feed clocks; missing checkpoints have none',t=>{
 const s=store(t),r=new Research({researchEnabled:true,securityTtlMs:300000,researchNotifications:false},s);
 for(const ms of [0,15000,30000,45000,60000]){const m=market(T+ms,{priceUsd:1+ms/100000,txns:{m5:{buys:70+ms/1000,sells:30}},volume:{m5:5000+ms/10}});const c={...m,feedEvidence:applyFeed(null,m,T+ms),marketObservedAt:T+ms,marketAttemptStatus:'observed'};r.observe(c,c,{},T+ms,true);if(!ms)r.baseline(c,T);}
 const b=s.readJsonl('research-entries').find(e=>e.cohort==='baseline');assert.equal(b.feedEvidence.bodyAt,T);
 assert.equal(s.readJsonl('research-outcomes')[0].feedEvidence.bodyAt,T+30000);
 const f=s.readJsonl('fast-shadow-entries')[0];assert.equal(f.feedEvidence.bodyAt,T+30000);
 const o=s.readJsonl('fast-shadow-outcomes')[0];assert.equal(o.feedEvidence.bodyAt,T+60000);
 r.fast.sweep(T+400000);assert.ok(s.readJsonl('fast-shadow-outcomes').filter(x=>x.status==='missing').every(x=>!x.feedEvidence));
 assert.deepEqual(s.notificationStats(),{});
});
test('Radar measures application delay but keeps score, snapshots, schedules and unknown transport behavior',t=>{
 t.mock.method(Date,'now',()=>T);const s=store(t),r=new Radar(readConfig({}),s);r.candidates.set('token',{mint:'token',firstSeenAt:T});
 const m=market(T-100);r.applyObservation('token',{market:m,observedAt:T-100});const c=r.candidates.get('token');
 assert.equal(c.feedEvidence.applyDelayMs,100);assert.equal(c.marketObservedAt,T-100);assert.equal(r.getHealth().feedEvidenceVersion,'feed-provenance-1');
 assert.equal(s.readJsonl('snapshots')[0].feedEvidence,undefined);
 r.applyObservation('token',{market:{mint:'token',pairAddress:'pool',priceUsd:1},observedAt:T});assert.equal(r.candidates.get('token').feedEvidence,null);
});
