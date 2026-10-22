import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
import {Storage} from '../src/core/storage.js';import {Research} from '../src/core/research.js';import {MomentumHistory} from '../src/core/momentum.js';
import {observationQuality} from '../src/core/observation-quality.js';import {FAST_RULE} from '../src/core/fast-shadow.js';
const T=1800000000000,mint='So11111111111111111111111111111111111111112';
const config={researchEnabled:true,securityTtlMs:300000,researchNotifications:false};
const token=(i,patch={})=>({mint,symbol:'TEST',priceUsd:1+i*.08,pairAddress:'pool',marketObservedAt:T+i*15000,
 liquidityUsd:20000,txns:{m5:{buys:70+i*8,sells:30+i*3}},volume:{m5:5000+i*1000},mintAuthority:null,freezeAuthority:null,
 securityCheckedAt:T,top10Pct:10,score:75,...patch});
function setup(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'fast-test-')),storage=new Storage(dir);t.after(()=>{storage.close();fs.rmSync(dir,{recursive:true,force:true});});return {storage,r:new Research(config,storage)};}
function feed(r,i,patch={}){const c=token(i,patch);return r.observe(c,c,{score:75},c.marketObservedAt,true);}
test('quality distinguishes initial, repeated, price-only and value-only changes without freshness claims',()=>{
 const h=new MomentumHistory();h.observe(token(0),T);assert.equal(observationQuality(h,T).state,'first observation');
 h.observe(token(0),T+15000);let q=observationQuality(h,T+16000);assert.equal(q.responseAgeMs,1000);assert.equal(q.priceUnchangedForAtLeastMs,16000);assert.equal(q.lastPriceChangeAt,null);
 h.observe(token(2,{priceUsd:1}),T+30000);q=observationQuality(h,T+30000);assert.equal(q.state,'reported values changed');assert.equal(q.consecutiveRepeatedPrices,2);assert.equal(q.underlyingFreshness,'unknown');
 assert.equal(observationQuality(h,T+90000).responseRecent,false);
});
test('fast track fires at 30 seconds, existing early track at 60 and linked lead is explicit',t=>{
 const {r,storage}=setup(t);for(let i=0;i<=4;i++)feed(r,i);
 const f=storage.readJsonl('fast-shadow-entries'),e=storage.readJsonl('research-entries');
 assert.equal(f.length,1);assert.equal(f[0].entryContext.derived.transactions5m,122);assert.equal(f[0].entryContext.clocks.securityCheckedAt.at,T);assert.equal(f[0].at,T+30000);assert.equal(e[0].at,T+60000);
 assert.equal(storage.readJsonl('fast-shadow-links')[0].leadMs,30000);assert.deepEqual(storage.notificationStats(),{});
 assert.equal(r.pending(mint),true);assert.equal(storage.getState('fast-shadow-registration').id,FAST_RULE.id);
});
test('fast-only tracking gets a bounded focus tier without creating a baseline paper position',t=>{
 const {r}=setup(t);for(let i=0;i<=2;i++)feed(r,i);
 assert.equal(r.fast.stats().pending,1);assert.equal(r.pending(mint),false);assert.equal(r.focusTier(token(2),T+30000),0.5);assert.equal(r.trackingPending(mint),true);
});
test('one initial plus one changed transition cannot create early history',t=>{
 const {r,storage}=setup(t);feed(r,0);feed(r,1,{...token(0),marketObservedAt:T+15000});feed(r,2);
 assert.equal(storage.readJsonl('fast-shadow-entries').length,0);
});
test('negative latest interval and severe flags do not pass fast rule',t=>{
 const {r,storage}=setup(t);feed(r,0);feed(r,1,{priceUsd:1.5});feed(r,2,{priceUsd:1.3});
 assert.equal(storage.readJsonl('fast-shadow-entries').length,0);feed(r,3,{top10Pct:70});assert.equal(storage.readJsonl('fast-shadow-entries').length,0);
});
test('unknown pump liquidity remains explicit and does not become a security pass',t=>{
 const {r,storage}=setup(t);for(let i=0;i<=2;i++)feed(r,i,{liquidityUsd:undefined,dexId:'pumpfun',securityCheckedAt:undefined,mintAuthority:undefined});
 const f=storage.readJsonl('fast-shadow-entries')[0];assert.equal(f.liquidityUsd,null);assert.equal(f.security.status,'expired or unavailable');
});
test('all checkpoints recorded once with real provider timestamps and no added notifications',t=>{
 const {r,storage}=setup(t);for(let i=0;i<=23;i++)feed(r,i);
 const outcomes=storage.readJsonl('fast-shadow-outcomes');assert.equal(outcomes.length,4);assert.ok(outcomes.every(o=>o.status==='observed'&&o.coverage==='sampled'));
 assert.equal(storage.readJsonl('fast-shadow-entries').length,1);assert.deepEqual(storage.notificationStats(),{});
});
test('missing observations, pool switches and eviction never generate synthetic returns',t=>{
 const {r,storage}=setup(t);for(let i=0;i<=2;i++)feed(r,i);feed(r,4,{pairAddress:'other'});r.drop(mint,T+70000);
 const rows=storage.readJsonl('fast-shadow-outcomes');assert.equal(rows.length,4);assert.ok(rows.every(o=>o.status==='missing'&&o.returnPct===undefined));
});
test('restart preserves cooldown and flags unfinished paths as gapped',t=>{
 const {r,storage}=setup(t);for(let i=0;i<=2;i++)feed(r,i);const r2=new Research(config,storage);for(let i=3;i<=8;i++)feed(r2,i);
 assert.equal(storage.readJsonl('fast-shadow-entries').length,1);assert.ok(storage.readJsonl('fast-shadow-outcomes').every(o=>o.coverage==='gapped'));
});
test('sweep expires a shadow position without market requests',t=>{
 const {r,storage}=setup(t);for(let i=0;i<=2;i++)feed(r,i);r.sweep(T+400000);
 assert.equal(storage.readJsonl('fast-shadow-outcomes').length,4);assert.equal(r.fast.stats().pending,0);
});
test('retention prunes fast evidence and state, preserves registration and baseline',t=>{
 const {storage}=setup(t);for(const kind of ['fast-shadow-entries','fast-shadow-outcomes','fast-shadow-links'])storage.append(kind,{id:kind,at:T});
 storage.setState({updatedAt:T},'fast-shadow:old');storage.setState({id:FAST_RULE.id,registeredAt:T},'fast-shadow-registration');storage.append('alerts',{id:'baseline',at:T});
 storage.prune(T+1);assert.deepEqual(storage.getState('fast-shadow:old'),{});assert.equal(storage.getState('fast-shadow-registration').id,FAST_RULE.id);assert.equal(storage.readJsonl('alerts').length,1);
 for(const kind of ['fast-shadow-entries','fast-shadow-outcomes','fast-shadow-links'])assert.equal(storage.readJsonl(kind).length,0);
});
test('quality counters reset with pool and warmup, future timestamp never fresh',()=>{
 const h=new MomentumHistory();for(let i=0;i<4;i++)h.observe(token(i),T+i*15000);h.observe(token(4,{pairAddress:'other'}),T+60000);
 const q=observationQuality(h,T+60000);assert.equal(q.sampleCount,1);assert.equal(q.lastPriceChangeAt,null);assert.equal(q.historyResetReason,'pool changed');
 assert.equal(observationQuality(h,T+59000).responseRecent,false);
});

