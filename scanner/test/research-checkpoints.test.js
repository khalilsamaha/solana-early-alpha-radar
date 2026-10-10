import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {Radar} from '../src/core/radar.js';
import {Storage} from '../src/core/storage.js';
import {readConfig} from '../src/config.js';
import {summarizeResearch} from '../src/core/research.js';
const T=1800000000000;
const mint='So11111111111111111111111111111111111111112';
const other='A'.repeat(32);
function setup(t,extra={}){
 let now=T;t.mock.method(Date,'now',()=>now);
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'checkpoint-'));
 const storage=new Storage(dir);t.after(()=>{storage.close();fs.rmSync(dir,{recursive:true,force:true});});
 const radar=new Radar({...readConfig({}),notificationsEnabled:false,...extra},storage);
 const candidate={mint,pairAddress:'entry-pool',priceUsd:1,marketObservedAt:T,lastAttemptAt:T-15000,firstSeenAt:T,score:0};
 radar.candidates.set(mint,candidate);radar.research.baseline(candidate,T);
 return {radar,storage,candidate,time:value=>{now=T+value;},outcomes:()=>storage.readJsonl('research-outcomes')};
}
test('pending checkpoints bypass old backoff but retain minimum revisit and broad-queue backoff',t=>{
 const x=setup(t);x.candidate.nextMarketAttemptAt=T+300000;
 x.radar.candidates.set(other,{...x.candidate,mint:other});
 assert.deepEqual(x.radar.selectBatch(T).map(c=>c.mint),[mint]);
 x.candidate.lastAttemptAt=T;
 assert.equal(x.radar.selectBatch(T+14999).length,0);
 assert.deepEqual(x.radar.selectBatch(T+15000).map(c=>c.mint),[mint]);
 x.radar.research.sweep(T+330001);
 assert.equal(x.radar.research.pending(mint),false);
 x.candidate.nextMarketAttemptAt=T+500000;
 assert.ok(!x.radar.selectBatch(T+330002).some(c=>c.mint===mint));
});
test('an empty response during research can recover in the checkpoint window without changing its pool',async t=>{
 const x=setup(t);x.time(15000);
 await x.radar.enrichOne(mint,{market:null,observedAt:T+15000});
 assert.equal(x.radar.candidates.get(mint).nextMarketAttemptAt,T+30000);
 x.time(30000);assert.equal(x.radar.selectBatch()[0].mint,mint);
 await x.radar.enrichOne(mint,{market:{mint,pairAddress:'entry-pool',priceUsd:1.2},observedAt:T+30000});
 const row=x.outcomes()[0];assert.equal(row.status,'observed');assert.equal(row.coverage,'sampled');
 assert.ok(Math.abs(row.returnPct-20)<1e-9);assert.equal(row.observationBasis,'provider-response-time');
 assert.equal(row.evidence.entryPool,'entry-pool');
});
test('pending research survives candidate age cutoff only until its checkpoints expire',async t=>{
 const x=setup(t);x.candidate.firstSeenAt=T-24*3600000;x.candidate.inactive=true;
 assert.equal(x.radar.selectBatch(T)[0].mint,mint);
 assert.ok(x.radar.researchFocus.has(mint));x.time(30000);
 await x.radar.enrichOne(mint,{market:{mint,pairAddress:'entry-pool',priceUsd:1.1},observedAt:T+30000});
 assert.equal(x.outcomes()[0].status,'observed');
 assert.equal(x.radar.candidates.get(mint).inactive,true);
 assert.equal(x.radar.selectBatch(T+45000)[0].mint,mint);
 x.time(330001);x.radar.research.sweep();
 await x.radar.enrichOne(mint,{market:null,observedAt:T+330001});
 assert.equal(x.radar.candidates.get(mint).inactive,true);
 assert.equal(x.radar.selectBatch(T+360000).length,0);
});
test('a different current pool never fills an original-pool checkpoint and the missing reason is retained',t=>{
 const x=setup(t),c={...x.candidate,pairAddress:'new-pool',priceUsd:5,marketObservedAt:T+30000};
 x.radar.research.observe(c,c,{score:0},T+30000,true);
 assert.equal(x.outcomes().length,0);
 x.radar.research.sweep(T+60001);
 const o=x.outcomes()[0];assert.equal(o.status,'missing');assert.equal(o.reasonCode,'different-pool');
 assert.equal(o.coverage,'gapped');assert.equal(o.evidence.lastAttempt.pairAddress,'new-pool');
 assert.equal(o.evidence.lastSamePoolAt,T);assert.equal(o.priceUsd,undefined);assert.equal(o.returnPct,undefined);
 const summary=summarizeResearch(x.storage.readJsonl('research-entries'),x.outcomes(),T+60001);
 assert.deepEqual(summary.baseline.horizons['30s'].missingByReason,{'different-pool':1});
 assert.equal(summary.baseline.horizons['30s'].medianReturnPct,null);
});
test('empty, failed and stale attempts remain distinguishable without fabricating price evidence',async t=>{
 for(const [status,code] of [['no-usable-market','no-usable-market'],['error','provider-error'],['observed','stale-or-invalid']]){
  await t.test(status,t=>{
   const x=setup(t),c={...x.candidate,marketAttemptStatus:status};
   x.radar.research.observe(c,c,{score:0},T+40000,false);
   x.radar.research.sweep(T+60001);const o=x.outcomes()[0];
   assert.equal(o.reasonCode,code);assert.equal(o.evidence.lastAttempt.pairAddress,undefined);
   assert.equal(o.coverage,'gapped');assert.equal(o.returnPct,undefined);
  });
 }
});
test('a stalled scanner records no-observation and a gap; late data cannot rewrite it',t=>{
 const x=setup(t);x.radar.research.sweep(T+60001);const before=x.outcomes()[0];
 assert.equal(before.reasonCode,'no-observation');assert.equal(before.coverage,'gapped');
 const c={...x.candidate,priceUsd:100,marketObservedAt:T+70000};
 x.radar.research.observe(c,c,{score:0},T+70000,true);
 assert.deepEqual(x.outcomes().find(o=>o.id===before.id),before);
});
test('completed deadlines and disabled research do not keep candidates eligible indefinitely',t=>{
 const x=setup(t);x.candidate.nextMarketAttemptAt=T+300000;x.radar.config.researchEnabled=false;
 assert.equal(x.radar.research.pending(mint),false);assert.equal(x.radar.selectBatch(T).length,0);
});
