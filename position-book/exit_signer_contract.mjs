// Independent restricted exit contract. No filesystem, keys, RPC or sender.
import {addresses} from '../devnet-pool/pool_policy.mjs';
import {check,text,hash,bytesHash,compile,roles} from './admission_signer_contract.mjs';
export {check,text,hash,bytesHash};
const fields=(v,ks)=>check(v && !Array.isArray(v) && Object.keys(v).sort().join('|')===[...ks].sort().join('|'));
const num=(n,lo,hi)=>check(Number.isSafeInteger(n)&&n>=lo&&n<=hi);
const atomic=s=>{check(typeof s==='string'&&/^(0|[1-9][0-9]{0,19})$/.test(s));const n=BigInt(s);check(n<=2n**64n-1n);return n;};
const stable=['network','accounts','amountIn','minimumAmountOut','maxComputeUnits','maxMicroLamportsPerCU','maxPriorityFeeLamports','maxTotalFeeLamports'];
const GENESIS='EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG';
function rows(values,now,limit){
  check(values.length>0&&values.length<=limit);let previous='',last=0;
  return values.map((r,i)=>{
    num(r.at_ms,last,now);check(r.seq===i+1&&typeof r.value==='string'&&r.value.length<=8192);
    const v=JSON.parse(r.value);check(text(v)===r.value&&r.previous_hash===previous);
    check(r.hash===hash({seq:r.seq,atMs:r.at_ms,value:v,previousHash:previous}));
    previous=r.hash;last=r.at_ms;return v;
  });
}
function record(row,max){
  check(row&&row.id===1&&typeof row.value==='string'&&Buffer.byteLength(row.value)<=max);
  const v=JSON.parse(row.value);check(text(v)===row.value&&hash(v)===row.hash);return v;
}
export function validate(data,metadata,pair,requestedHash,now){
  check(typeof requestedHash==='string'&&/^[a-f0-9]{64}$/.test(requestedHash));
  const {policy,admissionRows,signingRows,preparationRow,accountingRow}=data;
  const states=rows(admissionRows,now,8),s=states.at(-1),boundary=rows(signingRows,now,1)[0];
  check(s.state==='signed-recorded'&&states.every(v=>v.policySha256===hash(policy)));
  fields(boundary,['state','request','requestSha256','admissionHeadSha256']);
  check(boundary.state==='exit-signing-unknown'&&boundary.admissionHeadSha256===admissionRows.at(-1).hash);
  const req=boundary.request;fields(req,['format','preparationSha256','entryAccountingSha256','collectionSha256','messageSha256','validUntilExclusiveMs','quantityAtomic','feeCapLamports','packet']);
  check(req.format==='exit-signing-handoff-1-request'&&hash(req)===requestedHash&&boundary.requestSha256===requestedHash);
  const original=record(preparationRow,24*1024*1024+16384),entry=record(accountingRow,8192);
  let prep=original;
  if(data.replacementRow != null){
    const envelope=record(data.replacementRow,24*1024*1024+16384+2048);
    fields(envelope,['format','originalPreparationSha256','replacement']);
    check(envelope.format==='unsigned-exit-replacement-1-record' && envelope.originalPreparationSha256===hash(original));
    // Replay the original at persistence time; expiry today cannot erase its contract.
    const b=original.binding;
    const historical={format:'exit-signing-handoff-1-request',preparationSha256:hash(original),
      entryAccountingSha256:b.entryAccountingSha256,collectionSha256:b.collectionSha256,
      messageSha256:b.messageSha256,validUntilExclusiveMs:b.validUntilExclusiveMs,
      quantityAtomic:b.quantityAtomic,feeCapLamports:b.feeCapLamports,packet:original.evidence.packet};
    preparation(original,entry,policy,s,metadata,pair,historical,original.recordedAtMs,original.recordedAtMs);
    prep=envelope.replacement;
    check(Buffer.byteLength(text(prep))<=24*1024*1024+16384);
    const next=prep.binding,start=prep.collection.provenance.startedAtMs;
    num(start,b.validUntilExclusiveMs,prep.recordedAtMs);
    num(prep.recordedAtMs,start,next.validUntilExclusiveMs-1);
    for(const k of ['entryAccountingSha256','entryReceiptIdentity','quantityAtomic','feeCommitmentRemainingLamports','attemptNumber','attemptsConsumed'])
      check(next[k]===b[k]);
    check(atomic(next.feeCapLamports)<=atomic(b.feeCapLamports) && atomic(next.protectedInventoryAtomic)>=atomic(b.protectedInventoryAtomic));
    check(prep.evidence.packet.policy.blockhash!==original.evidence.packet.policy.blockhash);
    num(prep.evidence.price.quote.contextSlot,original.evidence.price.quote.contextSlot,Number.MAX_SAFE_INTEGER);
  }
  if(data.continuationRow != null){
    check(data.replacementRow != null);
    const envelope=record(data.continuationRow,24*1024*1024+16384+4096);
    fields(envelope,['format','originalPreparationSha256','previousPreparationSha256','continuation']);
    check(envelope.format==='unsigned-exit-continuation-1-record' &&
      envelope.originalPreparationSha256===hash(original) && envelope.previousPreparationSha256===hash(prep));
    const previous=prep,b=previous.binding;
    const historical={format:'exit-signing-handoff-1-request',preparationSha256:hash(previous),
      entryAccountingSha256:b.entryAccountingSha256,collectionSha256:b.collectionSha256,
      messageSha256:b.messageSha256,validUntilExclusiveMs:b.validUntilExclusiveMs,
      quantityAtomic:b.quantityAtomic,feeCapLamports:b.feeCapLamports,packet:previous.evidence.packet};
    preparation(previous,entry,policy,s,metadata,pair,historical,previous.recordedAtMs,previous.recordedAtMs);
    prep=envelope.continuation;
    check(Buffer.byteLength(text(prep))<=24*1024*1024+16384);
    for(const prior of [original,previous]){
      const old=prior.binding,next=prep.binding,start=prep.collection.provenance.startedAtMs;
      num(start,old.validUntilExclusiveMs,prep.recordedAtMs);
      num(prep.recordedAtMs,start,next.validUntilExclusiveMs-1);
      for(const k of ['entryAccountingSha256','entryReceiptIdentity','quantityAtomic','feeCommitmentRemainingLamports','attemptNumber','attemptsConsumed'])
        check(next[k]===old[k]);
      check(atomic(next.feeCapLamports)<=atomic(old.feeCapLamports) && atomic(next.protectedInventoryAtomic)>=atomic(old.protectedInventoryAtomic));
      check(prep.evidence.packet.policy.blockhash!==prior.evidence.packet.policy.blockhash);
      num(prep.evidence.price.quote.contextSlot,prior.evidence.price.quote.contextSlot,Number.MAX_SAFE_INTEGER);
    }
  }
  const result=preparation(prep,entry,policy,s,metadata,pair,req,now,signingRows[0].at_ms);
  return {...result,notBeforeMs:signingRows[0].at_ms,requestHash:requestedHash,signingHead:signingRows[0].hash};
}

