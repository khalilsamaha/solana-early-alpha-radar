import test from 'node:test';import assert from 'node:assert/strict';
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';
import {recordMetadata,metadataAt,readMetadata} from '../src/core/metadata-provenance.js';
import {captureEntryContext,readEntryContext} from '../src/core/entry-context.js';
import {Radar} from '../src/core/radar.js';import {Storage} from '../src/core/storage.js';import {readConfig} from '../src/config.js';
const T=1800000000000,mint='So11111111111111111111111111111111111111112';
function setup(t,adapters={}){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'metadata-evidence-'));const storage=new Storage(dir);t.after(()=>{storage.close();fs.rmSync(dir,{recursive:true,force:true});});return new Radar({...readConfig({}),jupiterApiKey:'test'},storage,adapters);}
test('partial discovery updates preserve the older per-field receipt and zero values',()=>{
 const p={organicScore:0,holderCount:50};p.metadataProvenance=recordMetadata(null,p,{source:'jupiter:recent',receivedAt:T},T+1);
 const n={...p,organicScore:20};n.metadataProvenance=recordMetadata(p,{organicScore:20},{source:'jupiter:top-organic',receivedAt:T+1000},T+1002);
 const d=metadataAt(n.metadataProvenance,n,T+2000);
 assert.equal(d.fields.organicScore.source,'jupiter:top-organic');assert.equal(d.fields.organicScore.ageMs,1000);
 assert.equal(d.fields.holderCount.source,'jupiter:recent');assert.equal(d.fields.holderCount.ageMs,2000);
 assert.equal(metadataAt(p.metadataProvenance,p,T+2000).fields.organicScore.value,0);
 assert.deepEqual(readMetadata(d,n,T+2000),d);
});
test('unknown overwrites and explicit clears cannot inherit old provenance',()=>{
 const p={organicScore:1,holderCount:20};p.metadataProvenance=recordMetadata(null,p,{source:'jupiter:search',receivedAt:T},T);
 const n=recordMetadata(p,{organicScore:1,holderCount:undefined},null,T+1);
 assert.deepEqual(n.fields,{});assert.equal(metadataAt(p.metadataProvenance,{...p,organicScore:2},T+1).fields.organicScore.state,'invalid');
 for(const receivedAt of [T+1,'1800000000000',NaN])assert.deepEqual(recordMetadata(null,p,{source:'jupiter:recent',receivedAt},T).fields,{});
});
test('entry serialization rejects forged age, value binding and arbitrary provider fields',()=>{
 const c={mint,pairAddress:mint,organicScore:4,holderCount:40};c.metadataProvenance=recordMetadata(null,c,{source:'jupiter:recent',receivedAt:T},T+1);
 const d=captureEntryContext(c,T+2000,{});const id={at:T+2000,mint,pairAddress:mint};
 assert.equal(readEntryContext(d,id).data.metadataProvenance.fields.organicScore.ageMs,2000);
 for(const mutate of [x=>x.ageMs=0,x=>x.value=999,x=>x.receivedAt=T+3000,x=>x.source='untrusted']){
  const bad=structuredClone(d);mutate(bad.metadataProvenance.fields.organicScore);
  const out=readEntryContext(bad,id);assert.equal(out.state,'recorded');assert.equal(out.data.metadataProvenance.fields.organicScore.state,'invalid');
 }
 d.metadataProvenance.secret='private';assert.equal(JSON.stringify(readEntryContext(d,id)).includes('private'),false);
});
test('real discovery loop retains two feed sources with no extra requests or checked-at refresh',async t=>{
 let now=T,calls=0;t.mock.method(Date,'now',()=>now);
 const r=setup(t,{getRecent:async()=>{calls++;return [{id:mint,organicScore:0,holderCount:50}];},getTopOrganic:async()=>{calls++;now+=1000;return [{id:mint,organicScore:10}];}});
 r.addCandidate({mint,priceUsd:1,pairAddress:mint,liquidityUsd:10000,txns:{m5:{buys:20,sells:5}},marketObservedAt:T,stale:false,jupiterCheckedAt:T-500000});
 r.running=true;r.pause=async()=>{r.running=false;};await r.discoveryLoop('jupiter',60000);
 const c=r.candidates.get(mint);assert.equal(calls,2);assert.equal(c.jupiterCheckedAt,T-500000);
 assert.equal(c.metadataProvenance.fields.organicScore.source,'jupiter:top-organic');assert.equal(c.metadataProvenance.fields.holderCount.source,'jupiter:recent');
 assert.equal(r.selectMetadata('jupiter',T+1000).mint,mint);assert.equal(c.holderCount,50);
 const reopen=new Radar(r.config,r.storage);assert.deepEqual(reopen.candidates.get(mint).metadataProvenance,c.metadataProvenance);
});
test('dedicated search records its own provenance and retains its existing scheduling timestamp',async t=>{
 t.mock.method(Date,'now',()=>T);let calls=0;
 const r=setup(t,{searchToken:async()=>{calls++;return {organicScore:10,holderCount:20};}});
 r.addCandidate({mint,priceUsd:1,pairAddress:mint,liquidityUsd:10000,txns:{m5:{buys:20,sells:5}},marketObservedAt:T,stale:false});
 await r.refreshMetadata('jupiter',mint);const c=r.candidates.get(mint);
 assert.equal(calls,1);assert.equal(c.jupiterCheckedAt,T);assert.equal(c.metadataProvenance.fields.organicScore.source,'jupiter:search');
 assert.equal(c.metadataProvenance.fields.holderCount.receivedAt,T);assert.equal(r.selectMetadata('jupiter',T),null);
});
