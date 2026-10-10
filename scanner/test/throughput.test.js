import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {Radar} from '../src/core/radar.js';
import {Storage} from '../src/core/storage.js';
import {createEntry} from '../src/core/paper.js';
import {readConfig} from '../src/config.js';
import {getTokenPairs} from '../src/adapters/dexscreener.js';
import {scoreCandidate} from '../src/core/scoring.js';
const mint='So11111111111111111111111111111111111111112';
const second='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v';
const fixture=JSON.parse(fs.readFileSync(new URL('../fixtures/scoring-cases.json',import.meta.url)))[0];
const market=(id=mint)=>({mint:id,pairAddress:'original',pairCreatedAt:Date.now(),priceUsd:1,liquidityUsd:20000,txns:{m5:{buys:60,sells:25}}});
function radar(t,adapters={},config={}) {
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'radar-throughput-'));
 const storage=new Storage(dir);t.after(()=>{storage.close();fs.rmSync(dir,{recursive:true,force:true});});
 return new Radar({...readConfig({}),...config},storage,adapters);
}
function deferred(){let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};}
const raw=(address,pair='original',usd=100)=>({chainId:'solana',baseToken:{address},pairAddress:pair,liquidity:{usd},priceUsd:'1'});

test('batch endpoint splits at 30 and assigns explicit missing observations',async()=>{
 const candidates=Array.from({length:65},(_,i)=>({mint:`mint${i}`}));let calls=0;
 const result=await getTokenPairs(candidates,{json:async(_,url)=>{calls++;assert.ok(url.split('/').at(-1).split(',').length<=30);return [];}});
 assert.equal(calls,3);assert.equal(result.size,65);assert.equal(result.get('mint64').market,null);
});
test('batch rejects wrong chain, quote-only match and unrelated mints',async()=>{
 const result=await getTokenPairs([{mint}],{json:async()=>[{...raw(mint),chainId:'ethereum'},{...raw(second),quoteToken:{address:mint}},raw(mint,'correct',50),raw(mint,'larger',100)]});
 assert.equal(result.get(mint).market.pairAddress,'larger');assert.equal(result.size,1);
});
test('paper batch requests exact pool and never substitutes a larger pool',async()=>{
 let url;
 const result=await getTokenPairs([{mint,paperEntry:{pairAddress:'original'}}],{json:async(_,u)=>{url=u;return {pairs:[raw(mint,'larger',10000)]};}});
 assert.ok(url.endsWith('/latest/dex/pairs/solana/original'));assert.equal(result.get(mint).market,null);
});
test('mixed batch keeps observation times and pins original paper market',async()=>{
 const result=await getTokenPairs([{mint:second},{mint,paperEntry:{pairAddress:'original'}}],{json:async(_,url)=>url.includes('/tokens/v1/')?[raw(second)]:{pairs:[raw(mint),raw(second,'original')]}});
 assert.equal(result.get(mint).market.mint,mint);assert.equal(result.get(second).market.mint,second);
 assert.ok(result.get(mint).observedAt>0);
});
test('malformed batch response is an error rather than empty coverage',async()=>{
 await assert.rejects(getTokenPairs([{mint}],{json:async()=>({oops:true})}),/not an array/);
});
test('1000 pending candidates receive a first attempt in 34 batches',async t=>{
 let calls=0;const r=radar(t,{getTokenPairs:async rows=>{calls++;return new Map(rows.map(c=>[c.mint,{market:null,observedAt:Date.now()}]));}});
 for(let i=0;i<1000;i++){const id=String(i);r.candidates.set(id,{mint:id,firstSeenAt:Date.now()});}
 for(let i=0;i<34;i++)await r.enrichBatch();
 assert.equal(calls,34);assert.equal(r.getHealth().coverage.neverAttempted,0);assert.equal(r.getHealth().coverage.noUsableMarket,1000);
});
test('single-slot scheduler rotates between paper, first looks and revisits',t=>{
 const r=radar(t,{}, {batchSize:1});
 r.candidates=new Map([['paper',{mint:'paper',firstSeenAt:1,paperEntry:{version:'price-v2',horizons:{}}}],['new',{mint:'new',firstSeenAt:2}],['rest',{mint:'rest',lastAttemptAt:1,firstSeenAt:1}]]);
 const picks=Array.from({length:3},()=>r.selectBatch(100000)[0].mint);
 assert.deepEqual(new Set(picks),new Set(['paper','new','rest']));
});
test('slow metadata cannot block another market batch or overwrite its price',async t=>{
 const gate=deferred();const r=radar(t,{getMintSecurity:()=>gate.promise,getTokenPairs:async rows=>new Map(rows.map(c=>[c.mint,{market:{...market(c.mint),priceUsd:2},observedAt:Date.now()}]))},{heliusApiKey:'test'});
 r.addCandidate({...market(),marketObservedAt:Date.now()});
 const security=r.refreshMetadata('helius',mint);
 await r.enrichBatch([r.candidates.get(mint)]);assert.equal(r.candidates.get(mint).priceUsd,2);
 gate.resolve({mintAuthority:null,freezeAuthority:null,top10Pct:10,securityCheckedAt:Date.now(),priceUsd:999});await security;
 assert.equal(r.candidates.get(mint).priceUsd,2);assert.equal(r.candidates.get(mint).top10Pct,10);
});
test('late metadata cannot resurrect an evicted or newly rediscovered row',async t=>{
 const gate=deferred();const r=radar(t,{getMintSecurity:()=>gate.promise},{heliusApiKey:'test'});
 r.addCandidate({...market(),marketObservedAt:Date.now()});const security=r.refreshMetadata('helius',mint);
 r.candidates.delete(mint);r.storage.deleteCandidate(mint);r.addCandidate({mint});
 gate.resolve({mintAuthority:null,freezeAuthority:null,top10Pct:10,securityCheckedAt:Date.now()});await security;
 assert.equal(r.candidates.get(mint).securityCheckedAt,undefined);
});
test('metadata completion during market fetch survives the market merge',async t=>{
 const gate=deferred();const r=radar(t,{getTokenPair:()=>gate.promise,getMintSecurity:async()=>({mintAuthority:null,freezeAuthority:null,top10Pct:12,securityCheckedAt:Date.now()})},{heliusApiKey:'test'});
 r.addCandidate({...market(),marketObservedAt:Date.now()});const pending=r.enrichOne(mint);await r.refreshMetadata('helius',mint);
 r.addCandidate({mint,discoverySource:'new-feed'});gate.resolve(market());await pending;
 assert.equal(r.candidates.get(mint).top10Pct,12);assert.ok(r.candidates.get(mint).discoverySources.includes('new-feed'));
});
test('provider failures do not claim no-market success or create stale alerts',async t=>{
 const r=radar(t,{getTokenPairs:async()=>{throw new Error('offline');}});r.addCandidate({...market(),marketObservedAt:Date.now(),score:100});
 await r.enrichBatch();const c=r.candidates.get(mint);
 assert.equal(c.marketAttemptStatus,'error');assert.equal(c.marketEmptyCount,undefined);assert.equal(c.score,0);assert.equal(r.storage.readJsonl('alerts').length,0);
});
test('empty market backoff does not delay tracked paper observations',async t=>{
 const r=radar(t);r.addCandidate({mint});await r.enrichOne(mint,{market:null,observedAt:Date.now()});
 assert.ok(r.candidates.get(mint).nextMarketAttemptAt>Date.now());
 r.addCandidate({mint:second,paperEntry:createEntry(market(second),Date.now())});
 await r.enrichOne(second,{market:null,observedAt:Date.now()});assert.equal(r.candidates.get(second).nextMarketAttemptAt,undefined);
});
test('metadata-only extensions remove no other authority or concentration caps',()=>{
 const c={...fixture.current,extensions:['metadataPointer','tokenMetadata']};
 assert.ok(scoreCandidate(c,fixture.previous,fixture.now).score>=82);
 for(const patch of [{mintAuthority:'active'},{freezeAuthority:'active'},{top10Pct:60},{extensions:['metadataPointer','transferHook']},{extensions:['unknown']},{extensions:[null]},{extensions:'tokenMetadata'}])
   assert.ok(scoreCandidate({...c,...patch},fixture.previous,fixture.now).score<=55);
 assert.ok(scoreCandidate({...c,mintAuthority:undefined},fixture.previous,fixture.now).score<=57);
});
test('metadata eligibility excludes thin inactive markets but allows tracked paper',t=>{
 const r=radar(t,{}, {heliusApiKey:'test'}),c={...market(),marketObservedAt:Date.now(),liquidityUsd:100};
 assert.equal(r.metadataEligible(c),false);c.paperEntry={version:'price-v2',horizons:{}};assert.equal(r.metadataEligible(c),true);
 c.marketObservedAt=1;assert.equal(r.metadataEligible(c),false);
});
test('security expiry still prevents a new signal after metadata cap correction',async t=>{
 const r=radar(t);r.addCandidate({mint,...fixture.current,pairCreatedAt:Date.now(),securityCheckedAt:Date.now()-400000,extensions:['tokenMetadata']});
 await r.enrichOne(mint,{market:{...market(),...fixture.current,mint,pairCreatedAt:Date.now(),priceUsd:1},observedAt:Date.now()});
 assert.equal(r.storage.readJsonl('alerts').length,0);
});
test('initial backlog drains while fresh discovery and revisits continue',async t=>{
 let now=Date.now();t.mock.method(Date,'now',()=>now);const seen=new Set();
 const r=radar(t,{getTokenPairs:async rows=>new Map(rows.map(c=>{seen.add(c.mint);return [c.mint,{market:market(c.mint),observedAt:now}];}))});
 // All mints meet production validation; identities are test-only synthetic strings.
 const id=i=>'A'.repeat(28)+i.toString(16).replaceAll('0','z').padStart(6,'B');
 for(let i=0;i<1000;i++)r.addCandidate({mint:id(i),...(i<81?{lastAttemptAt:now-15000}:{} )});
 for(let batch=0;batch<120;batch++) {
   await r.enrichBatch();now+=1500;
   for(let j=0;j<2;j++)r.addCandidate({mint:id(1000+batch*2+j)});
 }
 assert.equal(Array.from({length:1000},(_,i)=>id(i)).filter(m=>seen.has(m)).length,1000);
 assert.equal(r.getHealth().coverage.evictedBeforeAttempt,0);
 assert.ok(r.getHealth().coverage.neverAttempted<=2);
});
test('first pool observation older than launch window cannot create an entry',async t=>{
 const r=radar(t);r.addCandidate({mint,securityCheckedAt:Date.now(),jupiterCheckedAt:Date.now()});
 await r.enrichOne(mint,{market:{...fixture.current,mint,pairCreatedAt:Date.now()-3*3600000,priceUsd:1},observedAt:Date.now()});
 assert.equal(r.candidates.get(mint).inactive,true);assert.equal(r.storage.readJsonl('alerts').length,0);
});
