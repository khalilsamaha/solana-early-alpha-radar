// Independent successor generation checks; no files, keys, network or sender.
import crypto from 'node:crypto';
import {raw58} from '../devnet-pool/pool_policy.mjs';
import {check,text,hash,bytesHash,validate as previous,preparation} from './exit_signer_contract.mjs';
export {check,text,hash,bytesHash};
const GENESIS='EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG';
const TOKEN='TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA',SYSTEM='11111111111111111111111111111111';
const fields=(v,ks)=>check(v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join('|')===[...ks].sort().join('|'));
const num=(n,lo=0,hi=Number.MAX_SAFE_INTEGER)=>check(Number.isSafeInteger(n)&&n>=lo&&n<=hi);
const atomic=s=>{check(typeof s==='string'&&/^(0|[1-9][0-9]{0,19})$/.test(s));const n=BigInt(s);check(n<=2n**64n-1n);return n;};
const b58=b=>{const a='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';let n=BigInt('0x'+b.toString('hex')),s='',z=0;while(n){s=a[Number(n%58n)]+s;n/=58n;}while(z<b.length&&b[z]===0)z++;return '1'.repeat(z)+s;};
const base64=s=>{check(typeof s==='string');const b=Buffer.from(s,'base64');check(b.toString('base64')===s);return b;};
function record(row,cap){check(row&&row.id===1&&typeof row.value==='string'&&Buffer.byteLength(row.value)<=cap);const v=JSON.parse(row.value);check(text(v)===row.value&&hash(v)===row.hash);return v;}
function rows(items,now,cap){check(items.length>0&&items.length<=cap);let prev='',stamp=0;return items.map((r,i)=>{num(r.at_ms,stamp,now);check(r.seq===i+1&&typeof r.value==='string'&&Buffer.byteLength(r.value)<=12288);const v=JSON.parse(r.value);check(text(v)===r.value&&r.previous_hash===prev&&r.hash===hash({seq:r.seq,atMs:r.at_ms,value:v,previousHash:prev}));prev=r.hash;stamp=r.at_ms;return v;});}
const received=i=>{fields(i,['state','result']);check(i.state==='received');return i.result;};
function account(row,owner,size){check(row&&row.owner===owner&&row.executable===false&&Array.isArray(row.data)&&row.data.length===2&&row.data[1]==='base64');num(row.lamports);const raw=base64(row.data[0]);check(raw.length===size);return raw;}
function project(row){check(row&&typeof row==='object');return Object.fromEntries(['owner','executable','lamports','data'].map(k=>[k,row[k]]));}
function scopedAccounts(items,keys,amounts){
 check(items.length===5);account(items[0],SYSTEM,0);check(BigInt(items[0].lamports)>=atomic(amounts.feeHeldLamports));
 for(let i=1;i<=2;i++){
  const b=account(items[i],TOKEN,165);check(b.subarray(0,32).equals(raw58(keys[i+2]))&&b.subarray(32,64).equals(raw58(keys[0])));
  check(b[108]===1&&b.readUInt32LE(72)===0&&b.readBigUInt64LE(121)===0n&&b.readUInt32LE(129)===0);
  if(i===2)check(b.readBigUInt64LE(64)>=atomic(amounts.ownedAcquiredHeldAtomic)+atomic(amounts.protectedAcquiredInventoryAtomic));
 }
 for(const row of items.slice(3)){const b=account(row,TOKEN,82);check(b[45]===1);}
}
function proof(ev,ctx,start,observed,now){
 fields(ev,['genesisBefore','validity','height','status','transaction','accounts','blockTime','genesisAfter']);
 num(start,1,observed);num(observed,start,now);check(observed-start<=120000);
 check(received(ev.genesisBefore)===GENESIS&&received(ev.genesisAfter)===GENESIS);
 const validity=received(ev.validity),status=received(ev.status),accounts=received(ev.accounts);
 check(validity.value===false);num(validity.context.slot,ctx.identity.minimumContextSlot);
 num(status.context.slot,ctx.identity.minimumContextSlot);check(Array.isArray(status.value)&&status.value.length===1&&status.value[0]===null);
 check(received(ev.transaction)===null);const height=received(ev.height);num(height,ctx.lastValidBlockHeight+1);
 num(accounts.context.slot,status.context.slot);check(Array.isArray(accounts.value));
 const blockTime=received(ev.blockTime);num(blockTime);check(now-30000<=blockTime*1000&&blockTime*1000<=now+2000);
 scopedAccounts(accounts.value,ctx.accountKeys,ctx.identity.scopedAccounting);
 check(text(accounts.value.map(project))===text(ctx.expectedAccounts.map(project)));
 return {blockSlot:validity.context.slot,statusSlot:status.context.slot,accountSlot:accounts.context.slot,blockTime,height};
}
function signedWire(wire,message,wallet){const b=base64(wire);check(b.length<=1232&&b[0]===1&&b.subarray(65).equals(message));const pub=crypto.createPublicKey({key:Buffer.concat([Buffer.from('302a300506032b6570032100','hex'),raw58(wallet)]),format:'der',type:'spki'});check(crypto.verify(null,message,pub,b.subarray(1,65)));return {hash:bytesHash(b),signature:b58(b.subarray(1,65))};}

