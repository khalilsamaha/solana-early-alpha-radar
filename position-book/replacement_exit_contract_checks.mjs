// Pure contract checks on a synthetic fixture supplied by the offline runner.
// No wallet-file reader, key access, network, signing or transaction sender.
import fs from 'node:fs';
import {validate,check,text,hash} from './exit_signer_contract.mjs';
const input=fs.readFileSync(0);check(input.length<=64*1024*1024);
const source=JSON.parse(input),copy=v=>JSON.parse(text(v));
const verify=v=>validate(v.data,v.metadata,v.pair,v.requestedHash,v.now);
const current=v=>JSON.parse(v.data.replacementRow.value);
function save(v,e){v.data.replacementRow={id:1,value:text(e),hash:hash(e)};}
verify(source);
const cases={'valid-replacement-replays-both-records':'passed'};
const mutations={
 'lineage-rehashed':(v,e)=>{e.originalPreparationSha256='0'.repeat(64);save(v,e);},
 'reused-blockhash-rehashed':(v,e)=>{e.replacement.evidence.packet.policy.blockhash=JSON.parse(v.data.preparationRow.value).evidence.packet.policy.blockhash;save(v,e);},
 'fee-hold-changed-rehashed':(v,e)=>{e.replacement.binding.feeCommitmentRemainingLamports='1';save(v,e);},
 'fee-cap-increased-rehashed':(v,e)=>{e.replacement.binding.feeCapLamports='10001';save(v,e);},
 'inventory-protection-reduced-rehashed':(v,e)=>{e.replacement.binding.protectedInventoryAtomic='0';save(v,e);},
 'premature-replacement-rehashed':(v,e)=>{e.replacement.collection.provenance.startedAtMs=JSON.parse(v.data.preparationRow.value).recordedAtMs;save(v,e);},
 'original-ownership-rehashed':(v,e)=>{const old=JSON.parse(v.data.preparationRow.value);old.binding.quantityAtomic='1';v.data.preparationRow={id:1,value:text(old),hash:hash(old)};e.originalPreparationSha256=hash(old);save(v,e);},
 'replacement-removed':v=>{delete v.data.replacementRow;},
 'current-deadline-expired':(v,e)=>{v.now=e.replacement.binding.validUntilExclusiveMs;}
};
for(const [name,mutate] of Object.entries(mutations)){
 const value=copy(source);mutate(value,current(value));let failed=false;
 try{verify(value);}catch{failed=true;}check(failed);cases[name]='passed';
}
process.stdout.write(text({casesPassed:Object.keys(cases).length,cases}));
