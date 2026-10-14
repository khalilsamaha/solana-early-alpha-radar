// Walletless, bounded GET-only quote observation. No signing or execution paths.
import fs from 'node:fs/promises';
import {errorEvidence} from './error-evidence.mjs';
export {errorEvidence} from './error-evidence.mjs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
export const VERSION='radar-quote-transport-0.4.0';
export const USDC='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v';
export const SOL='So11111111111111111111111111111111111111112';
export const ENDPOINT='https://api.jup.ag/swap/v2/order';
const U64=(1n<<64n)-1n;
export function address(s){
  if(typeof s!=='string'||s.length<32||s.length>44)return false;
  const alphabet='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';let n=0n;
  for(const c of s){const i=alphabet.indexOf(c);if(i<0)return false;n=n*58n+BigInt(i);}
  let bytes=0;for(let t=n;t>0;t>>=8n)bytes++;
  return bytes+(s.match(/^1*/)?.[0].length||0)===32;
}
export function amount(s){return typeof s==='string'&&/^[1-9][0-9]{0,19}$/.test(s)&&BigInt(s)<=U64;}
export function args(argv){
  let preflight=false,mint=null,watch=false;
  for(let i=0;i<argv.length;i++){
    if(argv[i]==='--preflight')preflight=true;
    else if(argv[i]==='--mint'){if(mint!==null)throw Error('Duplicate mint');mint=argv[++i];}
    else if(argv[i]==='--watch')watch=true;
    else throw Error('Usage: node quote-check.mjs --preflight OR --mint SOLANA_MINT [--watch]');
  }
  if(preflight&&(mint||watch))throw Error('Preflight cannot be combined with mint or watch');
  if(!preflight&&(!address(mint)||mint===USDC))throw Error('Supply a valid Solana mint other than USDC');
  return {mint:preflight?SOL:mint,watch,preflight,usdcAtomic:'10000000'};
}
export function urlFor(inputMint,outputMint,inAmount){
  if(!address(inputMint)||!address(outputMint)||inputMint===outputMint||!amount(inAmount))throw Error('Invalid quote arguments');
  const u=new URL(ENDPOINT);u.search=new URLSearchParams({inputMint,outputMint,amount:inAmount}).toString();return u;
}
const numeric=x=>typeof x==='number'&&Number.isFinite(x)?x:null;
const text=(x,n=96)=>typeof x==='string'?x.slice(0,n):null;
const nonnegative=x=>numeric(x)!==null&&x>=0?x:null;
const atomicOrZero=x=>typeof x==='string'&&/^(0|[1-9][0-9]{0,19})$/.test(x)&&BigInt(x)<=U64?x:null;
export function parseQuote(b,inputMint,outputMint,inAmount){
  if(!b||typeof b!=='object'||Array.isArray(b))return {status:'invalid-response'};
  if(b.transaction)return {status:'unexpected-transaction-rejected'};
  if(b.errorCode!==undefined&&b.errorCode!==null)return {status:'provider-error',...errorEvidence(b)};
  if(b.error!==undefined||b.errorMessage)return {status:'provider-error',...errorEvidence(b)};
  if(b.inputMint!==inputMint||b.outputMint!==outputMint||b.inAmount!==inAmount||!amount(b.outAmount))return {status:'invalid-response'};
  if(b.swapMode!==undefined&&b.swapMode!=='ExactIn')return {status:'unexpected-swap-mode'};
  if(!Array.isArray(b.routePlan)||!b.routePlan.length)return {status:'no-route-evidence'};
  return {status:'quoted',inputMint,outputMint,inAmount,outAmount:b.outAmount,
    pricingEvidenceVersion:'quote-pricing-1',
    inUsdValue:nonnegative(b.inUsdValue),outUsdValue:nonnegative(b.outUsdValue),swapUsdValue:nonnegative(b.swapUsdValue),
    platformFee:{amountAtomic:atomicOrZero(b.platformFee?.amount),feeBps:nonnegative(b.platformFee?.feeBps),
      feeMint:address(b.platformFee?.feeMint)?b.platformFee.feeMint:null},
    minimumOutAmount:amount(b.otherAmountThreshold)?b.otherAmountThreshold:null,
    priceImpactPercentagePoints:numeric(b.priceImpact),legacyPriceImpactRatio:text(b.priceImpactPct),
    feeBps:numeric(b.feeBps),feeMint:address(b.feeMint)?b.feeMint:null,
    signatureFeeLamports:numeric(b.signatureFeeLamports),prioritizationFeeLamports:numeric(b.prioritizationFeeLamports),
    rentFeeLamports:numeric(b.rentFeeLamports),slippageBps:numeric(b.slippageBps),router:text(b.router),
    routePlan:b.routePlan.slice(0,12).map(r=>({pool:address(r?.swapInfo?.ammKey)?r.swapInfo.ammKey:null,
      label:text(r?.swapInfo?.label,48),inputMint:address(r?.swapInfo?.inputMint)?r.swapInfo.inputMint:null,
      outputMint:address(r?.swapInfo?.outputMint)?r.swapInfo.outputMint:null,percent:numeric(r?.percent),
      inputAtomic:atomicOrZero(r?.swapInfo?.inAmount),outputAtomic:atomicOrZero(r?.swapInfo?.outAmount),
      bps:nonnegative(r?.bps),usdValue:nonnegative(r?.usdValue)})),
    routePlanTruncated:b.routePlan.length>12,transactionRequested:false,executionVerified:false};
}
export function usdcChange(out,input){
  if(!amount(out)||!amount(input))throw Error('Invalid amounts');
  // Integer arithmetic avoids token-quantity rounding; output is a descriptive percentage only.
  return Number((BigInt(out)-BigInt(input))*1000000n/BigInt(input))/10000;
}
export async function readError(response){
  if(!response.body)return {errorBodyStatus:'empty'};
  const reader=response.body.getReader();let total=0;const chunks=[];
  try{while(true){const {done,value}=await reader.read();if(done)break;total+=value.length;
    if(total>8192){await reader.cancel();return {errorBodyStatus:'oversized'};}chunks.push(value);}
    try{return errorEvidence(JSON.parse(Buffer.concat(chunks).toString('utf8')));}catch{return {errorBodyStatus:'not-json'};}
  }catch{return {errorBodyStatus:'read-failed'};}
  finally{reader.releaseLock();}
}
export async function requestQuote(inputMint,outputMint,inAmount,{fetchFn=fetch,now=Date.now,signal}={}){
  const startedAt=now();const controller=new AbortController();
  const combined=signal?AbortSignal.any([controller.signal,signal]):controller.signal;
  const timer=setTimeout(()=>controller.abort(),8000);
  let response;
  try{
    response=await fetchFn(urlFor(inputMint,outputMint,inAmount),{method:'GET',redirect:'error',signal:combined,
      headers:{accept:'application/json'}});
    if(!response.ok){const evidence=await readError(response);return {status:response.status===429?'rate-limited':[401,403].includes(response.status)?'access-denied':'http-error',
      ...evidence,httpStatus:response.status,startedAt,receivedAt:now(),latencyMs:now()-startedAt};}
    const reader=response.body.getReader();const chunks=[];let total=0;
    while(true){const {done,value}=await reader.read();if(done)break;total+=value.length;
      if(total>262144){controller.abort();await reader.cancel().catch(()=>{});return {status:'response-too-large',startedAt,receivedAt:now(),latencyMs:now()-startedAt};}chunks.push(value);}
    const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));
    return {...parseQuote(body,inputMint,outputMint,inAmount),httpStatus:response.status,startedAt,receivedAt:now(),latencyMs:now()-startedAt};
  }catch{
    return {status:signal?.aborted?'interrupted':controller.signal.aborted?'timeout':'network-or-json-error',startedAt,receivedAt:now(),latencyMs:now()-startedAt};
  }finally{clearTimeout(timer);}
}
export function pause(ms,signal){
  return new Promise(resolve=>{
    if(signal?.aborted){resolve();return;}
    let timer;const finish=()=>{clearTimeout(timer);signal?.removeEventListener('abort',finish);resolve();};
    timer=setTimeout(finish,ms);signal?.addEventListener('abort',finish,{once:true});
  });
}
export async function observe(options,{quote=requestQuote,now=Date.now,sleep=pause,save=async()=>{},signal}={}){
  const report={format:VERSION,mode:options.preflight?'preflight':options.watch?'manual-watch':'manual-pair',startedAt:now(),
    mint:options.mint,baseMint:USDC,hypotheticalInputUsdc:'10',inputAtomic:options.usdcAtomic,
    sampling:'manual current-time probe; not an entry-cohort or historical replay',maxRequests:options.watch?5:2,
    requests:0,observations:[],state:'running',limits:{minimumRequestSpacingMs:10000,requestTimeoutMs:8000,automaticRetries:0},
    limitations:['Quotes are not fills, wallet simulation or proof of sellability.',
      'The hypothetical token quantity is fixed from the initial buy quote; no purchase is performed.',
      'Quoted USDC change is not net P&L: execution, slippage, network fees and failed transactions are unmeasured.',
      'Quote routing may change pools; observations are not spliced into original-pool paper results.',
      'No scanner signal timestamp or historical execution claim. Manual token selection is not representative sampling.']};
  await save(report);
  const buy=await quote(USDC,options.mint,options.usdcAtomic,{signal});report.requests++;
  report.observations.push({leg:'buy',...buy});await save(report);
  if(buy.status!=='quoted'){report.state='buy-quote-failed';report.finishedAt=now();await save(report);return report;}
  const base=buy.receivedAt;let previousRequest=buy.startedAt;
  let halt=null;
  for(const offset of (options.watch?[0,30000,60000,120000]:[0])){
    if(signal?.aborted)halt='interrupted';
    if(halt){report.observations.push({leg:'sell',targetOffsetMs:offset,status:'skipped',reason:halt});continue;}
    await sleep(Math.max(0,base+offset-now(),previousRequest+10000-now()),signal);
    if(signal?.aborted){halt='interrupted';report.observations.push({leg:'sell',targetOffsetMs:offset,status:'skipped',reason:halt});continue;}
    if(now()>base+offset+15000){report.observations.push({leg:'sell',targetOffsetMs:offset,status:'skipped',reason:'deadline-missed'});await save(report);continue;}
    const sell=await quote(options.mint,USDC,buy.outAmount,{signal});report.requests++;previousRequest=sell.startedAt;
    const row={leg:'sell',targetOffsetMs:offset,actualStartOffsetMs:sell.startedAt-base,...sell};
    if(sell.status==='quoted')row.quotedUsdcChangePct=usdcChange(sell.outAmount,options.usdcAtomic);
    report.observations.push(row);await save(report);
    if(['rate-limited','access-denied','unexpected-transaction-rejected','interrupted'].includes(sell.status))halt=sell.status;
  }
  report.state=halt?'stopped':report.observations.slice(1).every(r=>r.status==='quoted')?'complete':'complete-with-failures';
  report.finishedAt=now();await save(report);return report;
}
async function main(){
  const options=args(process.argv.slice(2));const directory=path.resolve('quote-reports');
  await fs.mkdir(directory,{recursive:true,mode:0o700});
  if((await fs.lstat(directory)).isSymbolicLink())throw Error('Report directory must not be a symlink');
  await fs.chmod(directory,0o700);
  const lock=path.join(directory,'.quote-check.lock');
  try{await fs.mkdir(lock,{mode:0o700});}catch{throw Error('A quote check is running or a previous lock remains; see README.');}
  const controller=new AbortController();let output;
  const stop=()=>controller.abort();process.once('SIGINT',stop);process.once('SIGTERM',stop);
  try{
    await fs.writeFile(path.join(lock,'pid'),String(process.pid),{mode:0o600});
    output=path.join(directory,'radar-quote-'+new Date().toISOString().replace(/[:.]/g,'-')+'-'+randomUUID()+'.json');
    const save=async r=>{const tmp=output+'.tmp';await fs.writeFile(tmp,JSON.stringify(r,null,2)+'\n',{mode:0o600});await fs.rename(tmp,output);};
    console.log(`${VERSION}: 10 USDC hypothetical size; walletless GET requests only.`);
    console.log(`Maximum ${options.watch?5:2} requests. Report: ${output}`);
    const report=await observe(options,{save,signal:controller.signal});
    for(const row of report.observations)console.log(`${row.leg}: ${row.status}`+(row.quotedUsdcChangePct!==undefined?`; quoted USDC change ${row.quotedUsdcChangePct.toFixed(2)}% (not net P&L)`:'')+(row.latencyMs!==undefined?`; ${row.latencyMs}ms`:''));
    console.log(`State: ${report.state}\nUpload: ${output}`);
    if(report.state!=='complete')process.exitCode=2;
  }finally{process.removeListener('SIGINT',stop);process.removeListener('SIGTERM',stop);await fs.rm(lock,{recursive:true,force:true});}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(()=>{
  console.error('Quote check stopped. Check arguments, report directory permissions, or the lock described in README. No trade was sent.');process.exitCode=1;
});