test('fast tracking admission is bounded, recorded, survives restart and expires',t=>{
 const {r,storage}=setup(t);
 for(let n=0;n<13;n++)for(let i=0;i<=2;i++)feed(r,i,{mint:'token'+n});
 const entries=storage.readJsonl('fast-shadow-entries');assert.equal(entries.length,13);
 assert.equal(entries.filter(e=>e.followup.admitted).length,12);assert.equal(entries[12].followup.reason,'tracking capacity full');
 assert.equal(r.trackingPending('token12'),false);assert.equal(r.fast.stats().trackingActive,12);
 const restarted=new Research(config,storage);for(let n=0;n<13;n++)restarted.state('token'+n);
 assert.equal(restarted.fast.stats().trackingActive,12);assert.equal(restarted.fast.states.get('token0').position.gapped,true);
 restarted.sweep(T+400000);assert.equal(restarted.fast.stats().trackingActive,0);
 assert.equal(storage.readJsonl('fast-shadow-outcomes').length,52);
 assert.equal(storage.getState('fast-followup-registration').id,'fast-followup-1');
});
test('linked entry records its own observed price and timestamp without modifying old entry',t=>{
 const {r,storage}=setup(t);for(let i=0;i<=4;i++)feed(r,i);
 const entry=storage.readJsonl('fast-shadow-entries')[0],link=storage.readJsonl('fast-shadow-links')[0];
 assert.equal(entry.priceUsd,token(2).priceUsd);assert.equal(link.comparisonPriceUsd,token(4).priceUsd);
 assert.equal(link.comparisonObservedAt,T+60000);assert.equal(link.followup.policy,'fast-followup-1');
});
