import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {Radar} from '../src/core/radar.js';
import {Storage} from '../src/core/storage.js';
import {readConfig} from '../src/config.js';
import {createEntry} from '../src/core/paper.js';
const mint='So11111111111111111111111111111111111111112';
function setup(t,config={}) {
 let now=Date.now();const initial=now;t.mock.method(Date,'now',()=>now);
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'radar-snapshots-'));const storage=new Storage(dir);
 t.after(()=>{storage.close();fs.rmSync(dir,{recursive:true,force:true});});
 const c={...readConfig({}),...config};let r=new Radar(c,storage);
 r.addCandidate({mint});
 const market={mint,pairAddress:'pool',pairCreatedAt:initial,priceUsd:1,liquidityUsd:100,txns:{m5:{buys:2,sells:1}},volume:{m5:100}};
 return {storage,market,get r(){return r;},get now(){return now;},
   advance(ms){now+=ms;},restart(){r=new Radar(c,storage);},
   async observe(change={}){await r.enrichOne(mint,{market:{...market,...change},observedAt:now});},
   snapshots(){return storage.readJsonl('snapshots',10000);}};
}

test('thin markets archive at five-minute intervals but every live price persists',async t=>{
 const x=setup(t);await x.observe();
 for(let i=1;i<=19;i++){x.advance(15000);await x.observe({priceUsd:i+1});}
 assert.equal(x.snapshots().length,1);assert.equal(x.r.candidates.get(mint).priceUsd,20);
 assert.equal(x.storage.loadCandidates()[mint].lastSnapshot.priceUsd,20);
 assert.equal(x.r.getHealth().snapshotArchive.skippedSinceRestart,19);
 x.advance(15000);await x.observe({priceUsd:21});assert.equal(x.snapshots().length,2);
});
test('liquid routine candidates archive each minute and promotion archives immediately',async t=>{
 const x=setup(t);await x.observe();x.advance(15000);await x.observe({liquidityUsd:20000});
 assert.equal(x.snapshots().length,2);assert.equal(x.snapshots().at(-1).archiveTier,'routine');
 for(let i=0;i<3;i++){x.advance(15000);await x.observe({liquidityUsd:20000});}
 assert.equal(x.snapshots().length,2);x.advance(15000);await x.observe({liquidityUsd:20000});assert.equal(x.snapshots().length,3);
});
test('acceleration uses immediately previous scan even when archive skips it',async t=>{
 const x=setup(t);await x.observe();x.advance(15000);await x.observe({volume:{m5:2000}});
 assert.ok(x.r.candidates.get(mint).scoreReasons.some(r=>r.reason==='5m volume is accelerating'));
 x.advance(15000);await x.observe({volume:{m5:2100}});
 assert.equal(x.snapshots().length,1);
 assert.ok(!x.r.candidates.get(mint).scoreReasons.some(r=>r.reason.includes('volume is accelerating')||r.reason.includes('volume is beginning to accelerate')));
 assert.equal(x.storage.loadCandidates()[mint].lastSnapshot.volume.m5,2100);
});
test('archive interval and latest live observation survive worker restart',async t=>{
 const x=setup(t);await x.observe();x.advance(15000);await x.observe({priceUsd:2});x.restart();
 assert.equal(x.r.candidates.get(mint).lastSnapshot.priceUsd,2);
 x.advance(15000);await x.observe({priceUsd:3});assert.equal(x.snapshots().length,1);
 x.advance(270000);await x.observe({priceUsd:4});assert.equal(x.snapshots().length,2);
});
test('paper positions keep every observation including the terminal 60m checkpoint',async t=>{
 const x=setup(t);x.r.addCandidate({mint,paperEntry:createEntry(x.market,x.now)});
 await x.observe();
 for(let i=0;i<240;i++){x.advance(15000);await x.observe({priceUsd:1+i/1000});}
 assert.equal(x.snapshots().length,241);
 const outcomes=x.storage.readJsonl('outcomes');assert.equal(outcomes.length,3);
 assert.equal(outcomes.find(o=>o.horizon==='60m').status,'observed');
 assert.equal(outcomes.find(o=>o.horizon==='60m').coverage,'sampled');
 x.advance(15000);await x.observe();assert.equal(x.snapshots().length,241);
});
test('qualified signals keep full cadence and preserve durable alert deduplication',async t=>{
 const x=setup(t,{notificationsEnabled:true});
 const strong={liquidityUsd:20000,txns:{m5:{buys:80,sells:30}},volume:{m5:15000},priceChange:{m5:25},marketCap:100000,socialCount:2};
 x.r.addCandidate({mint,mintAuthority:null,freezeAuthority:null,top10Pct:10,securityCheckedAt:x.now,organicScore:80,holderCount:300,jupiterCheckedAt:x.now});
 await x.observe(strong);assert.ok(x.r.candidates.get(mint).score>=82);
 for(let i=0;i<3;i++){x.advance(15000);await x.observe(strong);}
 assert.equal(x.snapshots().length,4);assert.equal(x.storage.readJsonl('alerts').length,1);
 assert.equal(x.storage.notificationStats().pending,1);
});
test('a pool change archives immediately while unavailable markets add no snapshot',async t=>{
 const x=setup(t);await x.observe();x.advance(15000);await x.observe({pairAddress:'new-pool'});
 assert.equal(x.snapshots().length,2);x.advance(15000);
 await x.r.enrichOne(mint,{market:null,observedAt:x.now});assert.equal(x.snapshots().length,2);
 assert.equal(x.r.getHealth().snapshotArchive.skippedSinceRestart,0);
});
test('existing archive remains intact and only snapshots expire under retention',async t=>{
 const x=setup(t);const old=x.now-8*86400000;
 for(const kind of ['snapshots','alerts','outcomes','exit-alerts'])x.storage.append(kind,{id:'old-'+kind,at:old});
 await x.observe();assert.equal(x.snapshots().length,2);
 x.storage.prune(x.now-7*86400000);assert.equal(x.snapshots().length,1);
 for(const kind of ['alerts','outcomes','exit-alerts'])assert.equal(x.storage.readJsonl(kind).length,1);
});
