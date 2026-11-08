// Disposable-key backend exercise; never accepts an existing wallet directory.
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import crypto from 'node:crypto';
import {spawnSync,spawn} from 'node:child_process';import {fileURLToPath} from 'node:url';import {DatabaseSync} from 'node:sqlite';
import {addresses} from '../devnet-pool/pool_policy.mjs';
import {check,text,hash,bytesHash,compile,roles} from './admission_signer_contract.mjs';
import {validate} from './successor_signer_contract.mjs';
const HERE=path.dirname(fileURLToPath(import.meta.url)),GENESIS='EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG';
const alpha='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
const b58=b=>{let n=BigInt('0x'+b.toString('hex')),s='',z=0;while(n){s=alpha[Number(n%58n)]+s;n/=58n;}while(z<b.length&&b[z]===0)z++;return '1'.repeat(z)+s;};
const copy=v=>JSON.parse(text(v)),write=(p,v)=>fs.writeFileSync(p,Buffer.isBuffer(v)||typeof v==='string'?v:text(v),{mode:0o600,flag:'wx'});
const top=fs.mkdtempSync(path.join(os.tmpdir(),'radar-exit-signer-'));fs.chmodSync(top,0o700);
let der,wrongDer;
try{
 const key=crypto.generateKeyPairSync('ed25519'),wrong=crypto.generateKeyPairSync('ed25519');
 der=key.privateKey.export({format:'der',type:'pkcs8'});wrongDer=wrong.privateKey.export({format:'der',type:'pkcs8'});
 const pair={wallet:b58(key.publicKey.export({format:'der',type:'spki'}).subarray(12)),mintA:b58(Buffer.alloc(32,11)),holderA:b58(Buffer.alloc(32,13)),mintB:b58(Buffer.alloc(32,12)),holderB:b58(Buffer.alloc(32,14))};
 const derived=addresses(pair),map={source:'holder0',destination:'holder1',inputVault:'vault0',outputVault:'vault1',inputMint:'mint0',outputMint:'mint1'};
 let index=0;
 function fixture(){
  const now=Date.now()-60000,root=path.join(top,'source-'+index++),storage=root+'-entry-handoff-v1';
  fs.mkdirSync(root,{mode:0o700});fs.mkdirSync(storage,{mode:0o700});fs.mkdirSync(path.join(root,'controlled-pool-v1'),{mode:0o700});
  const scope={format:'devnet-swap-scope-1',network:'devnet',accounts:Object.fromEntries(roles.map(k=>[k,derived[map[k]||k]])),amountIn:'1000',minimumAmountOut:'990',maxComputeUnits:300000,maxMicroLamportsPerCU:'0',maxPriorityFeeLamports:'0',maxTotalFeeLamports:'10000'};
  const policy={format:'pre-sign-admission-1-policy',scope,maximumExitAttempts:2,maximumExitFeeLamports:'10000',maximumTotalFeeLamports:'40000'};
  const state={state:'signed-recorded',policySha256:hash(policy),reservedFeeLamports:'30000',accountingHandoffSha256:'a'.repeat(64),signedWireSha256:'b'.repeat(64),signingRequest:{packet:{policy:{blockhash:b58(Buffer.alloc(32,18))}}}};
  const a={format:'admission-entry-accounting-1',state:'entry-position-open',owner:'same-admission-ledger',exitAttemptsConsumed:0,
    policySha256:hash(policy),handoffSha256:state.accountingHandoffSha256,wireSha256:state.signedWireSha256,receiptIdentity:'c'.repeat(64),
    wallet:pair.wallet,sourceAccount:scope.accounts.source,acquiredAccount:scope.accounts.destination,sourceMint:scope.accounts.inputMint,acquiredMint:scope.accounts.outputMint,
    originalFeeCommitmentLamports:'30000',entryFeePaidLamports:'5000',feeCommitmentRemainingLamports:'25000',exitAttemptFeeHeldLamports:'20000',ownedAcquiredAtomic:'996'};
  const entry={format:'admission-entry-accounting-1-record',recordedAtMs:now,accounting:a};
  const reverse=copy(scope);for(const [l,r] of [['source','destination'],['inputMint','outputMint'],['inputVault','outputVault']])[reverse.accounts[l],reverse.accounts[r]]=[reverse.accounts[r],reverse.accounts[l]];
  reverse.amountIn='996';reverse.minimumAmountOut='980';
  const q={...copy(reverse),format:'cpmm-instruction-policy-1',blockhash:b58(Buffer.alloc(32,19)),issuedAtMs:now,expiresAtMs:now+15000};
  const built=compile(reverse,q.blockhash),packet={format:'unsigned-cpmm-contract-1',policy:q,unsignedTransactionBase64:built.unsigned,feeAssertion:{format:'message-fee-assertion-1',network:'devnet',messageSha256:bytesHash(built.message),observedAtMs:now,lamports:'5000'}};
  const evidence={packet};
  const collection={initialCapture:{fixture:'initial'},packetBuild:{fixture:'packet'},requestTrace:Array.from({length:20},(_,i)=>({index:i})),finalGenesis:{state:'received',result:GENESIS},provenance:{identity:{admissionStateSha256:hash(state),entryAccountingSha256:hash(entry)},networkRequests:20,startedAtMs:now,validUntilExclusiveMs:now+10000,evidenceSha256:hash(evidence)}};
  const prep={format:'admission-exit-collection-1-record',recordedAtMs:now,evidence,collection,binding:{entryAccountingSha256:hash(entry),collectionSha256:'',entryReceiptIdentity:a.receiptIdentity,evidenceSha256:hash(evidence),attemptNumber:1,attemptsConsumed:0,quantityAtomic:'996',feeCapLamports:'10000',feeCommitmentRemainingLamports:'25000',otherFeeCommitmentsHeldLamports:'15000',messageSha256:bytesHash(built.message),scopeSha256:hash(reverse),validUntilExclusiveMs:now+10000,observedFeeLamports:'5000'}};
  const req={format:'exit-signing-handoff-1-request',preparationSha256:'',entryAccountingSha256:hash(entry),collectionSha256:'',messageSha256:bytesHash(built.message),validUntilExclusiveMs:now+10000,quantityAtomic:'996',feeCapLamports:'10000',packet};
  write(path.join(root,'wallet.json'),{format:'devnet-wallet-1',network:'devnet',purpose:'fixed-self-transfer-rehearsal',wallet:pair.wallet});write(path.join(root,'signer.pk8'),der);
  write(path.join(root,'controlled-pool-v1','plan.json'),{format:'devnet-pool-intent-1',network:'devnet',genesis:GENESIS,pairAccounts:pair});
  return {root,storage,now,policy,state,entry,prep,req,built};
 }
 function ledger(f,alter=()=>{}){
  const c=f.prep.collection,p=c.provenance;
  for(const [k,v] of [['initialCaptureSha256',c.initialCapture],['packetBuildSha256',c.packetBuild],['requestTraceSha256',c.requestTrace],['finalGenesisSha256',c.finalGenesis]])p[k]=hash(v);
  f.prep.binding.collectionSha256=hash(c);f.req.collectionSha256=hash(c);f.req.preparationSha256=hash(f.prep);
  const row=(seq,value,previous='')=>({seq,at_ms:f.now,value:text(value),previous_hash:previous,hash:hash({seq,atMs:f.now,value,previousHash:previous})});
  const admission=[row(1,f.state)],signing=[row(1,{state:'exit-signing-unknown',request:f.req,requestSha256:hash(f.req),admissionHeadSha256:admission[0].hash})];alter(admission,signing);
  const file=path.join(f.storage,'entry.admission.sqlite');write(file,'');const db=new DatabaseSync(file);
  try{db.exec('PRAGMA application_id=1380534833;PRAGMA user_version=1;CREATE TABLE intents(id);CREATE TABLE events(id);CREATE TABLE admission_policy(id,value);CREATE TABLE admission_events(seq,at_ms,value,previous_hash,hash);CREATE TABLE admission_exit_signing(seq,at_ms,value,previous_hash,hash);CREATE TABLE admission_entry_accounting(id,value,hash);CREATE TABLE admission_exit_preparation(id,value,hash)');
   db.prepare('INSERT INTO admission_policy VALUES(1,?)').run(text(f.policy));
   for(const [table,rows] of [['admission_events',admission],['admission_exit_signing',signing]])for(const r of rows)db.prepare(`INSERT INTO ${table} VALUES(?,?,?,?,?)`).run(r.seq,r.at_ms,r.value,r.previous_hash,r.hash);
   for(const [table,v] of [['admission_entry_accounting',f.entry],['admission_exit_preparation',f.prep]])db.prepare(`INSERT INTO ${table} VALUES(1,?,?)`).run(text(v),hash(v));
  }finally{db.close();}
 }
 function nextFixture(){
  const f=fixture(),a=f.entry.accounting,scope=f.policy.scope,keys=[pair.wallet,scope.accounts.source,scope.accounts.destination,scope.accounts.inputMint,scope.accounts.outputMint];
  a.preexistingDestinationAtomic='500000000';a.sourcePrincipalHeldAtomic='0';a.sourcePrincipalSpentAtomic='1000';
  const raw58=s=>{let n=0n;for(const c of s)n=n*58n+BigInt(alpha.indexOf(c));let h=n.toString(16);if(h.length%2)h='0'+h;return Buffer.concat([Buffer.alloc(s.match(/^1*/)[0].length),n?Buffer.from(h,'hex'):Buffer.alloc(0)]);};
  const acct=(buf,owner,lamports=2039280)=>({owner,executable:false,lamports,data:[buf.toString('base64'),'base64']});
  const token=(mint,amount)=>{const b=Buffer.alloc(165);raw58(mint).copy(b);raw58(pair.wallet).copy(b,32);b.writeBigUInt64LE(BigInt(amount),64);b[108]=1;return acct(b,'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA');};
  const mint=()=>{const b=Buffer.alloc(82);b[45]=1;return acct(b,'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA');};
  const accounts=[acct(Buffer.alloc(0),'11111111111111111111111111111111',500000000),token(keys[3],'499999000'),token(keys[4],'500000996'),mint(),mint()];
  const e=f.prep.evidence;e.capture={accountKeys:keys,evidence:{accounts:{state:'received',result:{context:{slot:100},value:accounts}}}};
  e.simulationItem={result:{context:{slot:100}}};e.price={quote:{contextSlot:100}};f.prep.collection.packetBuild.lastValidBlockHeight=200;
  f.prep.binding.protectedInventoryAtomic='500000000';
  f.prep.binding.evidenceSha256=f.prep.collection.provenance.evidenceSha256=hash(e);
  f.prep.binding.entryAccountingSha256=f.req.entryAccountingSha256=f.prep.collection.provenance.identity.entryAccountingSha256=hash(f.entry);
  ledger(f);
  const file=path.join(f.storage,'entry.admission.sqlite'),db=new DatabaseSync(file);
  const one=(table,v)=>db.prepare(`INSERT INTO ${table} VALUES(1,?,?)`).run(text(v),hash(v));
  const row=(seq,v,prev,at)=>({seq,at_ms:at,value:text(v),previous_hash:prev,hash:hash({seq,atMs:at,value:v,previousHash:prev})});
  try{
   const first=db.prepare('SELECT * FROM admission_exit_signing').get(),admission=db.prepare('SELECT * FROM admission_events').all();
   const oldSig=crypto.sign(null,f.built.message,key.privateKey),oldWire=Buffer.concat([Buffer.from([1]),oldSig,f.built.message]).toString('base64');
   const signed={state:'exit-signed-recorded',signedWireBase64:oldWire,wireSha256:bytesHash(Buffer.from(oldWire,'base64')),signature:b58(oldSig)};
   const second=row(2,signed,first.hash,f.now+1);db.prepare('INSERT INTO admission_exit_signing VALUES(?,?,?,?,?)').run(second.seq,second.at_ms,second.value,second.previous_hash,second.hash);
   const oldState={state:'exit-signed-recorded',request:f.req,requestSha256:hash(f.req),admissionHeadSha256:admission[0].hash,eventCount:2,headSha256:second.hash,lastAtMs:second.at_ms,signed,minimumContextSlot:100};
   const amounts={sourcePrincipalHeldAtomic:'0',sourcePrincipalSpentAtomic:'1000',sourceProceedsHeldAtomic:'0',ownedAcquiredHeldAtomic:'996',protectedAcquiredInventoryAtomic:'500000000',feeHeldLamports:'25000',feePaidLamports:'5000',sourceProceedsReleasedAtomic:'0',unusedFeeReleasedLamports:'0',protectedInventoryReleasedAtomic:'0',scopedClosureRecorded:false,basis:'entry-settled-exit-not-settled'};
   const ctx={identity:{preparationSha256:hash(f.prep),signingStateSha256:hash(oldState),signature:signed.signature,blockhash:f.req.packet.policy.blockhash,minimumContextSlot:100,scopedAccounting:amounts},accountKeys:keys,expectedAccounts:accounts,lastValidBlockHeight:200,signedWire:oldWire};
   const proof=(at,slot)=>Object.fromEntries(Object.entries({genesisBefore:GENESIS,genesisAfter:GENESIS,validity:{context:{slot},value:false},height:201,status:{context:{slot:slot+1},value:[null]},transaction:null,accounts:{context:{slot:slot+2},value:copy(accounts)},blockTime:Math.floor(at/1000)}).map(([k,v])=>[k,{state:'received',result:v}]));
   const now=Date.now(),retired={format:'held-exit-retirement-1',recordedAtMs:now-20000,preparationSha256:hash(f.prep),contextSha256:hash(ctx),startedAtMs:now-20000,observedAtMs:now-20000,rpcEvidence:proof(now-20000,110)};
   const fresh={contextSha256:hash(ctx),startedAtMs:now,observedAtMs:now,rpcEvidence:proof(now,120)};
   const c={format:'retired-exit-successor-1-unsigned',evidence:copy(e),collection:copy(f.prep.collection),binding:copy(f.prep.binding)};
   const q=c.evidence.packet.policy;q.issuedAtMs=now;q.expiresAtMs=now+15000;q.blockhash=b58(Buffer.alloc(32,20));
   const reverse={...copy(q),format:'devnet-swap-scope-1'};for(const k of ['issuedAtMs','expiresAtMs','blockhash'])delete reverse[k];
   const built=compile(reverse,q.blockhash);c.evidence.packet.unsignedTransactionBase64=built.unsigned;
   c.evidence.packet.feeAssertion.messageSha256=bytesHash(built.message);c.evidence.packet.feeAssertion.observedAtMs=now;
   c.evidence.capture.evidence.accounts.result.context.slot=122;
   Object.assign(c.binding,{attemptNumber:2,attemptsConsumed:1,messageSha256:bytesHash(built.message),validUntilExclusiveMs:now+10000,retiredFeeExposureHeldLamports:'10000',otherHeldFeeLamports:'15000',additionalFeeReservationLamports:'0',retirementSha256:hash(retired),retiredPreparationSha256:hash(f.prep)});
   const p=c.collection.provenance;p.startedAtMs=now;p.validUntilExclusiveMs=now+10000;
   p.evidenceSha256=c.binding.evidenceSha256=hash(c.evidence);
   c.binding.collectionSha256=hash(c.collection);
   const successor={format:'retired-exit-successor-1',recordedAtMs:now,contextSha256:hash(ctx),retirementSha256:hash(retired),retiredPreparationSha256:hash(f.prep),expiryProof:fresh,candidate:c};
   const b=c.binding,request={format:'successor-signing-handoff-1-request',successorSha256:hash(successor),retirementSha256:hash(retired),retiredPreparationSha256:hash(f.prep),contextSha256:hash(ctx),entryAccountingSha256:b.entryAccountingSha256,collectionSha256:b.collectionSha256,messageSha256:b.messageSha256,validUntilExclusiveMs:b.validUntilExclusiveMs,quantityAtomic:b.quantityAtomic,protectedInventoryAtomic:b.protectedInventoryAtomic,feeCapLamports:b.feeCapLamports,feeCommitmentRemainingLamports:b.feeCommitmentRemainingLamports,retiredFeeExposureHeldLamports:b.retiredFeeExposureHeldLamports,additionalFeeReservationLamports:'0',attemptNumber:2,attemptsConsumed:1,packet:c.evidence.packet};
   const boundary=row(1,{state:'successor-signing-unknown',request,requestSha256:hash(request),admissionHeadSha256:admission[0].hash},'',now);
   db.exec('CREATE TABLE admission_exit_retirement(id,value,hash);CREATE TABLE admission_exit_successor(id,value,hash);CREATE TABLE admission_successor_signing(seq,at_ms,value,previous_hash,hash)');
   one('admission_exit_retirement',retired);one('admission_exit_successor',successor);
   db.prepare('INSERT INTO admission_successor_signing VALUES(?,?,?,?,?)').run(boundary.seq,boundary.at_ms,boundary.value,boundary.previous_hash,boundary.hash);
   const oldAttempt={format:'exit-signer-attempt-1',requestSha256:hash(f.req),signingHeadSha256:first.hash,preparationSha256:hash(f.prep),atMs:f.now};
   const oldAck={format:'exit-signer-ack-1',requestSha256:hash(f.req),signedTransactionBase64:oldWire,wireSha256:signed.wireSha256};
   write(path.join(f.storage,'exit-signer-attempt.json'),oldAttempt);write(path.join(f.storage,'exit-signer-ack.json'),oldAck);
   return {...f,now,request,built,successor,retired,oldAttempt,oldAck,data:{policy:f.policy,admissionRows:admission,signingRows:[first,second],preparationRow:db.prepare('SELECT * FROM admission_exit_preparation').get(),accountingRow:db.prepare('SELECT * FROM admission_entry_accounting').get(),retirementRow:db.prepare('SELECT * FROM admission_exit_retirement').get(),successorRow:db.prepare('SELECT * FROM admission_exit_successor').get(),successorSigningRows:[boundary],oldAttempt,oldAck},metadata:JSON.parse(fs.readFileSync(path.join(f.root,'wallet.json')))};
  }finally{db.close();}
 }
 function invoke(f){return spawnSync(process.execPath,[path.join(HERE,'successor_signer.mjs')],{input:text({directory:f.root,requestSha256:hash(f.request)}),encoding:'utf8',timeout:5000,env:{PATH:process.env.PATH}});}
 const cases={};
 const f=nextFixture();validate(f.data,f.metadata,pair,hash(f.request),f.now);
 const file=path.join(f.storage,'entry.admission.sqlite'),before=fs.readFileSync(file),r=invoke(f);
 check(r.status===0&&r.stdout==='{"state":"successor-signed-recorded"}');
 const ackPath=path.join(f.storage,'successor-signer-ack.json'),ack=JSON.parse(fs.readFileSync(ackPath));
 const wire=Buffer.from(ack.signedTransactionBase64,'base64');check(wire.subarray(65).equals(f.built.message)&&crypto.verify(null,wire.subarray(65),key.publicKey,wire.subarray(1,65)));
 check(before.equals(fs.readFileSync(file)));cases['independent-successor-signature-without-ledger-write']='passed';
 check(text(JSON.parse(fs.readFileSync(path.join(f.storage,'exit-signer-attempt.json'))))===text(f.oldAttempt)&&text(JSON.parse(fs.readFileSync(path.join(f.storage,'exit-signer-ack.json'))))===text(f.oldAck));cases['retired-generation-markers-preserved']='passed';
 check(invoke(f).status!==0);cases['repeat-invocation-refused']='passed';
 fs.unlinkSync(ackPath);fs.unlinkSync(path.join(f.root,'signer.pk8'));check(invoke(f).status!==0);cases['lost-ack-never-resigns']='passed';

 function rehashCandidate(d,fn){
  const n=JSON.parse(d.successorRow.value);fn(n);
  const c=n.candidate,p=c.collection.provenance;
  p.evidenceSha256=c.binding.evidenceSha256=hash(c.evidence);c.binding.collectionSha256=hash(c.collection);
  d.successorRow.value=text(n);d.successorRow.hash=hash(n);
  const v=JSON.parse(d.successorSigningRows[0].value),q=v.request;
  q.successorSha256=hash(n);q.packet=copy(c.evidence.packet);
  for(const k of ['collectionSha256','messageSha256','validUntilExclusiveMs','quantityAtomic','protectedInventoryAtomic','feeCapLamports','feeCommitmentRemainingLamports','retiredFeeExposureHeldLamports'])q[k]=c.binding[k];
  v.requestSha256=hash(q);const r=d.successorSigningRows[0];r.value=text(v);r.hash=hash({seq:1,atMs:r.at_ms,value:v,previousHash:''});
  return hash(q);
 }
 const g=nextFixture();
 for(const [name,fn] of Object.entries({
  'reset-attempt-counter':n=>n.candidate.binding.attemptsConsumed=0,
  'third-attempt':n=>n.candidate.binding.attemptNumber=3,
  'new-fee-reservation':n=>n.candidate.binding.additionalFeeReservationLamports='1',
  'retired-fee-exposure-erased':n=>n.candidate.binding.retiredFeeExposureHeldLamports='0',
  'fee-increase':n=>n.candidate.binding.feeCapLamports='10001',
  'owned-quantity-change':n=>n.candidate.binding.quantityAtomic='997',
  'protected-inventory-reduction':n=>n.candidate.binding.protectedInventoryAtomic='0',
  'retired-blockhash-reuse':n=>n.candidate.evidence.packet.policy.blockhash=g.prep.evidence.packet.policy.blockhash,
  'mainnet-policy':n=>n.candidate.evidence.packet.policy.network='mainnet',
  'changed-unsigned-wire':n=>n.candidate.evidence.packet.unsignedTransactionBase64='AA==',
  'expired-candidate':n=>n.candidate.binding.validUntilExclusiveMs=g.now,
  'fresh-status-present':n=>n.expiryProof.rpcEvidence.status.result.value=[{err:null}],
  'fresh-transaction-present':n=>n.expiryProof.rpcEvidence.transaction.result={},
  'fresh-blockhash-still-valid':n=>n.expiryProof.rpcEvidence.validity.result.value=true,
  'fresh-height-not-expired':n=>n.expiryProof.rpcEvidence.height.result=200,
  'fresh-account-balance-changed':n=>n.expiryProof.rpcEvidence.accounts.result.value[0].lamports--,
  'fresh-proof-too-old':n=>{n.expiryProof.startedAtMs-=31000;n.expiryProof.observedAtMs-=31000;},
  'proof-context-substitution':n=>n.expiryProof.contextSha256='0'.repeat(64),
  'account-slot-regression':n=>n.candidate.evidence.capture.evidence.accounts.result.context.slot=100,
  'wrong-collection-genesis':n=>{n.candidate.collection.finalGenesis.result='wrong';n.candidate.collection.provenance.finalGenesisSha256=hash(n.candidate.collection.finalGenesis);},
  'forward-account-direction':n=>n.candidate.evidence.packet.policy.accounts.source=g.policy.scope.accounts.source,
  'inflated-deadline':n=>{n.candidate.binding.validUntilExclusiveMs=g.now+20000;n.candidate.collection.provenance.validUntilExclusiveMs=g.now+20000;},
 })){
  const d=copy(g.data),h=rehashCandidate(d,fn);let denied=false;
  try{validate(d,g.metadata,pair,h,g.now);}catch{denied=true;}check(denied);cases[name+'-refused']='passed';
 }
 for(const [name,fn] of Object.entries({
  'old-ack-substitution':d=>d.oldAck.requestSha256='0'.repeat(64),
  'old-attempt-substitution':d=>d.oldAttempt.signingHeadSha256='0'.repeat(64),
  'missing-retirement':d=>d.retirementRow=null,
  'missing-successor-boundary':d=>d.successorSigningRows=[],
  'already-acknowledged-generation':d=>d.successorSigningRows.push(d.successorSigningRows[0]),
  'old-wire-corruption':d=>{const r=d.signingRows[1],v=JSON.parse(r.value),b=Buffer.from(v.signedWireBase64,'base64');b[1]^=1;v.signedWireBase64=b.toString('base64');v.wireSha256=bytesHash(b);r.value=text(v);r.hash=hash({seq:2,atMs:r.at_ms,value:v,previousHash:r.previous_hash});},
  'changed-request-digest':d=>d.successorSigningRows[0].hash='0'.repeat(64),
 })){
  const d=copy(g.data);fn(d);let denied=false;try{validate(d,g.metadata,pair,hash(g.request),g.now);}catch{denied=true;}check(denied);cases[name+'-refused']='passed';
 }
 function deniedBackend(name,fn){const h=nextFixture();fn(h);check(invoke(h).status!==0&&!fs.existsSync(path.join(h.storage,'successor-signer-ack.json'))&&!fs.existsSync(path.join(h.storage,'successor-signer-attempt.json')));cases[name]='passed';}
 deniedBackend('stop-refuses-before-key-signing',h=>write(path.join(h.root,'STOP'),''));
 deniedBackend('wrong-wallet-key-refused',h=>fs.writeFileSync(path.join(h.root,'signer.pk8'),wrongDer));
 deniedBackend('symlink-key-refused',h=>{const p=path.join(h.root,'signer.pk8');fs.renameSync(p,p+'.saved');fs.symlinkSync(p+'.saved',p);});
 deniedBackend('public-key-permissions-refused',h=>fs.chmodSync(path.join(h.root,'signer.pk8'),0o644));
 deniedBackend('database-sidecar-refused',h=>write(path.join(h.storage,'entry.admission.sqlite-wal'),''));
 deniedBackend('old-send-boundary-refused',h=>{const db=new DatabaseSync(path.join(h.storage,'entry.admission.sqlite'));try{db.exec('CREATE TABLE admission_exit_submission(id)');}finally{db.close();}});
 deniedBackend('old-ack-file-mismatch-refused',h=>fs.writeFileSync(path.join(h.storage,'exit-signer-ack.json'),'{}'));
 const concurrent=nextFixture();
 const start=()=>new Promise((resolve,reject)=>{const child=spawn(process.execPath,[path.join(HERE,'successor_signer.mjs')],{stdio:['pipe','pipe','pipe'],env:{PATH:process.env.PATH}});let out='';child.stdout.on('data',b=>out+=b);child.stderr.resume();child.on('error',reject);child.on('close',code=>resolve({code,out}));child.stdin.end(text({directory:concurrent.root,requestSha256:hash(concurrent.request)}));});
 const winners=await Promise.all([start(),start()]);check(winners.filter(r=>r.code===0&&r.out==='{"state":"successor-signed-recorded"}').length===1&&winners.filter(r=>r.code!==0).length===1);
 cases['concurrent-processes-have-one-exclusive-signing-winner']='passed';
 process.stdout.write(text({state:'offline-checks-passed',casesPassed:Object.keys(cases).length,cases,networkRequests:0,transactionsSent:0,userPrivateKeysAccessed:false,disposableKeys:true}));
}finally{if(der)der.fill(0);if(wrongDer)wrongDer.fill(0);fs.rmSync(top,{recursive:true,force:true});}
