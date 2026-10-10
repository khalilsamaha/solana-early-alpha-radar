import test from 'node:test';
import assert from 'node:assert/strict';
import {entryFeatures,FEATURE_CAPTURE} from './entry-features.mjs';
import {signalRecord} from './observer.mjs';
const at=1800000000000;
const mint='So11111111111111111111111111111111111111112';
test('baseline immutable feature capture preserves zeros, sources and ages',()=>{
 const r={at,candidate:{liquidityUsd:0,organicScore:0,holderCount:2500,top10Pct:20},
 qualification:{metrics:{averageReportedTradeUsd:2,transactions5m:3000,volume5mUsd:6000,return30sPct:-2}},
 evidence:{inputs:{marketObservedAt:at-500,securityCheckedAt:at-10000,jupiterCheckedAt:at-5000}}};
 const before=structuredClone(r),out=entryFeatures(r);
 assert.equal(out.features.liquidityUsd,0);assert.equal(out.features.organicScore,0);
 assert.equal(out.features.averageReportedTradeUsd,2);assert.equal(out.features.holderCount,2500);
 assert.equal(out.featureCapture.ageAtSignalMs.securityCheckedAt,10000);
 assert.equal(out.featureCapture.sources.averageReportedTradeUsd.source,'qualification.metrics.averageReportedTradeUsd');
 assert.deepEqual(r,before);
});
test('early activity never fills missing provider data using marketContext or later fields',()=>{
 const out=entryFeatures({at,candidate:{liquidityUsd:null},marketContext:{holderCount:500,security:'limited checks complete'},
 qualification:{metrics:{volume5mUsd:0,transactions5m:0,averageReportedTradeUsd:null}},
 evidence:{inputs:{holderCount:999}}});
 assert.equal(out.features.holderCount,null);assert.equal(out.features.securityCheckedAt,null);
 assert.equal(out.features.averageReportedTradeUsd,null);assert.equal(out.features.transactions5m,0);
 assert.equal(out.featureCapture.sources.holderCount.state,'absent');
});
test('future timestamps and invalid numbers are unknown rather than fresh or zero',()=>{
 const out=entryFeatures({at,candidate:{holderCount:-1,liquidityUsd:Infinity},
 evidence:{inputs:{marketObservedAt:at+1,securityCheckedAt:0,jupiterCheckedAt:'yesterday'}},
 qualification:{metrics:{averageReportedTradeUsd:'3',return30sPct:NaN}}});
 for(const k of ['holderCount','liquidityUsd','marketObservedAt','securityCheckedAt','jupiterCheckedAt','averageReportedTradeUsd','return30sPct']){
  assert.equal(out.features[k],null);assert.equal(out.featureCapture.sources[k].state,'invalid');
 }
});
test('signal parsing adds features without changing cohort, identity or admission inputs',()=>{
 const raw={id:`${mint}:${at}:1`,at,engineVersion:'0.2.9',candidate:{mint,holderCount:42},
 qualification:{disposition:'defer',historyReady:false,metrics:{averageReportedTradeUsd:3}}};
 const s=signalRecord({kind:'alerts',seq:4,at,data:JSON.stringify(raw)});
 assert.equal(s.seq,4);assert.equal(s.entryId,raw.id);assert.equal(s.cohort,'baseline');
 assert.equal(s.features.disposition,'defer');assert.equal(s.features.holderCount,42);
 assert.equal(s.featureCapture.version,FEATURE_CAPTURE);
});
