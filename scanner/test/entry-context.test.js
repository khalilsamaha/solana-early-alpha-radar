import test from 'node:test';
import assert from 'node:assert/strict';
import {captureEntryContext,readEntryContext} from '../src/core/entry-context.js';
const at=1800000000000,c={mint:'mint',pairAddress:'pool',liquidityUsd:0,volume:{m5:100},txns:{m5:{buys:0,sells:10}},
 marketObservedAt:at-200,securityCheckedAt:at-500000,jupiterCheckedAt:at-1000,mintAuthority:null,top10Pct:20};
const cfg={freshMs:120000,securityTtlMs:300000};
const identity={at,mint:c.mint,pairAddress:c.pairAddress};
test('entry context keeps zero, absent fields, derived activity, stale security and unknown authority separate',()=>{
 const before=structuredClone(c),d=captureEntryContext(c,at,cfg);
 assert.equal(d.values.liquidityUsd.value,0);assert.equal(d.values.organicScore.state,'absent');
 assert.equal(d.derived.transactions5m,10);assert.equal(d.derived.averageReportedTradeUsd,10);
 assert.equal(d.authorities.mintAuthority,false);assert.equal(d.authorities.freezeAuthority,null);
 assert.equal(d.clocks.securityCheckedAt.state,'stale');assert.equal(d.clocks.jupiterCheckedAt.state,'age-only');
 assert.deepEqual(readEntryContext(d,identity),{state:'recorded',data:d});assert.deepEqual(c,before);
});
test('missing counts, malformed numbers and future provider times cannot become zeros or fresh evidence',()=>{
 const d=captureEntryContext({...c,txns:{m5:{buys:1}},marketObservedAt:at+1,liquidityUsd:'0',top10Pct:101},at,cfg);
 assert.equal(d.derived.transactions5m,null);assert.equal(d.derived.averageReportedTradeUsd,null);
 assert.equal(d.clocks.marketObservedAt.at,null);assert.equal(d.clocks.marketObservedAt.state,'invalid');
 assert.equal(d.values.liquidityUsd.state,'invalid');assert.equal(d.values.top10Pct.state,'invalid');
 assert.equal(readEntryContext(d,identity).state,'recorded');
});
test('consumer rejects wrong pool, later contexts and forged age/freshness; allowlists extra data',()=>{
 const d=captureEntryContext(c,at,cfg);
 for(const mutate of [x=>x.pairAddress='other',x=>x.signalAt++,x=>x.clocks.securityCheckedAt.state='within-ttl',x=>x.clocks.marketObservedAt.ageMs=0,x=>x.values.buys5m.value=.5]){
  const bad=structuredClone(d);mutate(bad);assert.equal(readEntryContext(bad,identity).state,'invalid');
 }
 d.secret='not exported';d.values.liquidityUsd.extra='not exported';d.derived.transactions5m=999;
 const out=readEntryContext(d,identity).data;assert.equal(out.secret,undefined);assert.equal(out.values.liquidityUsd.extra,undefined);assert.equal(out.derived.transactions5m,10);
});
test('captured evidence is detached and bounded regardless of candidate size',()=>{
 const d=captureEntryContext({...c,arbitrary:new Array(10000).fill('x')},at,cfg);
 c.txns.m5.sells=20;assert.equal(d.derived.transactions5m,10);c.txns.m5.sells=10;
 assert.ok(JSON.stringify(d).length<2500);
});
