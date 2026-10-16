// Per-field receipt provenance only. Never sets jupiterCheckedAt or changes eligibility.
export const METADATA_VERSION='metadata-provenance-1';
export const METADATA_KEYS=['organicScore','holderCount'];
const sources=new Set(['jupiter:recent','jupiter:top-organic','jupiter:search']);
const time=x=>Number.isSafeInteger(x)&&x>0;
const number=(k,x)=>typeof x==='number'&&Number.isFinite(x)&&x>=0&&(k!=='holderCount'||Number.isSafeInteger(x));
const valid=(p,k,v,at)=>p&&number(k,p.value)&&p.value===v&&sources.has(p.source)&&time(p.receivedAt)&&time(p.appliedAt)&&p.receivedAt<=p.appliedAt&&p.appliedAt<=at;
export function recordMetadata(previous,patch,receipt,appliedAt){
 const fields={};
 for(const k of METADATA_KEYS){
  if(Object.hasOwn(patch,k)){
   const row={value:patch[k],source:receipt?.source,receivedAt:receipt?.receivedAt,appliedAt};
   if(valid(row,k,patch[k],appliedAt))fields[k]=row;
  }else{
   const p=previous?.metadataProvenance?.version===METADATA_VERSION?previous.metadataProvenance.fields?.[k]:null;
   if(valid(p,k,previous?.[k],appliedAt))fields[k]={value:p.value,source:p.source,receivedAt:p.receivedAt,appliedAt:p.appliedAt};
  }
 }
 return {version:METADATA_VERSION,fields};
}
export function metadataAt(raw,values,at){
 const fields={};
 for(const k of METADATA_KEYS){
  const p=raw?.version===METADATA_VERSION?raw.fields?.[k]:null;
  const good=valid(p,k,values[k],at);
  fields[k]=good?{state:'recorded',value:p.value,source:p.source,receivedAt:p.receivedAt,appliedAt:p.appliedAt,ageMs:at-p.receivedAt}
   :{state:p?'invalid':'not-recorded',value:null,source:null,receivedAt:null,appliedAt:null,ageMs:null};
 }
 return {version:METADATA_VERSION,fields,basis:'local response processing time; not provider measurement time or freshness approval'};
}
export function readMetadata(raw,values,at){
 if(raw===undefined||raw===null)return null;
 const result=metadataAt(raw,values,at);
 for(const k of METADATA_KEYS){
  const p=raw.fields?.[k],out=result.fields[k];
  if(raw.version!==METADATA_VERSION||!p||!['recorded','not-recorded','invalid'].includes(p.state)
   ||(p.state==='recorded'&&(out.state!=='recorded'||p.ageMs!==out.ageMs))
   ||(p.state!=='recorded'&&['value','source','receivedAt','appliedAt','ageMs'].some(x=>p[x]!==null))){
   result.fields[k]={state:'invalid',value:null,source:null,receivedAt:null,appliedAt:null,ageMs:null};
  }else if(p.state!=='recorded')result.fields[k]={state:p.state,value:null,source:null,receivedAt:null,appliedAt:null,ageMs:null};
 }
 return result;
}