export function validate(data,metadata,pair,requestedHash,now){
 check(typeof requestedHash==='string'&&/^[a-f0-9]{64}$/.test(requestedHash));num(now,1);
 const oldRows=rows(data.signingRows,now,2);check(oldRows.length===2);
 const oldReq=oldRows[0].request;
 const old=previous({...data,signingRows:data.signingRows.slice(0,1)},metadata,pair,hash(oldReq),data.signingRows[0].at_ms);
 fields(oldRows[1],['state','signedWireBase64','wireSha256','signature']);check(oldRows[1].state==='exit-signed-recorded');
 const checkedWire=signedWire(oldRows[1].signedWireBase64,old.message,old.wallet);
 check(oldRows[1].wireSha256===checkedWire.hash&&oldRows[1].signature===checkedWire.signature);
 const olds=[record(data.preparationRow,24*1024*1024+16384)];
 if(data.replacementRow)olds.push(record(data.replacementRow,24*1024*1024+18432).replacement);
 if(data.continuationRow)olds.push(record(data.continuationRow,24*1024*1024+20480).continuation);
 const parent=olds.at(-1);check(hash(parent)===oldReq.preparationSha256);
 const state=rows(data.admissionRows,now,8).at(-1),entry=record(data.accountingRow,8192),a=entry.accounting;
 const x=parent.evidence,minimum=Math.max(x.simulationItem.result.context.slot,x.capture.evidence.accounts.result.context.slot,x.price.quote.contextSlot);
 num(minimum,1);for(const n of [x.simulationItem.result.context.slot,x.capture.evidence.accounts.result.context.slot,x.price.quote.contextSlot])num(n,1);
 const oldState={state:'exit-signed-recorded',request:oldReq,requestSha256:hash(oldReq),admissionHeadSha256:oldRows[0].admissionHeadSha256,
  eventCount:2,headSha256:data.signingRows[1].hash,lastAtMs:data.signingRows[1].at_ms,signed:oldRows[1],minimumContextSlot:minimum};
 const oldAttempt=data.oldAttempt,oldAck=data.oldAck;
 fields(oldAttempt,['format','requestSha256','signingHeadSha256','preparationSha256','atMs']);
 check(oldAttempt.format==='exit-signer-attempt-1'&&oldAttempt.requestSha256===hash(oldReq)&&oldAttempt.signingHeadSha256===data.signingRows[0].hash&&oldAttempt.preparationSha256===hash(parent));
 num(oldAttempt.atMs,data.signingRows[0].at_ms,Math.min(now,oldReq.validUntilExclusiveMs-1));
 fields(oldAck,['format','requestSha256','signedTransactionBase64','wireSha256']);
 check(oldAck.format==='exit-signer-ack-1'&&oldAck.requestSha256===hash(oldReq)&&oldAck.signedTransactionBase64===oldRows[1].signedWireBase64&&oldAck.wireSha256===checkedWire.hash);
 const amounts={sourcePrincipalHeldAtomic:a.sourcePrincipalHeldAtomic,sourcePrincipalSpentAtomic:a.sourcePrincipalSpentAtomic,sourceProceedsHeldAtomic:'0',
  ownedAcquiredHeldAtomic:a.ownedAcquiredAtomic,protectedAcquiredInventoryAtomic:a.preexistingDestinationAtomic,
  feeHeldLamports:a.feeCommitmentRemainingLamports,feePaidLamports:a.entryFeePaidLamports,sourceProceedsReleasedAtomic:'0',unusedFeeReleasedLamports:'0',
  protectedInventoryReleasedAtomic:'0',scopedClosureRecorded:false,basis:'entry-settled-exit-not-settled'};
 const accounts=data.policy.scope.accounts,keys=[accounts.wallet,accounts.source,accounts.destination,accounts.inputMint,accounts.outputMint];
 check(new Set(keys).size===5);const saved=new Map(x.capture.accountKeys.map((k,i)=>[k,x.capture.evidence.accounts.result.value[i]]));
 const ctx={identity:{preparationSha256:hash(parent),signingStateSha256:hash(oldState),signature:checkedWire.signature,blockhash:oldReq.packet.policy.blockhash,minimumContextSlot:minimum,scopedAccounting:amounts},
  accountKeys:keys,expectedAccounts:keys.map(k=>saved.get(k)),lastValidBlockHeight:parent.collection.packetBuild.lastValidBlockHeight,signedWire:oldRows[1].signedWireBase64};
 num(ctx.lastValidBlockHeight,1);scopedAccounts(ctx.expectedAccounts,keys,amounts);
 const retired=record(data.retirementRow,65536),next=record(data.successorRow,25*1024*1024);
 fields(retired,['format','recordedAtMs','preparationSha256','contextSha256','startedAtMs','observedAtMs','rpcEvidence']);
 check(retired.format==='held-exit-retirement-1'&&retired.preparationSha256===hash(parent)&&retired.contextSha256===hash(ctx));
 num(retired.recordedAtMs,Math.max(oldReq.validUntilExclusiveMs,oldState.lastAtMs),now);check(retired.recordedAtMs-retired.observedAtMs<=10000);
 const earlier=proof(retired.rpcEvidence,ctx,retired.startedAtMs,retired.observedAtMs,retired.recordedAtMs);
 fields(next,['format','recordedAtMs','contextSha256','retirementSha256','retiredPreparationSha256','expiryProof','candidate']);
 check(next.format==='retired-exit-successor-1'&&next.contextSha256===hash(ctx)&&next.retirementSha256===hash(retired)&&next.retiredPreparationSha256===hash(parent));
 num(next.recordedAtMs,retired.recordedAtMs,now);
 const fresh=next.expiryProof;fields(fresh,['contextSha256','startedAtMs','observedAtMs','rpcEvidence']);
 check(fresh.contextSha256===hash(ctx));num(fresh.startedAtMs,retired.recordedAtMs,fresh.observedAtMs);num(fresh.observedAtMs,fresh.startedAtMs,next.recordedAtMs);
 check(now-fresh.observedAtMs<=30000);
 const later=proof(fresh.rpcEvidence,ctx,fresh.startedAtMs,fresh.observedAtMs,now);
 for(const k of Object.keys(earlier))check(later[k]>=earlier[k]);
 const c=next.candidate;fields(c,['format','evidence','collection','binding']);check(c.format==='retired-exit-successor-1-unsigned');
 const b=c.binding;check(b.attemptNumber===2&&b.attemptsConsumed===1&&data.policy.maximumExitAttempts>=2&&b.additionalFeeReservationLamports==='0');
 check(b.retirementSha256===hash(retired)&&b.retiredPreparationSha256===hash(parent));
 const cap=atomic(b.feeCapLamports),oldCap=atomic(parent.binding.feeCapLamports),held=atomic(amounts.feeHeldLamports);
 check(cap>0n&&cap<=oldCap&&held>=oldCap+cap&&b.retiredFeeExposureHeldLamports===String(oldCap)&&b.otherHeldFeeLamports===String(held-cap));
 check(atomic(b.protectedInventoryAtomic)>=atomic(amounts.protectedAcquiredInventoryAtomic));
 check(olds.every(p=>p.evidence.packet.policy.blockhash!==c.evidence.packet.policy.blockhash));
 num(c.collection.provenance.startedAtMs,fresh.observedAtMs,next.recordedAtMs);
 num(c.evidence.capture.evidence.accounts.result.context.slot,later.accountSlot);
 const captured=new Map(c.evidence.capture.accountKeys.map((k,i)=>[k,c.evidence.capture.evidence.accounts.result.value[i]]));
 check(text(keys.map(k=>project(captured.get(k))))===text(ctx.expectedAccounts.map(project)));
 const boundary=rows(data.successorSigningRows,now,1)[0];
 fields(boundary,['state','request','requestSha256','admissionHeadSha256']);check(boundary.state==='successor-signing-unknown'&&boundary.admissionHeadSha256===data.admissionRows.at(-1).hash);
 const req=boundary.request,expected={format:'successor-signing-handoff-1-request',successorSha256:hash(next),retirementSha256:hash(retired),retiredPreparationSha256:hash(parent),contextSha256:hash(ctx),
  entryAccountingSha256:b.entryAccountingSha256,collectionSha256:b.collectionSha256,messageSha256:b.messageSha256,validUntilExclusiveMs:b.validUntilExclusiveMs,
  quantityAtomic:b.quantityAtomic,protectedInventoryAtomic:b.protectedInventoryAtomic,feeCapLamports:b.feeCapLamports,feeCommitmentRemainingLamports:b.feeCommitmentRemainingLamports,
  retiredFeeExposureHeldLamports:b.retiredFeeExposureHeldLamports,additionalFeeReservationLamports:'0',attemptNumber:2,attemptsConsumed:1,packet:c.evidence.packet};
 check(text(req)===text(expected)&&hash(req)===requestedHash&&boundary.requestSha256===requestedHash);
 const at=data.successorSigningRows[0].at_ms;num(at,next.recordedAtMs,b.validUntilExclusiveMs-1);
 // A private validation view reuses the independent instruction compiler. It is
 // never saved or accepted as the actual successor/request identity above.
 const view={format:'retired-exit-successor-1-signing-view',recordedAtMs:next.recordedAtMs,evidence:c.evidence,collection:c.collection,binding:b};
 const out=preparation(view,entry,data.policy,state,metadata,pair,{...req,preparationSha256:hash(view)},now,at,2);
 return {...out,preparationHash:hash(next),retirementHash:hash(retired),retiredPreparationHash:hash(parent),notBeforeMs:at,
  requestHash:requestedHash,signingHead:data.successorSigningRows[0].hash};
}
