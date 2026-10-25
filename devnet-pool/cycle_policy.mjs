// Independent fixed cycle identity and durable reservation checks. No signing or network.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
const check=v=>{if(!v)throw new Error('cycle-policy');};
const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
const stringify=v=>JSON.stringify(canonical(v));
const hash=v=>crypto.createHash('sha256').update(stringify(v)).digest('hex');
const whole=n=>Number.isSafeInteger(n)&&n>=0;
const atomic=s=>{check(typeof s==='string'&&/^(0|[1-9][0-9]{0,19})$/.test(s));const n=BigInt(s);check(n<2n**64n);return n;};
const POLICY={network:'devnet',maximumCycles:2,maximumCumulativeEntryAtomic:'2000',maximumCumulativeSwapFeeLamports:'40000',
 nextEntryAtomic:'1000',nextMinimumOutputAtomic:'990',nextRoundTripFeeAllowanceLamports:'20000'};
const SPENDING={network:'devnet',maximumPrincipalAtomic:'1000',maximumLegFeeLamports:'10000',maximumRoundTripFeeLamports:'20000',maximumEntries:1,maximumExits:1};
function read(p,max){const fd=fs.openSync(p,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);try{
 const s=fs.fstatSync(fd);check(s.isFile()&&s.uid===process.getuid()&&(s.mode&0o777)===0o600&&s.nlink===1&&s.size<=max);return fs.readFileSync(fd);
}finally{fs.closeSync(fd);}}
function present(p){try{fs.lstatSync(p);return true;}catch(e){if(e.code==='ENOENT')return false;throw e;}}
function verifyReplacement(home,state,plan,rows){
 const r=state.unsignedReplacement,archive=path.join(home,'refused-unsigned-entry-v1');
 if(!r){check(plan.unsignedReplacementSha256===undefined&&!present(path.join(home,'unsigned-replacement.json'))&&!present(archive));return;}
 const m=JSON.parse(read(path.join(home,'unsigned-replacement.json'),32768));
 const seal=JSON.parse(read(path.join(home,'unsigned-replacement-ready.json'),4096));
 check(m.format==='unsigned-cycle-replacement-1'&&m.cycleId==='controlled-cycle-0002'&&r.format===m.format
  &&seal.format===m.format&&seal.manifestSha256===hash(m)&&r.manifestSha256===hash(m)
  &&plan.unsignedReplacementSha256===hash(m)&&m.preparationSha256===plan.cycleBinding.preparationSha256);
 check(m.oldLedgerCount===1&&rows.length>=3&&m.oldLedgerHash===rows[0].event_hash);
 const first=JSON.parse(rows[0].snapshot),approved=JSON.parse(rows[1].snapshot);
 check(!first.unsignedReplacement&&Object.keys(first.legs).join('|')==='entry'&&stringify(first.legs.entry)===stringify(m.oldEntry));
 check(stringify(r.oldEntry)===stringify(m.oldEntry)&&stringify(approved.legs.entry)===stringify(m.oldEntry)
  &&approved.unsignedReplacement.manifestSha256===hash(m)&&approved.unsignedReplacement.newPlanSha256===null);
 check(r.newPlanSha256===state.legs.entry.contract.planSha256&&r.newPlanSha256!==m.oldEntry.contract.planSha256
  &&whole(m.approvedAtMs)&&whole(r.authorizedAtMs)&&whole(r.replacedAtMs)
  &&m.approvedAtMs<=r.authorizedAtMs&&r.authorizedAtMs<=r.replacedAtMs&&r.replacedAtMs<=Date.now());
 check(m.oldEntry.signed===null&&m.oldEntry.boundaryAtMs===null&&m.oldEntry.receipt===null);
 const a=fs.lstatSync(archive);check(a.isDirectory()&&!a.isSymbolicLink()&&a.uid===process.getuid()&&(a.mode&0o777)===0o700);
 const limits={'plan.json':32768,'execution.json':32768,'preflight.json':4*1024*1024,
  'signing-request.json':8192,'spending-reservation.json':4096,'failure.json':4096};
 check(fs.readdirSync(archive).sort().join('|')===Object.keys(limits).sort().join('|'));
 const hashes={},values={};for(const [name,max] of Object.entries(limits)){
  const raw=read(path.join(archive,name),max);hashes[name]=crypto.createHash('sha256').update(raw).digest('hex');values[name]=JSON.parse(raw);
 }
 check(stringify(hashes)===stringify(m.files)&&m.evidenceSha256===hash(hashes));
 const old=values['plan.json'],request=values['signing-request.json'],contract=m.oldEntry.contract;
 check(contract.planSha256===hash(old)&&contract.preflightSha256===hash(values['preflight.json'])
  &&request.planSha256===hash(old)&&request.preflightSha256===contract.preflightSha256
  &&stringify(old.cycleBinding)===stringify(plan.cycleBinding)&&old.unsignedReplacementSha256===undefined);
 check(whole(request.expiresAtMs)&&whole(old.packet.policy.expiresAtMs)
  &&Math.max(request.expiresAtMs,old.packet.policy.expiresAtMs)<=m.approvedAtMs
  &&values['failure.json'].phase==='signing'&&values['failure.json'].reason==='execution-validation-or-transport-incomplete');
 if(plan.scope.accounts.source===old.scope.accounts.source){
  check(plan.packet.policy.blockhash!==old.packet.policy.blockhash&&hash(plan)===r.newPlanSha256);
 }
}
export function verifyCycleReservation(root,home,plan,capture,side){
 check(home===path.join(root,'controlled-cycle-0002')&&['entry','exit'].includes(side));
 // Python wrote canonical JSON and sealed those bytes. Re-encoding the parsed
 // object in JS rounds u64 RPC fields and changes float spellings (1.0 -> 1).
 // Verify the immutable bytes; never rewrite the preparation or its seal.
 const prepBytes=read(path.join(home,'preparation.json'),512*1024);
 const preparationHash=crypto.createHash('sha256').update(prepBytes).digest('hex');
 const prep=JSON.parse(prepBytes);
 const seal=JSON.parse(read(path.join(home,'complete.json'),4096));
 check(prep.format==='controlled-cycle-preparation-1'&&prep.cycleId==='controlled-cycle-0002'&&stringify(prep.policy)===stringify(POLICY));
 check(seal.format===prep.format&&seal.preparationSha256===preparationHash&&prep.priorEvidenceSha256===hash(prep.source));
 const a=prep.source.scope.accounts,budget=prep.budget;
 check(prep.wallet===a.wallet&&prep.pool===a.pool&&plan.scope.accounts.wallet===prep.wallet&&plan.scope.accounts.pool===prep.pool);
 check(budget.historicalCycles===1&&budget.allocatedCycles===2&&budget.historicalEntryAtomic==='1000'&&budget.historicalResidualAcquiredAtomic==='0');
 const priorFees=atomic(budget.historicalSwapFeeLamports);check(priorFees>0n&&priorFees<=20000n);
 check(prep.source.position.state==='closed'&&prep.source.position.lastReconciledResidualAtomic==='0'
  &&prep.source.position.originalSpentAtomic==='1000'&&prep.source.position.confirmedFeeLamports===budget.historicalSwapFeeLamports
  &&prep.source.entryReceipt.state==='finalized-success'&&prep.source.exitReceipt.state==='finalized-success'
  &&atomic(prep.source.entryReceipt.feeLamports)+atomic(prep.source.exitReceipt.feeLamports)===priorFees);
 check(budget.nextEntryAllocationAtomic==='1000'&&budget.nextFeeAllocationLamports==='20000'&&budget.cumulativeEntryWithAllocationAtomic==='2000');
 check(atomic(budget.cumulativeSwapFeesWithAllocationLamports)===priorFees+20000n&&priorFees+20000n<=40000n);
 const expected={format:'controlled-cycle-binding-1',cycleId:prep.cycleId,preparationSha256:preparationHash,priorEvidenceSha256:prep.priorEvidenceSha256,
 wallet:prep.wallet,pool:prep.pool,historicalEntryAtomic:budget.historicalEntryAtomic,historicalSwapFeeLamports:budget.historicalSwapFeeLamports,
 nextEntryAtomic:'1000',nextFeeAllowanceLamports:'20000',cumulativeEntryCapAtomic:'2000',cumulativeFeeCapLamports:'40000',balances:prep.balances,accounts:a};
 check(stringify(plan.cycleBinding)===stringify(expected));
 const dbpath=path.join(home,'controlled.spending.sqlite');read(dbpath,2*1024*1024);
 const db=new DatabaseSync(dbpath,{readOnly:true});let rows;
 try{rows=db.prepare('SELECT * FROM spending_events ORDER BY seq LIMIT 33').all();}finally{db.close();}
 check(rows.length>0&&rows.length<=32);let previous='',stamp=0,state;
 for(let i=0;i<rows.length;i++){
  const row=rows[i];check(row.seq===i+1&&whole(row.at_ms)&&row.at_ms>=stamp&&Buffer.byteLength(row.snapshot)<=32768);
  state=JSON.parse(row.snapshot);check(stringify(state)===row.snapshot&&state.format==='controlled-spending-guard-1');
  check(stringify(state.policy)===stringify(SPENDING)&&stringify(state.cycleBinding)===stringify(expected));
  check(row.previous_hash===previous&&row.event_hash===hash({seq:i+1,atMs:row.at_ms,state,previousHash:previous}));
  previous=row.event_hash;stamp=row.at_ms;
 }
 check(!state.quarantined&&state.wallet===prep.wallet&&state.pool===prep.pool&&stamp<=Date.now());
 verifyReplacement(home,state,plan,rows);
 const leg=state.legs[side];check(leg&&leg.signed===null&&leg.boundaryAtMs===null&&leg.receipt===null);
 check(leg.contract.planSha256===hash(plan)&&leg.contract.preflightSha256===hash(capture)&&leg.contract.scopeSha256===hash(plan.scope));
 check(leg.contract.feeLamports===plan.packet.feeAssertion.lamports&&atomic(leg.contract.feeLamports)>0n&&atomic(leg.contract.feeLamports)<=10000n);
 const marker=JSON.parse(read(path.join(home,side==='entry'?'swap-execution-v1':'swap-reverse-v1','spending-reservation.json'),4096));
 check(marker.format===state.format&&marker.side===side&&marker.planSha256===hash(plan));
 const byKey=new Map(capture.accountKeys.map((k,i)=>[k,capture.evidence.accounts.result.value[i]]));
 const wallet=byKey.get(a.wallet);check(whole(wallet.lamports)&&String(wallet.lamports)===leg.contract.nativeBeforeLamports);
 if(side==='entry'){
  check(Object.keys(state.legs).join('|')==='entry'&&plan.scope.amountIn==='1000'&&plan.scope.minimumAmountOut==='990');
  check(capture.evidence.accounts.result.context.slot>=prep.balances.slot&&String(wallet.lamports)===prep.balances.walletLamports);
  for(const [key,amount] of [[a.source,prep.balances.originalTokenAtomic],[a.destination,prep.balances.backgroundAcquiredAtomic]]){
   const row=byKey.get(key);check(row.data[1]==='base64');const raw=Buffer.from(row.data[0],'base64');
   check(raw.length===165&&raw.readBigUInt64LE(64).toString()===amount);
  }
  check(atomic(leg.contract.nativeBeforeLamports)>=20000n);
 }else{
  const entry=state.legs.entry;check(Object.keys(state.legs).sort().join('|')==='entry|exit'&&entry&&entry.receipt?.state==='finalized-success');
  check(plan.scope.amountIn===entry.receipt.outputAtomic&&leg.contract.nativeBeforeLamports===entry.receipt.walletAfterLamports);
  check(atomic(entry.receipt.feeLamports)+10000n<=20000n&&priorFees+atomic(entry.receipt.feeLamports)+10000n<=40000n);
  const first=JSON.parse(read(path.join(home,'swap-execution-v1','plan.json'),32768));
  check(entry.contract.planSha256===hash(first)&&stringify(first.cycleBinding)===stringify(expected));
 }
 return state;
}