function preparation(prep,entry,policy,s,metadata,pair,req,now,signingAtMs){
  fields(prep,['format','recordedAtMs','evidence','binding','collection']);
  fields(entry,['format','recordedAtMs','accounting']);
  check(prep.format==='admission-exit-collection-1-record'&&hash(prep)===req.preparationSha256);
  check(entry.format==='admission-entry-accounting-1-record'&&hash(entry)===req.entryAccountingSha256);
  num(entry.recordedAtMs,1,prep.recordedAtMs);num(prep.recordedAtMs,1,signingAtMs);
  const b=prep.binding,a=entry.accounting,c=prep.collection,p=c.provenance;
  check(b.entryAccountingSha256===hash(entry)&&b.collectionSha256===hash(c)&&hash(c)===req.collectionSha256);
  check(p.identity.admissionStateSha256===hash(s)&&p.identity.entryAccountingSha256===hash(entry));
  check(b.evidenceSha256===hash(prep.evidence)&&p.evidenceSha256===hash(prep.evidence));
  for(const [k,v] of [['initialCaptureSha256',c.initialCapture],['packetBuildSha256',c.packetBuild],['requestTraceSha256',c.requestTrace],['finalGenesisSha256',c.finalGenesis]])check(p[k]===hash(v));
  check(c.finalGenesis.state==='received'&&c.finalGenesis.result===GENESIS&&p.networkRequests===20&&c.requestTrace.length===20);
  check(a.format==='admission-entry-accounting-1'&&a.state==='entry-position-open'&&a.owner==='same-admission-ledger'&&a.exitAttemptsConsumed===0);
  check(a.policySha256===hash(policy)&&a.handoffSha256===s.accountingHandoffSha256&&a.wireSha256===s.signedWireSha256);
  check(b.entryReceiptIdentity===a.receiptIdentity&&b.attemptNumber===1&&b.attemptsConsumed===0);
  const held=atomic(a.feeCommitmentRemainingLamports),feeCap=atomic(req.feeCapLamports);
  check(atomic(a.originalFeeCommitmentLamports)===atomic(s.reservedFeeLamports)&&atomic(a.entryFeePaidLamports)>0n&&
    held+atomic(a.entryFeePaidLamports)===atomic(s.reservedFeeLamports));
  check(atomic(s.reservedFeeLamports)===atomic(policy.scope.maxTotalFeeLamports)+BigInt(policy.maximumExitAttempts)*atomic(policy.maximumExitFeeLamports)&&atomic(s.reservedFeeLamports)<=atomic(policy.maximumTotalFeeLamports));
  check(held>=atomic(a.exitAttemptFeeHeldLamports)&&atomic(a.exitAttemptFeeHeldLamports)===BigInt(policy.maximumExitAttempts)*atomic(policy.maximumExitFeeLamports));
  check(feeCap>0n&&feeCap<=atomic(policy.maximumExitFeeLamports)&&feeCap<=10000n&&held>=feeCap);
  check(b.feeCapLamports===req.feeCapLamports&&b.feeCommitmentRemainingLamports===String(held)&&b.otherFeeCommitmentsHeldLamports===String(held-feeCap));
  check(req.quantityAtomic===a.ownedAcquiredAtomic&&req.quantityAtomic===b.quantityAtomic&&atomic(req.quantityAtomic)>0n);
  check(metadata.format==='devnet-wallet-1'&&metadata.network==='devnet'&&metadata.purpose==='fixed-self-transfer-rehearsal');
  const derived=addresses(pair),entryMap={source:'holder0',destination:'holder1',inputVault:'vault0',outputVault:'vault1',inputMint:'mint0',outputMint:'mint1'};
  check(policy.format==='pre-sign-admission-1-policy'&&policy.scope.network==='devnet');
  num(policy.maximumExitAttempts,1,3);check(atomic(policy.maximumTotalFeeLamports)<=40000n);
  check(roles.every(k=>policy.scope.accounts[k]===derived[entryMap[k]||k]));
  const expected=JSON.parse(text(policy.scope));
  for(const [l,r] of [['source','destination'],['inputMint','outputMint'],['inputVault','outputVault']])
    [expected.accounts[l],expected.accounts[r]]=[expected.accounts[r],expected.accounts[l]];
  const packet=req.packet;fields(packet,['format','policy','unsignedTransactionBase64','feeAssertion']);
  const q=packet.policy;fields(q,['format','issuedAtMs','expiresAtMs','blockhash',...stable]);
  check(packet.format==='unsigned-cpmm-contract-1'&&q.format==='cpmm-instruction-policy-1'&&text(packet)===text(prep.evidence.packet));
  expected.amountIn=req.quantityAtomic;expected.minimumAmountOut=q.minimumAmountOut;expected.maxTotalFeeLamports=req.feeCapLamports;
  check(stable.every(k=>text(q[k])===text(expected[k]))&&hash(expected)===b.scopeSha256);
  check(metadata.wallet===q.accounts.wallet&&a.wallet===q.accounts.wallet&&a.acquiredAccount===q.accounts.source&&a.sourceAccount===q.accounts.destination&&a.acquiredMint===q.accounts.inputMint&&a.sourceMint===q.accounts.outputMint);
  check(q.blockhash!==s.signingRequest.packet.policy.blockhash);
  num(q.issuedAtMs,entry.recordedAtMs,prep.recordedAtMs);num(q.expiresAtMs,now+1,q.issuedAtMs+15000);
  check(req.validUntilExclusiveMs===b.validUntilExclusiveMs&&req.validUntilExclusiveMs===p.validUntilExclusiveMs);
  num(req.validUntilExclusiveMs,now+1,Math.min(q.expiresAtMs,p.startedAtMs+10000));
  const built=compile(expected,q.blockhash),fee=packet.feeAssertion;
  check(built.unsigned===packet.unsignedTransactionBase64&&bytesHash(built.message)===req.messageSha256&&b.messageSha256===req.messageSha256);
  fields(fee,['format','network','messageSha256','observedAtMs','lamports']);
  check(fee.format==='message-fee-assertion-1'&&fee.network==='devnet'&&fee.messageSha256===req.messageSha256&&fee.lamports===b.observedFeeLamports);
  num(fee.observedAtMs,q.issuedAtMs,prep.recordedAtMs);check(now-fee.observedAtMs<=10000&&atomic(fee.lamports)>0n&&atomic(fee.lamports)<=feeCap);
  return {message:built.message,wallet:q.accounts.wallet,deadline:req.validUntilExclusiveMs,preparationHash:hash(prep)};
}
