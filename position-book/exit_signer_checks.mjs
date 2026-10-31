// Disposable-key backend exercise; never accepts an existing wallet directory.
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import crypto from 'node:crypto';
import {spawnSync,spawn} from 'node:child_process';import {fileURLToPath} from 'node:url';import {DatabaseSync} from 'node:sqlite';
import {addresses} from '../devnet-pool/pool_policy.mjs';
import {check,text,hash,bytesHash,compile,roles} from './admission_signer_contract.mjs';
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
 let index=0;const cases={};
 function fixture(){
  const now=Date.now(),root=path.join(top,'source-'+index++),storage=root+'-entry-handoff-v1';
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
 function invoke(f,h=hash(f.req)){return spawnSync(process.execPath,[path.join(HERE,'exit_signer.mjs')],{input:text({directory:f.root,requestSha256:h}),encoding:'utf8',timeout:5000,env:{PATH:process.env.PATH}});}
 function refuse(name,mutate=()=>{},alter=()=>{},after=()=>{}){const f=fixture();mutate(f);ledger(f,alter);after(f);const r=invoke(f);check(r.status!==0&&!fs.existsSync(path.join(f.storage,'exit-signer-ack.json')));cases[name]='passed';}
 const f=fixture();ledger(f);const before=fs.readFileSync(path.join(f.storage,'entry.admission.sqlite'));const r=invoke(f);
 check(r.status===0&&r.stdout==='{"state":"exit-signed-recorded"}');
 const ack=JSON.parse(fs.readFileSync(path.join(f.storage,'exit-signer-ack.json'))),wire=Buffer.from(ack.signedTransactionBase64,'base64');
 check(wire[0]===1&&wire.subarray(65).equals(f.built.message)&&crypto.verify(null,wire.subarray(65),key.publicKey,wire.subarray(1,65)));
 cases['independent-exact-reverse-signature']='passed';
 check(fs.readFileSync(path.join(f.storage,'entry.admission.sqlite')).equals(before));cases['committed-ledger-remains-byte-identical']='passed';
 check(!fs.existsSync(path.join(f.storage,'signer-attempt.json'))&&!fs.existsSync(path.join(f.storage,'signer-ack.json')));cases['entry-backend-markers-never-reused']='passed';
 const raw=fs.readFileSync(path.join(f.storage,'exit-signer-ack.json'));check(invoke(f).status!==0&&raw.equals(fs.readFileSync(path.join(f.storage,'exit-signer-ack.json'))));cases['second-invocation-cannot-resign']='passed';
 fs.unlinkSync(path.join(f.storage,'exit-signer-ack.json'));fs.unlinkSync(path.join(f.root,'signer.pk8'));check(invoke(f).status!==0);cases['lost-acknowledgment-retains-one-shot-attempt']='passed';
 refuse('changed-quantity-refused',f=>f.req.quantityAtomic='995');
 refuse('wrong-reverse-account-refused',f=>f.req.packet.policy.accounts.source=f.policy.scope.accounts.source);
 refuse('mainnet-policy-refused',f=>f.req.packet.policy.network='mainnet');
 refuse('expired-deadline-refused',f=>f.req.validUntilExclusiveMs=f.prep.binding.validUntilExclusiveMs=f.prep.collection.provenance.validUntilExclusiveMs=f.now-1);
 refuse('entry-blockhash-reuse-refused',f=>f.req.packet.policy.blockhash=f.state.signingRequest.packet.policy.blockhash);
 refuse('missing-signing-boundary-refused',()=>{},(a,s)=>s.pop());
 refuse('additional-signing-event-refused',()=>{},(a,s)=>s.push(s[0]));
 refuse('changed-event-hash-refused',()=>{},(a,s)=>s[0].hash='0'.repeat(64));
 refuse('changed-wire-refused',f=>f.req.packet.unsignedTransactionBase64='AA==');
 refuse('raw-legacy-preparation-refused',f=>f.prep.format='admission-exit-preparation-1-record');
 refuse('wrong-final-genesis-even-rehashed-refused',f=>f.prep.collection.finalGenesis.result='wrong');
 refuse('missing-request-provenance-refused',f=>f.prep.collection.requestTrace=[]);
 refuse('entry-not-open-refused',f=>f.entry.accounting.state='entry-failed-held');
 refuse('fee-commitment-shortfall-refused',f=>f.entry.accounting.feeCommitmentRemainingLamports='1');
 refuse('wrong-key-refused',f=>fs.writeFileSync(path.join(f.root,'signer.pk8'),wrongDer));
 refuse('stop-refused',f=>write(path.join(f.root,'STOP'),''));
 refuse('unsafe-key-mode-refused',f=>fs.chmodSync(path.join(f.root,'signer.pk8'),0o644));
 refuse('symlink-key-refused',f=>{fs.renameSync(path.join(f.root,'signer.pk8'),path.join(f.root,'saved'));fs.symlinkSync(path.join(f.root,'saved'),path.join(f.root,'signer.pk8'));});
 refuse('recovery-sidecar-refused',()=>{},()=>{},f=>write(path.join(f.storage,'entry.admission.sqlite-journal'),''));
 const concurrent=fixture();ledger(concurrent);
 function asyncInvoke(f){return new Promise((resolve,reject)=>{const child=spawn(process.execPath,[path.join(HERE,'exit_signer.mjs')],{stdio:['pipe','pipe','pipe'],env:{PATH:process.env.PATH}});let out='';const timer=setTimeout(()=>child.kill('SIGKILL'),5000);child.stdout.on('data',b=>out+=b);child.stderr.resume();child.on('error',reject);child.on('close',code=>{clearTimeout(timer);resolve({code,out});});child.stdin.end(text({directory:f.root,requestSha256:hash(f.req)}));});}
 const concurrentResults=await Promise.all([asyncInvoke(concurrent),asyncInvoke(concurrent)]);
 check(concurrentResults.filter(x=>x.code===0).length===1&&concurrentResults.filter(x=>x.code!==0).length===1);
 const concurrentAck=JSON.parse(fs.readFileSync(path.join(concurrent.storage,'exit-signer-ack.json'))),concurrentWire=Buffer.from(concurrentAck.signedTransactionBase64,'base64');
 check(crypto.verify(null,concurrentWire.subarray(65),key.publicKey,concurrentWire.subarray(1,65)));
 cases['concurrent-backends-create-only-one-signature']='passed';
 const wrongHash=fixture();ledger(wrongHash);check(invoke(wrongHash,'0'.repeat(64)).status!==0);cases['caller-digest-cannot-replace-ledger-request']='passed';
 check((fs.statSync(path.join(f.storage,'exit-signer-attempt.json')).mode&0o777)===0o600);cases['attempt-file-private-and-durable']='passed';
 process.stdout.write(text({format:'restricted-exit-signer-1-self-check',state:'offline-checks-passed',mode:'disposable-key-offline',casesPassed:Object.keys(cases).length,cases,
  ephemeralTestKeysCreated:2,signaturesCreated:2,networkRequests:0,transactionsSent:0,productionWalletAccessed:false,productionLedgerUpdated:false,temporaryLedgersRemoved:true,
  liveSenderIntegrated:false,executionApproved:false,nextCycleAuthorized:false,reservationReleased:false}));
}finally{if(der)der.fill(0);if(wrongDer)wrongDer.fill(0);fs.rmSync(top,{recursive:true,force:true});}
