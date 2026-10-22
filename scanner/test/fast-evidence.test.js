import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
import {Storage} from '../src/core/storage.js';import {Research} from '../src/core/research.js';
import {evaluateEntryShadows,EVIDENCE_VERSION} from '../src/core/fast-shadow.js';
const T=1800000000000,mint='token',config={researchEnabled:true,securityTtlMs:300000,researchNotifications:false};
const c=(ms,extra={})=>({mint,priceUsd:1+ms/100000,pairAddress:'pool',marketObservedAt:T+ms,marketAttemptStatus:'observed',liquidityUsd:20000,txns:{m5:{buys:70+ms/1000,sells:30}},volume:{m5:5000+ms/10},mintAuthority:null,freezeAuthority:null,securityCheckedAt:T,top10Pct:10,...extra});
function setup(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'evidence-test-'));const storage=new Storage(dir);t.after(()=>{storage.close();fs.rmSync(dir,{recursive:true,force:true});});const r=new Research(config,storage);for(const ms of [0,15000,30000]){const row=c(ms);r.observe(row,row,{},T+ms,true);}return {r,storage};}
test('shadow registration and immutable entry features persist without admission or notification changes',t=>{
 const {r,storage}=setup(t),e=storage.readJsonl('fast-shadow-entries')[0],reg=storage.getState('fast-evidence-registration');
 assert.equal(reg.id,EVIDENCE_VERSION);assert.equal(e.shadowEvaluation.registeredAt,reg.registeredAt);assert.equal(e.shadowEvaluation.featureAt,e.at);
 assert.equal(e.shadowEvaluation.groups['known-liquidity-5000-v1'],'selected');assert.equal(r.fast.stats().trackingAdmissionsSinceRestart,1);assert.deepEqual(storage.notificationStats(),{});
 const before=JSON.stringify(e);r.fast.checkpoint(mint,c(60000,{liquidityUsd:null}),T+60000,true);assert.equal(JSON.stringify(storage.readJsonl('fast-shadow-entries')[0]),before);
 const again=new Research(config,storage);again.fast.register(T+999999);assert.deepEqual(storage.getState('fast-evidence-registration'),reg);
});
test('unknown, zero and excessive entry momentum stay distinct',()=>{
 assert.deepEqual(evaluateEntryShadows({liquidityUsd:null,return30sPct:51}),{'known-liquidity-5000-v1':'unknown','return30-at-most-50-v1':'excluded'});
 assert.deepEqual(evaluateEntryShadows({liquidityUsd:0,return30sPct:0}),{'known-liquidity-5000-v1':'excluded','return30-at-most-50-v1':'selected'});
 assert.equal(evaluateEntryShadows({liquidityUsd:5000,return30sPct:50})['return30-at-most-50-v1'],'selected');
});
test('no-attempt windows do not fabricate returns or provider failures',t=>{
 const {r,storage}=setup(t);r.fast.sweep(T+120001);const o=storage.readJsonl('fast-shadow-outcomes')[0];
 assert.equal(o.reasonCode,'no-attempt-in-checkpoint-window');assert.equal(o.diagnostics.window.attempts,0);assert.equal(o.returnPct,undefined);assert.equal(o.diagnostics.partialHistory,false);
});
test('failed and empty attempts retain bounded per-window counts',t=>{
 const {r,storage}=setup(t);for(const [ms,status] of [[60000,'error'],[75000,'no-usable-market']])r.fast.checkpoint(mint,c(ms,{marketAttemptStatus:status}),T+ms,false);
 r.fast.sweep(T+90001);const o=storage.readJsonl('fast-shadow-outcomes')[0];assert.equal(o.diagnostics.window.attempts,2);
 assert.deepEqual(o.diagnostics.window.counts,{'provider-error':1,'no-usable-market':1});assert.equal(o.reasonCode,'no-timely-original-pool-observation');assert.equal(o.returnPct,undefined);
});
test('pool switch evidence permits recovery only on the original pool',t=>{
 const {r,storage}=setup(t);r.fast.checkpoint(mint,c(60000,{pairAddress:'other'}),T+60000,true);r.fast.checkpoint(mint,c(75000),T+75000,true);
 const o=storage.readJsonl('fast-shadow-outcomes')[0];assert.equal(o.status,'observed');assert.equal(o.pairAddress,'pool');assert.equal(o.diagnostics.window.counts['different-pool'],1);assert.equal(o.diagnostics.window.counts['same-pool'],1);assert.equal(o.reasonCode,null);
});
test('eviction and restart do not reconstruct diagnostic history',t=>{
 const {storage}=setup(t);const restarted=new Research(config,storage);restarted.state(mint);restarted.fast.sweep(T+120001);
 const rows=storage.readJsonl('fast-shadow-outcomes');assert.equal(rows[0].reasonCode,'restart-interrupted');assert.equal(rows[0].diagnostics.partialHistory,true);
 restarted.fast.drop(mint,T+130000);const last=storage.readJsonl('fast-shadow-outcomes').at(-1);assert.equal(last.reasonCode,'candidate-left-queue');assert.equal(last.returnPct,undefined);
});
test('diagnostics preserve checkpoint clocks, prices and terminal state',t=>{
 const {r,storage}=setup(t);for(let ms=45000;ms<=345000;ms+=15000)r.fast.checkpoint(mint,c(ms),T+ms,true);
 const rows=storage.readJsonl('fast-shadow-outcomes');assert.equal(rows.length,4);assert.deepEqual(rows.map(o=>o.sampleAt),[60000,90000,150000,330000].map(ms=>T+ms));
 assert.ok(rows.every(o=>o.status==='observed'&&o.coverage==='sampled'));assert.equal(r.fast.stats().pending,0);assert.ok(rows.every(o=>Object.keys(o.diagnostics.window.counts).length<=5));
});
