import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {Storage} from '../src/core/storage.js';
import {Research,RESEARCH_HORIZONS} from '../src/core/research.js';
import {observeContinuity,summarizeContinuity} from '../src/core/continuity.js';
import {readConfig} from '../src/config.js';
const T=1800000000000,mint='So11111111111111111111111111111111111111112';
const entry=()=>({mint,pairAddress:'original',priceUsd:1,at:T});
const market=(offset,extra={})=>({mint,pairAddress:'alternate',priceUsd:2,marketObservedAt:T+offset,liquidityUsd:10000,txns:{m5:{buys:30,sells:10}},...extra});
function setup(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'continuity-'));const storage=new Storage(dir);t.after(()=>{storage.close();fs.rmSync(dir,{recursive:true,force:true});});const r=new Research(readConfig({}),storage);r.baseline({...entry(),marketObservedAt:T},T);return {r,storage};}
test('alternate pool requires changing observations separated by 15 seconds',()=>{
 const p=entry();assert.equal(observeContinuity(p,market(15000),T+15000,true),null);
 assert.equal(observeContinuity(p,market(20000,{priceUsd:2.1}),T+20000,true),null);
 const result=observeContinuity(p,market(30000,{priceUsd:2.2}),T+30000,true);
 assert.equal(result.basis,'alternate-pool');assert.equal(result.migrationVerified,false);assert.ok(Math.abs(result.returnPct-120)<1e-9);
});
test('unchanged, unknown-liquidity, wrong-mint and stale alternate prices cannot qualify',()=>{
 for(const extra of [{},{liquidityUsd:undefined},{mint:'another-mint'},{marketObservedAt:T-50000},{txns:{m5:{buys:0,sells:0}}}]){
  const p=entry();observeContinuity(p,market(15000,extra),T+15000,true);
  assert.equal(observeContinuity(p,market(30000,extra),T+30000,true),null);
 }
});
test('duplicates, gaps, pool oscillation and provider failures reset confirmation',()=>{
 const p=entry();observeContinuity(p,market(15000),T+15000,true);
 assert.equal(observeContinuity(p,market(15000,{priceUsd:3}),T+30000,true),null);
 assert.equal(observeContinuity(p,market(61000,{priceUsd:3}),T+61000,true),null);
 assert.equal(observeContinuity(p,market(76000,{pairAddress:'third',priceUsd:3}),T+76000,true),null);
 observeContinuity(p,market(80000),T+80000,false);
 assert.equal(observeContinuity(p,market(91000,{pairAddress:'third',priceUsd:4}),T+91000,true),null);
});
test('qualified token follow-up is retained beside a missing original-pool checkpoint',t=>{
 const {r,storage}=setup(t);
 for(const [at,price] of [[15000,2],[30000,2.2]]) {
  const c=market(at,{priceUsd:price});r.observe(c,c,{score:0},T+at,true);r.sweep(T+at+1000);
 }
 r.sweep(T+60001);
 const row=storage.readJsonl('research-outcomes').find(x=>x.horizon==='30s');
 assert.equal(row.status,'missing');assert.equal(row.reasonCode,'different-pool');assert.equal(row.returnPct,undefined);
 assert.equal(row.tokenFollowup.status,'observed');assert.equal(row.tokenFollowup.basis,'alternate-pool');assert.equal(row.tokenFollowup.coverage,'sampled');
 const s=summarizeContinuity(storage.readJsonl('research-entries'),storage.readJsonl('research-outcomes'),RESEARCH_HORIZONS,T+60001,30000);
 assert.equal(s.baseline.horizons['30s'].alternatePool,1);assert.equal(s.baseline.horizons['30s'].missing,0);
 const before=JSON.stringify(row);r.observe(market(70000,{priceUsd:100}),{}, {score:0},T+70000,true);
 assert.equal(JSON.stringify(storage.readJsonl('research-outcomes').find(x=>x.id===row.id)),before);
});
test('restart cannot reuse pre-restart confirmation or hide observation gaps',t=>{
 const {r,storage}=setup(t),c=market(15000);r.observe(c,c,{score:0},T+15000,true);
 r.persist(mint,r.state(mint),T+15000);
 const next=new Research(readConfig({}),storage);
 for(const [at,price] of [[30000,2.2],[45000,2.3]]){const c=market(at,{priceUsd:price});next.observe(c,c,{score:0},T+at,true);}
 next.sweep(T+60001);
 const o=storage.readJsonl('research-outcomes').find(x=>x.horizon==='30s');
 assert.equal(o.tokenFollowup.sampleAt,T+45000);assert.equal(o.tokenFollowup.coverage,'gapped');
 const s=summarizeContinuity(storage.readJsonl('research-entries'),storage.readJsonl('research-outcomes'),RESEARCH_HORIZONS,T+60001,30000);
 assert.equal(s.baseline.horizons['30s'].observed,0);assert.equal(s.baseline.horizons['30s'].gapped,1);
});
test('pool change starts fresh momentum history and records a dashboard event without notification',t=>{
 const {r,storage}=setup(t),first=market(0,{pairAddress:'original',priceUsd:1});r.observe(first,first,{score:0},T,true);
 const c=market(15000);const summary=r.observe(c,c,{score:0},T+15000,true);
 assert.equal(summary.metrics.resetReason,'pool changed');assert.equal(summary.metrics.sampleCount,1);
 assert.equal(summary.poolChange.from,'original');assert.equal(summary.poolChange.to,'alternate');
 assert.equal(storage.readJsonl('research-events')[0].event,'pool changed');
 assert.deepEqual(storage.notificationStats(),{});
});
