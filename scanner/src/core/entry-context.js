import {metadataAt,readMetadata} from './metadata-provenance.js';
// Bounded, immutable entry evidence. No requests, scoring, or safety verdicts.
export const ENTRY_CONTEXT_VERSION='entry-context-1';
const defs={liquidityUsd:['liquidityUsd'],organicScore:['organicScore'],top10Pct:['top10Pct'],
 marketCap:['marketCap'],holderCount:['holderCount'],buys5m:['txns','m5','buys'],
 sells5m:['txns','m5','sells'],volume5mUsd:['volume','m5']};
const clockDefs={marketObservedAt:'freshMs',securityCheckedAt:'securityTtlMs',jupiterCheckedAt:null};
const countKeys=new Set(['holderCount','buys5m','sells5m']);
const positiveInt=x=>Number.isSafeInteger(x)&&x>0;
const nonnegative=x=>typeof x==='number'&&Number.isFinite(x)&&x>=0;
const label=x=>typeof x==='string'&&x.length>0&&x.length<=96?x:null;
function numeric(key,x){return nonnegative(x)&&(!countKeys.has(key)||Number.isSafeInteger(x))&&(key!=='top10Pct'||x<=100);}
function field(key,x){return {value:numeric(key,x)?x:null,state:x===null||x===undefined?'absent':numeric(key,x)?'recorded':'invalid'};}
function clock(x,at,ttl){
 const valid=positiveInt(x)&&x<=at,limit=positiveInt(ttl)?ttl:null;
 return {at:valid?x:null,ageMs:valid?at-x:null,ttlMs:limit,
 state:x===null||x===undefined?'absent':!valid?'invalid':limit===null?'age-only':at-x>limit?'stale':'within-ttl'};
}
function derived(values){
 const b=values.buys5m.value,s=values.sells5m.value,v=values.volume5mUsd.value;
 const n=b!==null&&s!==null&&Number.isSafeInteger(b+s)?b+s:null;
 const avg=n>0&&v!==null&&Number.isFinite(v/n)?v/n:null;
 return {transactions5m:n,averageReportedTradeUsd:avg};
}
export function captureEntryContext(c,at,config={}){
 const values=Object.fromEntries(Object.entries(defs).map(([k,p])=>[k,field(k,p.reduce((o,x)=>o?.[x],c))]));
 const clocks=Object.fromEntries(Object.entries(clockDefs).map(([k,ttl])=>[k,clock(c[k],at,config[ttl])]));
 const authorities={};
 for(const key of ['mintAuthority','freezeAuthority'])authorities[key]=c[key]===null?false:typeof c[key]==='string'&&c[key].length>0?true:null;
 return {version:ENTRY_CONTEXT_VERSION,signalAt:at,mint:label(c.mint),pairAddress:label(c.pairAddress),
 values,derived:derived(values),clocks,authorities,
 metadataProvenance:metadataAt(c.metadataProvenance,{organicScore:c.organicScore,holderCount:c.holderCount},at),
 concentrationMethod:c.concentrationMethod==='top10-token-accounts-unadjusted'?c.concentrationMethod:null,
 dexId:label(c.dexId),basis:'scanner-candidate-at-signal; response times are not trade timestamps'};
}
export function readEntryContext(raw,{at,mint,pairAddress}){
 if(raw===null||raw===undefined)return {state:'absent',data:null};
 if(raw.version!==ENTRY_CONTEXT_VERSION||!positiveInt(at)||raw.signalAt!==at||!label(mint)||!label(pairAddress)||raw.mint!==mint||raw.pairAddress!==pairAddress)return {state:'invalid',data:null};
 const values={},clocks={},authorities={};
 for(const key of Object.keys(defs)){
  const x=raw.values?.[key];
  if(!x||!['recorded','absent','invalid'].includes(x.state)||(x.state==='recorded'?!numeric(key,x.value):x.value!==null))return {state:'invalid',data:null};
  values[key]={value:x.value,state:x.state};
 }
 for(const key of Object.keys(clockDefs)){
  const x=raw.clocks?.[key];
  if(!x||!(x.ttlMs===null||positiveInt(x.ttlMs)))return {state:'invalid',data:null};
  if(x.at===null){if(x.ageMs!==null||!['absent','invalid'].includes(x.state))return {state:'invalid',data:null};}
  else {const check=clock(x.at,at,x.ttlMs);if(check.at===null||x.ageMs!==check.ageMs||x.state!==check.state)return {state:'invalid',data:null};}
  clocks[key]={at:x.at,ageMs:x.ageMs,ttlMs:x.ttlMs,state:x.state};
 }
 for(const key of ['mintAuthority','freezeAuthority']){
  const x=raw.authorities?.[key];if(x!==null&&typeof x!=='boolean')return {state:'invalid',data:null};authorities[key]=x;
 }
 return {state:'recorded',data:{version:ENTRY_CONTEXT_VERSION,signalAt:at,mint,pairAddress,values,
 derived:derived(values),clocks,authorities,
 ...(raw.metadataProvenance===undefined?{}:{metadataProvenance:readMetadata(raw.metadataProvenance,{organicScore:values.organicScore.value,holderCount:values.holderCount.value},at)}),
 concentrationMethod:raw.concentrationMethod==='top10-token-accounts-unadjusted'?raw.concentrationMethod:null,
 dexId:label(raw.dexId),basis:'scanner-candidate-at-signal; response times are not trade timestamps'}};
}
