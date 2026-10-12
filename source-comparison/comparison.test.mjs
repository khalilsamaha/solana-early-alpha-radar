import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {SOL, USDC} from '../quote-observer/quote-check.mjs';
import {parsePrice, requestPrice, endpoint} from './providers.mjs';
import {collect, Ledger, LIMITS, probe, quoteEvidence} from './collector.mjs';
const POOL = 'GbqkJ4cNTWxGNzYbELN6Ha2Nsg7dXbcgFWMuJshYke7D';
const epoch = 1791779000000;
const dex = (price='2') => ({pairs:[{chainId:'solana', pairAddress:POOL, baseToken:{address:SOL}, priceUsd:price}]});
const gecko = (orientation='base') => ({data:{id:`solana_${POOL}`,type:'pool', attributes:{address:POOL,base_token_price_usd:'2',quote_token_price_usd:'3'},relationships:{[`${orientation}_token`]:{data:{id:`solana_${SOL}`}}}}});
function observation(leg, at, offset) {
  return {leg, targetOffsetMs:offset, status:'quoted', inputMint:leg==='buy'?USDC:SOL,
    outputMint:leg==='buy'?SOL:USDC, inAmount:leg==='buy'?'10000000':'200',outAmount:leg==='buy'?'200':'11000000',
    transactionRequested:false,executionVerified:false,startedAt:at-100,receivedAt:at,
    routePlan:[{inputMint:SOL,outputMint:USDC,pool:POOL}],routePlanTruncated:false};
}
function record(seq, start, elapsed=0) {
  const observations=[observation('buy',start)];
  for(const offset of [0,30000,60000,120000]) if(elapsed>=Math.max(10000,offset)) observations.push(observation('sell',start+Math.max(10000,offset),offset));
  return {seq,data:JSON.stringify({mode:'automatic-signal-watch',mint:SOL,baseMint:USDC,inputAtomic:'10000000',startedAt:start,
    signal:{seq,mint:SOL,originalPool:POOL,cohort:'baseline',signalAt:start-500},observations,state:elapsed>=120000?'complete':'running'})};
}
function harness({request, mutate, times=[1000,181000,361000], finish=LIMITS.durationMs}={}) {
  let clock=0, calls=[];
  const source = {sourceIdentity:'1:2',tail:()=>times.filter(t=>clock>=t).length,
    rows:after=>times.flatMap((t,i)=>clock>=t&&i+1>after?[mutate?.(record(i+1,epoch+t,clock-t),clock)||record(i+1,epoch+t,clock-t)]:[]),
    get:seq=>mutate?.(record(seq,epoch+times[seq-1],clock-times[seq-1]),clock)||record(seq,epoch+times[seq-1],clock-times[seq-1])};
  const run = () => collect(source,{now:()=>epoch+clock,monotonic:()=>clock,
    sleep:async ms=>{clock=Math.min(finish,clock+ms); if(clock===finish&&finish<LIMITS.durationMs)clock=LIMITS.durationMs;},
    request:async(provider,pool,mint,options)=>{calls.push({provider,clock,pool,mint});return request?request(provider,clock):{status:'price',priceUsd:provider==='dexscreener'?2:3,startedAt:options.now(),receivedAt:options.now()+20};}});
  return {run,source,calls};
}
test('exact network, pool and mint binding; Gecko orientation is explicit',()=>{
  assert.equal(parsePrice('dexscreener',dex(),POOL,SOL).priceUsd,2);
  assert.equal(parsePrice('geckoterminal',gecko('quote'),POOL,SOL).orientation,'quote');
  const wrong=dex();wrong.pairs[0].chainId='ethereum';assert.notEqual(parsePrice('dexscreener',wrong,POOL,SOL).status,'price');
  assert.notEqual(parsePrice('dexscreener',dex(),POOL,USDC).status,'price');
  const duplicate=dex();duplicate.pairs.push(duplicate.pairs[0]);assert.notEqual(parsePrice('dexscreener',duplicate,POOL,SOL).status,'price');
  const ambiguous=gecko();ambiguous.data.relationships.quote_token=ambiguous.data.relationships.base_token;
  assert.notEqual(parsePrice('geckoterminal',ambiguous,POOL,SOL).status,'price');
  const other=gecko();other.data.id=`eth_${POOL}`;assert.notEqual(parsePrice('geckoterminal',other,POOL,SOL).status,'price');
});
test('unknown, zero, boolean and nonfinite prices remain unavailable',()=>{
  for(const v of [null,undefined,0,'0',true,'Infinity','',{},'1e999']){const body=dex();body.pairs[0].priceUsd=v;assert.equal(parsePrice('dexscreener',body,POOL,SOL).status,'price-unavailable');}
});
test('transport uses fixed public URLs, no credentials or cache-busting, and records cache without freshness claims',async()=>{
  let call;
  const r=await requestPrice('geckoterminal',POOL,SOL,{fetchFn:async(url,opts)=>{call={url,opts};return new Response(JSON.stringify(gecko()),{headers:{age:'19','cf-cache-status':'HIT'}});}});
  assert.equal(r.status,'price');assert.equal(r.httpAgeSeconds,19);assert.equal(r.providerPriceAt,null);
  assert.equal(call.opts.method,'GET');assert.equal(call.opts.redirect,'error');assert.deepEqual(Object.keys(call.opts.headers),['accept']);
  assert.equal(call.url,endpoint('geckoterminal',POOL));assert.ok(!call.url.includes('?'));
  assert.throws(()=>endpoint('other',POOL));assert.throws(()=>endpoint('dexscreener','../../x'));
});
test('HTTP access/rate errors are explicit and response bodies never leak',async()=>{
  for(const [status,expected] of [[429,'rate-limited'],[403,'access-denied'],[401,'access-denied'],[404,'http-error']]) {
    const r=await requestPrice('dexscreener',POOL,SOL,{fetchFn:async()=>new Response('private arbitrary text',{status})});
    assert.equal(r.status,expected);assert.ok(!JSON.stringify(r).includes('private'));
  }
});
test('oversized and malformed public responses fail boundedly',async()=>{
  for(const [body,expected] of [['x'.repeat(262145),'response-too-large'],['not json','network-or-json-error']]) {
    const r=await requestPrice('dexscreener',POOL,SOL,{fetchFn:async()=>new Response(body)});assert.equal(r.status,expected);
  }
});
test('three prospective watches use four points each and at most twenty-four HTTP calls',async()=>{
  const h=harness(),r=await h.run();assert.equal(r.state,'watch-cap');assert.equal(r.requests,24);assert.equal(r.watches.length,3);
  assert.equal(r.summary.pairedPrices,12);assert.equal(r.summary.priceDisagreementsAbove10Pct,12);
  assert.equal(r.watches[0].points[1].prices[0].changeFromBuyPricePct,0);
  assert.equal(r.watches[0].points[1].prices[0].quoteMinusPriceChangePp,10);
  for(const w of r.watches)assert.deepEqual(w.points.map(p=>p.key),['buy','sell:30000','sell:60000','sell:120000']);
  for(const provider of ['dexscreener','geckoterminal']) {
    const times=h.calls.filter(c=>c.provider===provider).map(c=>c.clock);
    assert.ok(times.slice(1).every((t,i)=>t-times[i]>=10000));
  }
});
test('failed sell is retained and cannot become zero return or provider request',async()=>{
  const h=harness({times:[1000],mutate:row=>{const p=JSON.parse(row.data);for(const o of p.observations)if(o.targetOffsetMs===30000)o.status='http-error';return {...row,data:JSON.stringify(p)};}});
  const r=await h.run();assert.equal(r.requests,6);const point=r.watches[0].points[1];
  assert.equal(point.state,'quote-failed-or-invalid');assert.equal(point.quote.quotedUsdcChangePct,null);
});
test('stale quote is labelled, not retried or paired to current price',async()=>{
  const h=harness({times:[1000],mutate:(row,clock)=>{const p=JSON.parse(row.data);if(clock>=31000)p.observations.find(o=>o.targetOffsetMs===30000).receivedAt-=6000;return {...row,data:JSON.stringify(p)};}});
  // Keep the quote clock internally valid while making its receipt stale.
  const old=h.source.get;h.source.get=s=>{const row=old(s),p=JSON.parse(row.data);for(const o of p.observations)o.startedAt=Math.min(o.startedAt,o.receivedAt-100);return {...row,data:JSON.stringify(p)};};
  const r=await h.run();assert.equal(r.watches[0].points[1].state,'quote-receipt-not-timely');assert.equal(r.requests,6);
});
test('provider denial halts the run after the already-started pair',async()=>{
  const h=harness({request:async(provider,clock)=>({status:provider==='geckoterminal'?'rate-limited':'price',priceUsd:2,startedAt:epoch+clock})});
  const r=await h.run();assert.equal(r.state,'provider-halt');assert.equal(r.requests,2);
  assert.equal(r.watches[0].points.filter(p=>p.state==='run-ended-before-observation').length,3);
});
test('busy arrivals are excluded with no hidden queue',async()=>{
  const h=harness({times:[1000,2000,3000]});const r=await h.run();assert.equal(r.watches.length,1);assert.equal(r.exclusions['observer-watch-arrived-while-busy'],2);
});
test('preexisting watches are skipped by tail registration',async()=>{
  const h=harness({times:[-1000]});const r=await h.run();assert.equal(r.initialTail,1);assert.equal(r.requests,0);
});
test('an excessive incoming backlog stops instead of scanning unbounded history',async()=>{
  const h=harness({times:Array.from({length:21},()=>1000)});const r=await h.run();
  assert.equal(r.state,'source-backlog');assert.equal(r.requests,0);
});
test('interruption preserves a sampled buy and labels unobserved exit points',async()=>{
  const controller=new AbortController();let clock=0;
  const ledger={sourceIdentity:'1:2',tail:()=>clock?1:0,rows:after=>clock&&!after?[record(1,epoch+1000)]:[],get:()=>record(1,epoch+1000)};
  const r=await collect(ledger,{signal:controller.signal,now:()=>epoch+clock,monotonic:()=>clock,
    sleep:async()=>{clock+=1000;if(clock>1000)controller.abort();},
    request:async()=>({status:'price',priceUsd:1,startedAt:epoch+clock,receivedAt:epoch+clock})});
  assert.equal(r.state,'interrupted');assert.equal(r.requests,2);
  assert.equal(r.watches[0].points.filter(x=>x.state==='run-ended-before-observation').length,3);
});
test('same observation cannot trigger a repeated request across polls',async()=>{
  const h=harness({times:[1000],mutate:row=>{const p=JSON.parse(row.data);p.observations=p.observations.slice(0,1);p.state='running';return {...row,data:JSON.stringify(p)};}});
  const r=await h.run();assert.equal(r.requests,2);assert.equal(r.watches[0].state,'watch-deadline');
});
test('source identity failures preserve completed evidence and terminate',async()=>{
  const h=harness();const old=h.source.get;let reads=0;h.source.get=s=>{if(++reads>3)throw Error('private path');return old(s);};
  const r=await h.run();assert.equal(r.state,'source-error');assert.equal(r.requests,2);assert.ok(!JSON.stringify(r).includes('private path'));
});
test('placeholder admission and quantity validation cannot manufacture a quoted result',()=>{
  const row=record(1,epoch);const p=JSON.parse(row.data);delete p.mode;delete p.mint;delete p.baseMint;delete p.inputAtomic;p.observations=[];
  assert.ok(probe({...row,data:JSON.stringify(p)}));
  const good=probe(row),sell=observation('sell',epoch+30000,30000);sell.inAmount='201';assert.equal(quoteEvidence(sell,good).status,'quote-failed-or-invalid');
  good.observations[0].executionVerified=true;assert.equal(quoteEvidence(good.observations[0],good).status,'quote-failed-or-invalid');
});
test('readonly SQLite reader sees updates, bounds payloads and detects source replacement',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'source-comparison-')),file=path.join(dir,'ledger');
  const db=new DatabaseSync(file);db.exec('CREATE TABLE meta(k TEXT PRIMARY KEY,v TEXT); CREATE TABLE probes(seq INTEGER PRIMARY KEY,data TEXT)');
  db.prepare('INSERT INTO meta VALUES(?,?)').run('sourceIdentity',JSON.stringify('1:2'));
  const ledger=new Ledger(file);
  try {
    assert.equal(ledger.tail(),0);db.prepare('INSERT INTO probes VALUES(?,?)').run(1,record(1,epoch).data);
    assert.equal(probe(ledger.get(1)).mint,SOL);assert.throws(()=>ledger.db.exec('DELETE FROM probes'));
    db.prepare('INSERT INTO probes VALUES(?,?)').run(2,'x'.repeat(65537));assert.equal(ledger.rows(1)[0].data,null);
    db.prepare('UPDATE meta SET v=?').run(JSON.stringify('2:3'));assert.throws(()=>ledger.tail());
  } finally {ledger.close();db.close();fs.rmSync(dir,{recursive:true,force:true});}
});
