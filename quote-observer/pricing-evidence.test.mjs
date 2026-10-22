import test from 'node:test';
import assert from 'node:assert/strict';
import {parseQuote,USDC,SOL} from './quote-check.mjs';
import {entryFeatures} from './entry-features.mjs';
const body=()=>({inputMint:USDC,outputMint:SOL,inAmount:'10000000',outAmount:'100',transaction:null,
 routePlan:[{swapInfo:{ammKey:SOL,inputMint:USDC,outputMint:SOL,inAmount:'18446744073709551615',outAmount:'100'},bps:10000,usdValue:10}],
 inUsdValue:10,outUsdValue:9.9,swapUsdValue:10,platformFee:{amount:'0',feeBps:10,feeMint:USDC},priceImpact:-1});
test('pricing fields preserve exact atomic route amounts and zero fee without modifying quote output',()=>{
 const b=body(),r=parseQuote(b,USDC,SOL,'10000000');
 assert.equal(r.outAmount,'100');assert.equal(r.inUsdValue,10);assert.equal(r.platformFee.amountAtomic,'0');
 assert.equal(r.routePlan[0].inputAtomic,'18446744073709551615');assert.equal(r.pricingEvidenceVersion,'quote-pricing-1');
});
test('malformed optional pricing remains unknown and arbitrary provider fields are omitted',()=>{
 const b=body();b.inUsdValue='10';b.outUsdValue=-1;b.swapUsdValue=true;b.secret='CANARY';
 b.platformFee={amount:'18446744073709551616',feeBps:'10',feeMint:'CANARY',secret:'CANARY'};
 b.routePlan[0].swapInfo.inAmount=123;b.routePlan[0].secret='CANARY';
 const r=parseQuote(b,USDC,SOL,'10000000');
 assert.equal(r.status,'quoted');assert.equal(r.inUsdValue,null);assert.equal(r.outUsdValue,null);assert.equal(r.swapUsdValue,null);
 assert.equal(r.platformFee.amountAtomic,null);assert.equal(r.routePlan[0].inputAtomic,null);assert.ok(!JSON.stringify(r).includes('CANARY'));
});
test('qualification provenance comes only from the entry event and refuses future assessment time',()=>{
 const at=1800000000000,q={version:'qualification-1',mode:'shadow',at,disposition:'retain'};
 const r=entryFeatures({at,qualification:q});assert.equal(r.features.qualificationVersion,'qualification-1');assert.equal(r.features.qualificationAt,at);
 assert.equal(entryFeatures({at,qualification:{...q,at:at+1}}).features.qualificationAt,null);
 assert.equal(entryFeatures({at}).features.qualificationVersion,null);
});
