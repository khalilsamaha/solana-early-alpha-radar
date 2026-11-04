// Pure three-generation contract validation. No keys, network or signing.
import fs from 'node:fs';
import {validate,check,text,hash} from './exit_signer_contract.mjs';
const raw=fs.readFileSync(0);check(raw.length<=64*1024*1024);
const source=JSON.parse(raw),copy=v=>JSON.parse(text(v));
const verify=v=>validate(v.data,v.metadata,v.pair,v.requestedHash,v.now);
const current=v=>JSON.parse(v.data.continuationRow.value);
const save=(v,e)=>{v.data.continuationRow={id:1,value:text(e),hash:hash(e)};};
// Rebind the unsigned request and boundary after mutation so constraint tests
// cannot pass merely because the top-level preparation/request hash is stale.
function rebind(v){
 if(v.data.continuationRow==null)return;
 const prep=current(v).continuation,b=prep.binding;
 const row=v.data.signingRows[0],boundary=JSON.parse(row.value);
 const req={...boundary.request,preparationSha256:hash(prep),entryAccountingSha256:b.entryAccountingSha256,
   collectionSha256:b.collectionSha256,messageSha256:b.messageSha256,validUntilExclusiveMs:b.validUntilExclusiveMs,
   quantityAtomic:b.quantityAtomic,feeCapLamports:b.feeCapLamports,packet:prep.evidence.packet};
 boundary.request=req;boundary.requestSha256=hash(req);v.requestedHash=hash(req);
 row.value=text(boundary);row.hash=hash({seq:row.seq,atMs:row.at_ms,value:boundary,previousHash:row.previous_hash});
}
verify(source);
const cases={'valid-continuation-replays-all-three-generations':'passed'};
const mutations={
 'original-lineage-rehashed':(v,e)=>{e.originalPreparationSha256='0'.repeat(64);save(v,e);},
 'previous-lineage-rehashed':(v,e)=>{e.previousPreparationSha256='0'.repeat(64);save(v,e);},
 'previous-generation-removed':v=>{delete v.data.replacementRow;},
 'continuation-removed':v=>{delete v.data.continuationRow;},
 'original-blockhash-reused':(v,e)=>{e.continuation.evidence.packet.policy.blockhash=JSON.parse(v.data.preparationRow.value).evidence.packet.policy.blockhash;save(v,e);},
 'previous-blockhash-reused':(v,e)=>{e.continuation.evidence.packet.policy.blockhash=JSON.parse(v.data.replacementRow.value).replacement.evidence.packet.policy.blockhash;save(v,e);},
 'fee-hold-reduced':(v,e)=>{e.continuation.binding.feeCommitmentRemainingLamports='1';save(v,e);},
 'fee-cap-increased':(v,e)=>{e.continuation.binding.feeCapLamports='10001';save(v,e);},
 'protected-inventory-reduced':(v,e)=>{e.continuation.binding.protectedInventoryAtomic='0';save(v,e);},
 'attempt-budget-reset':(v,e)=>{e.continuation.binding.attemptsConsumed=1;save(v,e);},
 'third-generation-expired':(v,e)=>{v.now=e.continuation.binding.validUntilExclusiveMs;},
 'previous-generation-corrupted-and-rehashed':(v,e)=>{
   const old=JSON.parse(v.data.replacementRow.value);old.replacement.binding.quantityAtomic='1';
   v.data.replacementRow={id:1,value:text(old),hash:hash(old)};
   e.previousPreparationSha256=hash(old.replacement);save(v,e);
 },
 'extra-envelope-field':(v,e)=>{e.retryAllowed=true;save(v,e);}
};
for(const [name,mutate] of Object.entries(mutations)){
 const v=copy(source);mutate(v,current(v));rebind(v);let failed=false;
 try{verify(v);}catch{failed=true;}check(failed);cases[name]='passed';
}
process.stdout.write(text({casesPassed:Object.keys(cases).length,cases,privateKeyAccessed:false,signaturesCreated:0}));
