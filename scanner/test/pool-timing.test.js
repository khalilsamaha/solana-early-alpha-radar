import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
import {Storage} from '../src/core/storage.js';import {Research} from '../src/core/research.js';
import {EXIT_PROTOCOL,PATH_VERSION} from '../src/core/fast-shadow.js';
const T=1800000000000,config={researchEnabled:true,securityTtlMs:300000,researchNotifications:false};
const candidate=(ms,extra={})=>({mint:'token',priceUsd:1+ms/100000,pairAddress:'pool',marketObservedAt:T+ms,marketAttemptStatus:'observed',liquidityUsd:20000,txns:{m5:{buys:70+ms/1000,sells:30}},volume:{m5:5000+ms/10},mintAuthority:null,freezeAuthority:null,securityCheckedAt:T,top10Pct:10,...extra});
function setup(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'pool-test-'));const storage=new Storage(dir);t.after(()=>{storage.close();fs.rmSync(dir,{recursive:true,force:true});});const r=new Research(config,storage);for(const ms of [0,15000,30000]){const c=candidate(ms);r.observe(c,c,{},T+ms,true);}return {r,storage};}
test('alternate checkpoint preserves original missing outcome and separate pool price',t=>{
 const {r,storage}=setup(t);for(const ms of [45000,60000,75000])r.fast.checkpoint('token',candidate(ms,{pairAddress:'alternate'}),T+ms,true);
 r.fast.sweep(T+90001);const o=storage.readJsonl('fast-shadow-outcomes')[0];
 assert.equal(o.status,'missing');assert.equal(o.pairAddress,'pool');assert.equal(o.returnPct,undefined);
 assert.equal(o.pathEvidence.alternateAtCheckpoint.pairAddress,'alternate');assert.equal(o.pathEvidence.alternateAtCheckpoint.sampleAt,T+60000);
 assert.equal(o.pathEvidence.firstAlternate.sampleAt,T+45000);assert.equal(o.pathEvidence.version,PATH_VERSION);
});
test('path is bounded, invalid observations skipped, sweeps never invent observations or writes',t=>{
 const {r,storage}=setup(t);const before=storage.readJsonl('fast-shadow-outcomes').length;
 for(let ms=31000;ms<59000;ms+=1000)r.fast.checkpoint('token',candidate(ms),T+ms,true);
 const p=r.fast.states.get('token').position;assert.equal(p.pathEvidence.points.length,8);assert.ok(p.pathEvidence.droppedPoints>0);
 const rows=JSON.stringify(p.pathEvidence.points);
 r.fast.checkpoint('token',candidate(59000,{marketObservedAt:T+90000}),T+59000,true);
 r.fast.checkpoint('token',candidate(59000,{marketAttemptStatus:'error'}),T+59000,true);
 r.fast.checkpoint('token',candidate(59000,{mint:'other'}),T+59000,true);
 r.fast.sweep(T+59000);assert.equal(JSON.stringify(p.pathEvidence.points),rows);assert.equal(storage.readJsonl('fast-shadow-outcomes').length,before);
});
test('original-pool recovery retains separate alternate evidence and actual checkpoint price',t=>{
 const {r,storage}=setup(t);r.fast.checkpoint('token',candidate(60000,{pairAddress:'alternate'}),T+60000,true);r.fast.checkpoint('token',candidate(75000),T+75000,true);
 const o=storage.readJsonl('fast-shadow-outcomes')[0];assert.equal(o.status,'observed');assert.equal(o.priceUsd,1.75);assert.equal(o.sampleAt,T+75000);
 assert.equal(o.pathEvidence.alternateAtCheckpoint.priceUsd,1.6);assert.equal(o.pathEvidence.points.at(-1).pairAddress,'pool');
});
test('restart discards in-memory trajectory and labels fresh evidence partial',t=>{
 const {r,storage}=setup(t);r.fast.checkpoint('token',candidate(60000),T+60000,true);
 const restart=new Research(config,storage);restart.state('token');restart.fast.checkpoint('token',candidate(90000),T+90000,true);
 const o=storage.readJsonl('fast-shadow-outcomes').at(-1);assert.equal(o.coverage,'gapped');assert.equal(o.pathEvidence.partialHistory,true);assert.equal(o.pathEvidence.points.length,1);
});
test('fixed exit registration persists and does not modify old entry rules or notifications',t=>{
 const {r,storage}=setup(t);const reg=storage.getState('fixed-short-exits-registration');assert.deepEqual(reg,{...EXIT_PROTOCOL,registeredAt:T+30000});
 const restart=new Research(config,storage);restart.fast.register(T+400000);assert.deepEqual(storage.getState('fixed-short-exits-registration'),reg);
 assert.equal(r.fast.stats().fixedExitProtocol,EXIT_PROTOCOL.id);assert.deepEqual(storage.notificationStats(),{});assert.equal(storage.readJsonl('fast-shadow-entries').length,1);
});
test('late alternate response cannot be labelled a timely checkpoint',t=>{
 const {r,storage}=setup(t);r.fast.checkpoint('token',candidate(90000,{pairAddress:'alternate'}),T+90001,true);
 const o=storage.readJsonl('fast-shadow-outcomes')[0];assert.equal(o.pathEvidence.alternateAtCheckpoint,null);assert.equal(o.status,'missing');
});
