import test from 'node:test';
import assert from 'node:assert/strict';
import {Radar} from '../src/core/radar.js';
import {readConfig} from '../src/config.js';
const T=1800000000000;
const mint=i=>'A'.repeat(28)+i.toString(16).replaceAll('0','z').padStart(6,'B');
const row=(i,patch={})=>({mint:mint(i),pairAddress:'pool'+i,firstSeenAt:T-60000,lastDiscoveryAt:T-10000,lastAttemptAt:T-15000,
 marketObservedAt:T,priceUsd:1,liquidityUsd:20000,volume:{m5:10000},txns:{m5:{buys:40,sells:20}},priceChange:{m5:15},...patch});
function radar(config={}){
 const state=new Map(),events=new Map();
 const storage={loadCandidates:()=>({}),getState:k=>state.get(k)||{},setState:(v,k)=>state.set(k,structuredClone(v)),saveCandidate:()=>{},deleteCandidate:()=>{},
  append:(kind,event)=>{const rows=events.get(kind)||[];rows.push(event);events.set(kind,rows);},queue:()=>{},notificationStats:()=>({}),
  events:kind=>events.get(kind)||[],readJsonl:(kind,n)=> (events.get(kind)||[]).slice(-n)};
 return new Radar({...readConfig({}),...config},storage);
}
function legacyBatch(r,now){
 const due=[...r.candidates.values()].filter(c=>!c.inactive&&now-(c.lastAttemptAt||0)>=15000);
 const order=(a,b)=>(a.lastAttemptAt||0)-(b.lastAttemptAt||0);
 const tracked=c=>c.paperEntry?.version==='price-v2'&&!c.paperEntry.horizons?.['60m'];
 const groups=[due.filter(tracked).sort(order),due.filter(c=>!tracked(c)&&!c.lastAttemptAt).sort(order),due.filter(c=>!tracked(c)&&c.lastAttemptAt).sort(order)];
 const result=[];while(result.length<30&&groups.some(g=>g.length)){const g=groups[r.marketGroupCursor++%3];if(g.length)result.push(g.shift());}return result;
}
function simulate(focused,t){
 let now=T;t.mock.method(Date,'now',()=>now);const r=radar();
 for(let i=0;i<1000;i++)r.candidates.set(mint(i),row(i,{liquidityUsd:i<35?20000:undefined,dexId:'pumpfun',priceChange:{m5:i<95?15:0},
  ...(i>=95&&i<108?{paperEntry:{version:'price-v2',pairAddress:'pool'+i,horizons:{},peakPrice:1}}:{})}));
 const first=new Map(),gaps=new Map();let attempts=0;
 for(let step=0;step<180;step++){
  if(step%27===0)for(let i=0;i<95;i++){const c=r.candidates.get(mint(i));if(c)c.lastDiscoveryAt=now;}
  const selected=focused?r.selectBatch(now):legacyBatch(r,now);
  for(const c of selected){
   attempts++;first.set(c.mint,first.get(c.mint)??now);
   if(c.lastMeasuredAt)gaps.set(c.mint,Math.max(gaps.get(c.mint)||0,now-c.lastMeasuredAt));
   c.lastAttemptAt=now;c.lastMeasuredAt=now;c.marketObservedAt=now;
   r.research.observe(c,c,{score:30},now,true);
  }
  for(let j=0;j<2;j++)r.addCandidate({mint:mint(1000+step*2+j)});
  now+=2200;
 }
 const relevant=[...r.candidates.values()].filter(c=>c.liquidityUsd>=5000);
 const ready=relevant.filter(c=>r.research.describe(c.mint,now)?.metrics?.ready&&r.research.describe(c.mint,now)?.stage!=='data unavailable').length;
 return {r,ready,retainedRelevant:relevant.length,attempts,first,gaps,now};
}
test('realistic queue timing reproduces old gaps and focused revisits restore histories',t=>{
 const before=simulate(false,t),after=simulate(true,t);
 assert.equal(before.retainedRelevant,35);assert.equal(before.ready,0);assert.equal(after.retainedRelevant,35);assert.equal(after.ready,35);
 assert.equal(after.r.researchFocus.size,60);assert.ok(after.attempts<=180*30);
 for(let i=0;i<35;i++)assert.ok(after.gaps.get(mint(i))<=45000);
 assert.ok(after.first.has(mint(900)));assert.ok(after.first.has(mint(1300)));
 const pending=[...after.r.candidates.values()].filter(c=>!c.lastAttemptAt);
 assert.ok(pending.length<=4);assert.equal(after.r.evictedBeforeAttempt||0,0);
});
test('focus is capped, stable, rejects adverse or weak markets and releases stale rows',()=>{
 const r=radar({researchFocusLimit:3});
 const rows=[row(0),row(1),row(2,{liquidityUsd:undefined,dexId:'pumpfun'}),row(3,{top10Pct:80}),row(4,{liquidityUsd:undefined,dexId:'pumpfun',priceChange:{m5:0}})];
 r.candidates=new Map(rows.map(c=>[c.mint,c]));r.selectBatch(T);
 assert.deepEqual([...r.researchFocus],[mint(0),mint(1),mint(2)]);
 r.selectBatch(T+1000);assert.equal(r.researchFocus.size,3);
 rows[0].stale=true;r.selectBatch(T+2000);assert.ok(!r.researchFocus.has(mint(0)));
 r.selectBatch(T+130000);assert.equal(r.researchFocus.size,0);
});
test('pending research checkpoints take priority over new focus admissions',()=>{
 const r=radar({researchFocusLimit:1}),a=row(0),b=row(1,{liquidityUsd:undefined,priceChange:{m5:-30}});
 r.candidates=new Map([[a.mint,a],[b.mint,b]]);r.research.baseline(b,T);r.selectBatch(T);
 assert.deepEqual([...r.researchFocus],[b.mint]);
});
test('single-slot scheduling serves paper, discovery, focus and broad queue',()=>{
 const r=radar({batchSize:1}),paper=row(0,{paperEntry:{version:'price-v2',horizons:{}}}),fresh=row(1,{lastAttemptAt:undefined}),focus=row(2),broad=row(3,{liquidityUsd:100});
 r.candidates=new Map([paper,fresh,focus,broad].map(c=>[c.mint,c]));
 const selected=Array.from({length:4},()=>r.selectBatch(T)[0].mint);assert.equal(new Set(selected).size,4);
});
test('disabling research removes focus allocation and protection',()=>{
 const r=radar({researchEnabled:false});r.candidates=new Map([[mint(0),row(0)]]);r.selectBatch(T);assert.equal(r.researchFocus.size,0);
});
test('health reports focus readiness and current cohort excludes older research entries',()=>{
 const r=radar();r.candidates=new Map([[mint(0),row(0)]]);r.selectBatch(T);
 r.storage.append('research-entries',{id:'old',version:'research-0.2.6',cohort:'baseline',at:T-1000,mint:mint(0)});
 const s=r.getStats();assert.equal(s.research.version,'research-0.2.9');assert.equal(s.research.summary.baseline.entries,0);
 assert.equal(s.research.summaryAllRetained.baseline.entries,1);assert.equal(s.health.research.focus.selected,1);assert.equal(s.health.research.focus.ready,0);
});

test('focus protection leaves admission space in small candidate queues',()=>{
 const r=radar({maxCandidates:10});for(let i=0;i<10;i++)r.candidates.set(mint(i),row(i));r.selectBatch(T);
 assert.equal(r.researchFocus.size,2);assert.ok(r.addCandidate({mint:mint(11)}));
 assert.ok(r.candidates.has(mint(0)));assert.ok(r.candidates.has(mint(1)));assert.equal(r.candidates.size,10);
});
