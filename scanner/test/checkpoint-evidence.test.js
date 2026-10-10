import test from 'node:test';
import assert from 'node:assert/strict';
import {Research} from '../src/core/research.js';
import {readConfig} from '../src/config.js';
const T=1800000000000;
function setup(){const events=[];const storage={getState:()=>({}),setState:()=>{},append:(kind,row)=>events.push({kind,row})};return {events,r:new Research({...readConfig({}),notificationsEnabled:false},storage)};}
const mint='So11111111111111111111111111111111111111112';
function token(i,pair='pool'){return {mint,pairAddress:pair,priceUsd:1+i*.01,marketObservedAt:T+i*16000,liquidityUsd:10000,txns:{m5:{buys:1,sells:1}},volume:{m5:100},firstSeenAt:T,launchAt:T};}
test('five-minute checkpoint keeps continuous evidence through delayed two-minute exits',()=>{
 const {r,events}=setup();const c=token(0);r.observe(c,c,{score:20},T,true);r.baseline(c,T);
 for(let i=1;i<=20;i++){const c=token(i);r.observe(c,c,{score:20},c.marketObservedAt,true);}
 const row=events.find(e=>e.kind==='research-outcomes'&&e.row.horizon==='5m').row;
 assert.equal(row.evidenceHistory.maxSamples,24);
 const samples=row.evidenceHistory.samples;
 assert.ok(samples.length>=18&&samples.length<=24);
 assert.ok(samples.some(p=>p.at===T+144000));
 assert.ok(samples.some(p=>p.at===T+160000));
 assert.ok(samples.every(p=>p.at<row.sampleAt));
 for(let i=1;i<samples.length;i++)assert.equal(samples[i].at-samples[i-1].at,16000);
 assert.equal(row.returnPct,(token(19).priceUsd/c.priceUsd-1)*100);
});
test('larger checkpoint evidence still never crosses pool changes',()=>{
 const {r,events}=setup();const c=token(0);r.observe(c,c,{score:20},T,true);r.baseline(c,T);
 for(let i=1;i<=21;i++){const c=token(i,i>=10?'new-pool':'pool');r.observe(c,c,{score:20},c.marketObservedAt,true);}
 const row=events.find(e=>e.kind==='research-outcomes'&&e.row.horizon==='5m').row;
 assert.equal(row.status,'missing');assert.equal(row.evidenceHistory.poolAddress,'new-pool');
 assert.ok(row.evidenceHistory.samples.every(p=>p.at>=T+160000));
});
