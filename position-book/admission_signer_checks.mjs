// Disposable-key self-check only. Never accepts a user wallet/source directory.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {DatabaseSync} from 'node:sqlite';
import {addresses} from '../devnet-pool/pool_policy.mjs';
import {check,text,hash,bytesHash,compile,roles} from './admission_signer_contract.mjs';
const HERE=path.dirname(fileURLToPath(import.meta.url));
const alpha='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
function b58(b) {let n=BigInt('0x'+b.toString('hex')),s='',z=0;while(n){s=alpha[Number(n%58n)]+s;n/=58n;}while(z<b.length&&b[z]===0)z++;return '1'.repeat(z)+s;}
const copy=v=>JSON.parse(JSON.stringify(v));
function write(p,v) {fs.writeFileSync(p,typeof v === 'string'||Buffer.isBuffer(v)?v:text(v),{mode:0o600,flag:'wx'});}
const top=fs.mkdtempSync(path.join(os.tmpdir(),'radar-signer-check-'));fs.chmodSync(top,0o700);
let der, otherDer;
try {
  const key=crypto.generateKeyPairSync('ed25519');
  der=key.privateKey.export({format:'der',type:'pkcs8'});
  const publicRaw=key.publicKey.export({format:'der',type:'spki'}).subarray(12);
  const wrong=crypto.generateKeyPairSync('ed25519');otherDer=wrong.privateKey.export({format:'der',type:'pkcs8'});
  const pair={wallet:b58(publicRaw),mintA:b58(Buffer.alloc(32,11)),holderA:b58(Buffer.alloc(32,13)),mintB:b58(Buffer.alloc(32,12)),holderB:b58(Buffer.alloc(32,14))};
  const derived=addresses(pair), mapping={source:'holder0',destination:'holder1',inputVault:'vault0',outputVault:'vault1',inputMint:'mint0',outputMint:'mint1'};
  let count=0;const cases={};
  function fixture() {
    const now=Date.now(),root=path.join(top,'source-'+count++);fs.mkdirSync(root,{mode:0o700});
    const storage=root+'-entry-handoff-v1';fs.mkdirSync(storage,{mode:0o700});
    fs.mkdirSync(path.join(root,'controlled-pool-v1'),{mode:0o700});
    const scope={format:'devnet-swap-scope-1',network:'devnet',accounts:Object.fromEntries(roles.map(k=>[k,derived[mapping[k]||k]])),
      amountIn:'1000',minimumAmountOut:'990',maxComputeUnits:300000,maxMicroLamportsPerCU:'0',maxPriorityFeeLamports:'0',maxTotalFeeLamports:'10000'};
    const policy={format:'pre-sign-admission-1-policy',scope,maximumExitAttempts:2,maximumExitFeeLamports:'10000',maximumTotalFeeLamports:'40000'};
    const p={...copy(scope),format:'cpmm-instruction-policy-1',issuedAtMs:now,expiresAtMs:now+15000,blockhash:b58(Buffer.alloc(32,18))};
    const built=compile(scope,p.blockhash),packet={format:'unsigned-cpmm-contract-1',policy:p,unsignedTransactionBase64:built.unsigned,
      feeAssertion:{format:'message-fee-assertion-1',network:'devnet',messageSha256:bytesHash(built.message),observedAtMs:now,lamports:'5000'}};
    const first={evidenceSha256:'a'.repeat(64),policySha256:hash(policy),messageSha256:bytesHash(built.message),ledgerHeadSha256:'b'.repeat(64),cycleBindingSha256:'c'.repeat(64),
      validUntilExclusiveMs:now+10000,reservedPrincipalAtomic:'1000',reservedFeeLamports:'30000',maximumExitAttempts:2,entryFeeCapLamports:'10000',exitFeeCapLamports:'10000',state:'reserved',reservedAtMs:now,signingBoundaryAtMs:null};
    const token=(side,mint,amount)=>({account:scope.accounts[side],mint:scope.accounts[mint],programId:'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA',decimals:6,preAmountAtomic:amount,lifecycle:'existing'});
    const req={format:'entry-handoff-1-sign-request',network:'devnet',policySha256:hash(policy),evidenceSha256:first.evidenceSha256,messageSha256:first.messageSha256,
      validUntilExclusiveMs:first.validUntilExclusiveMs,packet,receiptIntentTemplate:{format:'transaction-intent-1',network:'devnet',wallet:pair.wallet,messageSha256:built.canonicalHash,
        preparedAtMs:now,walletPreLamports:'100000',source:token('source','inputMint','10000'),destination:token('destination','outputMint','0'),inputAtomic:'1000',minimumOutputAtomic:'990',maximumFeeLamports:'10000',maximumRentLamports:'0'}};
    write(path.join(root,'wallet.json'),{format:'devnet-wallet-1',network:'devnet',purpose:'fixed-self-transfer-rehearsal',wallet:pair.wallet});
    write(path.join(root,'signer.pk8'),der);
    write(path.join(root,'controlled-pool-v1','plan.json'),{format:'devnet-pool-intent-1',network:'devnet',genesis:'EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG',pairAccounts:pair});
    return {root,storage,policy,first,req,now,built};
  }
  function ledger(f, alterRows=()=>{}) {
    const armed={...f.first,signingRequest:f.req,signingRequestSha256:hash(f.req)};
    const states=[f.first,armed,{...armed,state:'signing-unknown',signingBoundaryAtMs:f.now}];let prev='';
    const rows=states.map((value,i)=>{const h=hash({seq:i+1,atMs:f.now,value,previousHash:prev});const r={seq:i+1,at_ms:f.now,value:text(value),previous_hash:prev,hash:h};prev=h;return r;});alterRows(rows);
    const file=path.join(f.storage,'entry.admission.sqlite');write(file,'');const db=new DatabaseSync(file);
    try {
      db.exec('PRAGMA application_id=1380534833; PRAGMA user_version=1; CREATE TABLE intents(id); CREATE TABLE events(id); CREATE TABLE admission_policy(id PRIMARY KEY,value); CREATE TABLE admission_events(seq PRIMARY KEY,at_ms,value,previous_hash,hash)');
      db.prepare('INSERT INTO admission_policy VALUES(1,?)').run(text(f.policy));
      for(const r of rows)db.prepare('INSERT INTO admission_events VALUES(?,?,?,?,?)').run(r.seq,r.at_ms,r.value,r.previous_hash,r.hash);
    } finally {db.close();}
  }
  function invoke(f, requestedHash=hash(f.req)) {
    return spawnSync(process.execPath,[path.join(HERE,'admission_signer.mjs')],{input:text({directory:f.root,requestSha256:requestedHash}),encoding:'utf8',timeout:5000,env:{PATH:process.env.PATH}});
  }
  function refuse(name,mutate=()=>{},alterRows=()=>{},after=()=>{}) {
    const f=fixture();mutate(f);ledger(f,alterRows);after(f);const r=invoke(f);
    check(r.status !== 0 && !fs.existsSync(path.join(f.storage,'signer-ack.json')));
    cases[name]='passed';return f;
  }
  const f=fixture();ledger(f);const sourceBefore=fs.readFileSync(path.join(f.root,'signer.pk8'));
  const r=invoke(f);check(r.status === 0 && r.stdout === '{"state":"signed-recorded"}');
  const ack=JSON.parse(fs.readFileSync(path.join(f.storage,'signer-ack.json'))),wire=Buffer.from(ack.signedTransactionBase64,'base64');
  check(wire[0] === 1 && wire.subarray(65).equals(f.built.message) && crypto.verify(null,wire.subarray(65),key.publicKey,wire.subarray(1,65)));
  check(ack.requestSha256 === hash(f.req) && ack.wireSha256 === bytesHash(wire));cases['independent-exact-message-signature']='passed';
  const before=fs.readFileSync(path.join(f.storage,'signer-ack.json'));check(invoke(f).status !== 0);
  check(fs.readFileSync(path.join(f.storage,'signer-ack.json')).equals(before));cases['second-invocation-refused-without-changing-ack']='passed';
  check(fs.readFileSync(path.join(f.root,'signer.pk8')).equals(sourceBefore));cases['source-key-file-unchanged']='passed';
  fs.unlinkSync(path.join(f.root,'signer.pk8'));fs.unlinkSync(path.join(f.storage,'signer-ack.json'));
  check(invoke(f).status !== 0);cases['lost-ack-attempt-never-resigns']='passed';
  refuse('different-wallet-pool-scope-refused',f=>{f.policy.scope.accounts.source=f.policy.scope.accounts.destination;});
  refuse('mainnet-policy-refused',f=>{f.policy.scope.network='mainnet';});
  refuse('expired-original-deadline-refused',f=>{f.first.validUntilExclusiveMs=f.req.validUntilExclusiveMs=f.now-1;});
  refuse('missing-durable-boundary-refused',()=>{},rows=>rows.pop());
  refuse('changed-event-hash-refused',()=>{},rows=>rows[1].hash='0'.repeat(64));
  refuse('changed-wire-refused',f=>{f.req.packet.unsignedTransactionBase64='AA==';});
  refuse('wrong-private-key-refused',f=>{fs.writeFileSync(path.join(f.root,'signer.pk8'),otherDer);});
  refuse('stop-blocks-key-backend',f=>write(path.join(f.root,'STOP'),''));
  refuse('unsafe-key-permissions-refused',f=>fs.chmodSync(path.join(f.root,'signer.pk8'),0o644));
  refuse('symlink-key-refused',f=>{fs.renameSync(path.join(f.root,'signer.pk8'),path.join(f.root,'original'));fs.symlinkSync(path.join(f.root,'original'),path.join(f.root,'signer.pk8'));});
  refuse('database-recovery-sidecar-refused',()=>{},()=>{},f=>write(path.join(f.storage,'entry.admission.sqlite-journal'),''));
  refuse('fee-commitment-mismatch-refused',f=>{f.first.reservedFeeLamports='29999';});
  refuse('receipt-template-message-mismatch-refused',f=>{f.req.receiptIntentTemplate.messageSha256='0'.repeat(64);});
  const mismatch=fixture();ledger(mismatch);check(invoke(mismatch,'0'.repeat(64)).status !== 0);cases['caller-request-digest-must-match-ledger']='passed';
  for(const file of ['signer-attempt.json'])check((fs.statSync(path.join(f.storage,file)).mode&0o777)===0o600);
  cases['durable-private-attempt-file']='passed';
  process.stdout.write(text({format:'restricted-admission-signer-1-self-check',state:'offline-checks-passed',mode:'disposable-key-offline',
    casesPassed:Object.keys(cases).length,cases,temporaryLedgersRemoved:true,ephemeralTestKeysCreated:2,
    signaturesCreated:1,networkRequests:0,transactionsSent:0,productionWalletAccessed:false,productionLedgerUpdated:false,
    liveSenderIntegrated:false,executionApproved:false,nextCycleAuthorized:false,reservationReleased:false}));
} finally {
  if(der)der.fill(0);if(otherDer)otherDer.fill(0);fs.rmSync(top,{recursive:true,force:true});
}
