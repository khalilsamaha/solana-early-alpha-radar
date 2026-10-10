import test from 'node:test';
import assert from 'node:assert/strict';
import {args,address,amount,urlFor,parseQuote,requestQuote,observe,usdcChange,pause,USDC,SOL} from './quote-check.mjs';
const mint='6f4ZQ3cBHMaBDCab9Cjdb4r8WLHYiLU9gSGVjtxwpump';
function body(inputMint=USDC,outputMint=SOL,inAmount='10000000',outAmount='60000000'){
 return {inputMint,outputMint,inAmount,outAmount,swapMode:'ExactIn',transaction:null,routePlan:[{swapInfo:{ammKey:SOL,label:'Test route'}}],priceImpact:-0.1,feeBps:2};
}
test('validates address bytes and rejects names or malformed input',()=>{
 assert(address(mint));assert(address(USDC));assert(address(SOL));assert(!address('INFINIT'));assert(!address('1'.repeat(31)));assert(!address('0'.repeat(32)));
 assert.throws(()=>args(['--mint','INFINIT']));assert.throws(()=>args(['--mint',USDC]));assert.throws(()=>args(['--preflight','--watch']));assert.throws(()=>args(['--execute']));
 assert.equal(args(['--preflight']).mint,SOL);
});
test('quantity uses positive u64 decimal strings',()=>{
 assert(amount('18446744073709551615'));assert(!amount('18446744073709551616'));assert(!amount('0'));assert(!amount('1e6'));assert(!amount(100));
});
test('only fixed quote endpoint and three walletless parameters',()=>{
 const u=urlFor(USDC,mint,'10000000');assert.equal(u.origin+u.pathname,'https://api.jup.ag/swap/v2/order');
 assert.deepEqual([...u.searchParams.keys()],['inputMint','outputMint','amount']);assert(!u.search.includes('taker'));
});
test('rejects mismatched amount, mint and transaction',()=>{
 for(const change of [{inputMint:SOL},{outAmount:'0'},{inAmount:'9'},{transaction:'DONT-EXPORT'},{swapMode:'ExactOut'},{routePlan:[]}])
 assert.notEqual(parseQuote({...body(),...change},USDC,SOL,'10000000').status,'quoted');
});
test('allowlists response fields and preserves fee uncertainty',()=>{
 const b=body();b.secret='CANARY';b.requestId='CANARY';b.priceImpact=-.1;
 const r=parseQuote(b,USDC,SOL,'10000000');assert.equal(r.status,'quoted');assert.equal(r.priceImpactPercentagePoints,-.1);
 assert.equal(r.rentFeeLamports,null);assert(!JSON.stringify(r).includes('CANARY'));assert.equal(r.executionVerified,false);
});
test('provider errors not accepted as executable quotes',()=>{
 assert.equal(parseQuote({...body(),errorCode:5},USDC,SOL,'10000000').status,'provider-error');
});
test('HTTP transport uses GET, no credentials, refuses redirects',async()=>{
 const r=await requestQuote(USDC,SOL,'10000000',{fetchFn:async(u,o)=>{
  assert.equal(o.method,'GET');assert.equal(o.redirect,'error');assert.deepEqual(o.headers,{accept:'application/json'});
  return new Response(JSON.stringify(body()));
 }});assert.equal(r.status,'quoted');
});
test('rate errors sanitized, not leaked raw',async()=>{
 const r=await requestQuote(USDC,SOL,'10000000',{fetchFn:async()=>new Response('SECRET',{status:429})});
 assert.equal(r.status,'rate-limited');assert(!JSON.stringify(r).includes('SECRET'));
});
test('network errors sanitized',async()=>{
 const r=await requestQuote(USDC,SOL,'10000000',{fetchFn:async()=>{throw Error('SECRET');}});
 assert.equal(r.status,'network-or-json-error');assert(!JSON.stringify(r).includes('SECRET'));
});
test('response byte cap enforced',async()=>{
 const r=await requestQuote(USDC,SOL,'10000000',{fetchFn:async()=>new Response('x'.repeat(262145))});assert.equal(r.status,'response-too-large');
});
function mock(statuses=[]){
 let clock=1000000;const calls=[];const saved=[];
 return {calls,saved,dep:{now:()=>clock,sleep:async ms=>{clock+=ms;},save:async r=>saved.push(structuredClone(r)),
 quote:async(i,o,n)=>{const startedAt=clock;clock+=100;calls.push({i,o,n,startedAt});
  const status=statuses[calls.length-1]||'quoted';return {status,startedAt,receivedAt:clock,latencyMs:100,...(status==='quoted'?{inAmount:n,outAmount:i===USDC?'9007199254740993':'9900000'}:{})};}}};
}
test('preflight limited to two requests and exact reverse quantity',async()=>{
 const x=mock();const r=await observe(args(['--preflight']),x.dep);assert.equal(r.requests,2);
 assert.equal(x.calls[1].n,'9007199254740993');assert(x.calls[1].startedAt-x.calls[0].startedAt>=10000);
 assert.equal(r.observations[1].quotedUsdcChangePct,-1);assert.equal(r.state,'complete');
});
test('watch uses one fixed hypothetical quantity and bounded schedule',async()=>{
 const x=mock();const r=await observe(args(['--mint',mint,'--watch']),x.dep);assert.equal(r.requests,5);
 assert(x.calls.slice(1).every(c=>c.n==='9007199254740993'));assert.deepEqual(r.observations.slice(1).map(o=>o.targetOffsetMs),[0,30000,60000,120000]);
 assert.equal(x.saved.at(-1).state,'complete');
});
test('buy failure never requests hypothetical sells',async()=>{
 const x=mock(['access-denied']);const r=await observe(args(['--preflight']),x.dep);assert.equal(r.requests,1);assert.equal(r.state,'buy-quote-failed');
});
test('rate limit stops further requests without retry',async()=>{
 const x=mock(['quoted','rate-limited']);const r=await observe(args(['--mint',mint,'--watch']),x.dep);assert.equal(r.requests,2);assert.equal(r.state,'stopped');assert.equal(r.observations.filter(o=>o.status==='skipped').length,3);
});
test('ordinary sell failure stays visible and can later recover',async()=>{
 const x=mock(['quoted','network-or-json-error']);const r=await observe(args(['--mint',mint,'--watch']),x.dep);assert.equal(r.requests,5);assert.equal(r.state,'complete-with-failures');
 assert.equal(r.observations[1].quotedUsdcChangePct,undefined);
});
test('late samples not disguised as on-time',async()=>{
 let t=1000000;
 const r=await observe(args(['--mint',mint,'--watch']),{now:()=>t,sleep:async ms=>{t+=ms+200000;},quote:async()=>({status:'quoted',startedAt:t,receivedAt:t,inAmount:'10000000',outAmount:'9900000'}),save:async()=>{}});
 assert.equal(r.requests,1);assert(r.observations.slice(1).every(o=>o.reason==='deadline-missed'));
});
test('quoted USDC change calculated with integers without implying fees',()=>{
 assert.equal(usdcChange('9900000','10000000'),-1);assert.equal(usdcChange('11000000','10000000'),10);
});
test('abort cancels waiting promptly',async()=>{
 const c=new AbortController();const waiting=pause(30000,c.signal);c.abort();await waiting;
});
test('HTTP 400 retains safe route classification but not raw error or identifiers',async()=>{
 const r=await requestQuote(USDC,SOL,'10000000',{fetchFn:async()=>new Response(JSON.stringify({error:'No routes found SECRET_ADDRESS',requestId:'SECRET_ID',transaction:'SECRET_TX',errorCode:42}),{status:400})});
 assert.equal(r.status,'http-error');assert.equal(r.httpStatus,400);assert.equal(r.providerCategory,'route-unavailable-reported');assert.equal(r.providerCode,42);assert(!JSON.stringify(r).includes('SECRET'));
});
test('unknown, malformed and oversized error responses remain explicit',async()=>{
 for(const [raw,status] of [[JSON.stringify({error:'CANARY custom issue'}),'json'],['not json CANARY','not-json'],['x'.repeat(8193),'oversized']]){
 const r=await requestQuote(USDC,SOL,'10000000',{fetchFn:async()=>new Response(raw,{status:400})});assert.equal(r.errorBodyStatus,status);assert.equal(r.httpStatus,400);assert(!JSON.stringify(r).includes('CANARY'));}
});
