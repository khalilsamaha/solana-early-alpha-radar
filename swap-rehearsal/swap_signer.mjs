// Separate one-shot legacy CPMM devnet signer. No network or arbitrary wire signing.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {addresses as poolAddresses} from '../devnet-pool/pool_policy.mjs';
import {deriveReverse} from '../devnet-pool/reverse_policy.mjs';
import {verifyCycleReservation} from '../devnet-pool/cycle_policy.mjs';
function stopped(p){try{fs.lstatSync(path.join(p,'STOP'));return true;}catch(e){if(e.code==='ENOENT')return false;throw e;}}
const check=v=>{if(!v)throw new Error('refused');};
const alpha='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
function raw58(s){check(typeof s==='string'&&s.length>=32&&s.length<=44);let n=0n;
 for(const c of s){check(alpha.includes(c));n=n*58n+BigInt(alpha.indexOf(c));}
 let h=n.toString(16);if(h.length%2)h='0'+h;
 const b=Buffer.concat([Buffer.alloc(s.match(/^1*/)[0].length),n?Buffer.from(h,'hex'):Buffer.alloc(0)]);check(b.length===32);return b;}
const PROGRAM='DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb';
const TOKEN='TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA';
const COMPUTE='ComputeBudget111111111111111111111111111111';
const NATIVE='So11111111111111111111111111111111111111112';
const SYSTEM='11111111111111111111111111111111';
const roles=['wallet','authority','config','pool','source','destination','inputVault','outputVault','inputMint','outputMint','observation'];
const ixroles=['wallet','authority','config','pool','source','destination','inputVault','outputVault','inputTokenProgram','outputTokenProgram','inputMint','outputMint','observation'];
const writable=new Set(['wallet','pool','source','destination','inputVault','outputVault','observation']);
const namesMatch=(a,b)=>Object.keys(a).length===Object.keys(b).length&&Object.keys(a).every(k=>a[k]===b[k]);
const stable=['network','accounts','amountIn','minimumAmountOut','maxComputeUnits','maxMicroLamportsPerCU','maxPriorityFeeLamports','maxTotalFeeLamports'];
function canonical(v){if(Array.isArray(v))return v.map(canonical);if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])]));return v;}
const stringify=v=>JSON.stringify(canonical(v));
const hash=v=>crypto.createHash('sha256').update(stringify(v)).digest('hex');
function fields(v,names){check(v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join('|')===[...names].sort().join('|'));}
function directory(p){check(typeof p==='string'&&path.isAbsolute(p)&&fs.realpathSync(p)===p);const s=fs.lstatSync(p);check(s.isDirectory()&&s.uid===process.getuid()&&(s.mode&0o777)===0o700);}
function read(p,max){const fd=fs.openSync(p,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);try{const s=fs.fstatSync(fd);check(s.isFile()&&s.uid===process.getuid()&&(s.mode&0o777)===0o600&&s.nlink===1&&s.size<=max);return fs.readFileSync(fd);}finally{fs.closeSync(fd);}}
function save(p,v){const fd=fs.openSync(p,'wx',0o600);try{fs.writeFileSync(fd,stringify(v));fs.fsyncSync(fd);}finally{fs.closeSync(fd);}const d=fs.openSync(path.dirname(p),'r');try{fs.fsyncSync(d);}finally{fs.closeSync(d);}}
function atomic(s,positive=false){check(typeof s==='string'&&/^(0|[1-9][0-9]{0,19})$/.test(s));const n=BigInt(s);check(n<=2n**64n-1n&&n>=(positive?1n:0n));return n;}
function num(n,min,max){check(Number.isSafeInteger(n)&&n>=min&&n<=max);return n;}
const u64=n=>{const b=Buffer.alloc(8);b.writeBigUInt64LE(BigInt(n));return b;};
const u32=n=>{const b=Buffer.alloc(4);b.writeUInt32LE(n);return b;};
const ix=(program,accounts,data)=>Buffer.concat([Buffer.from([program,accounts.length,...accounts,data.length]),data]);
try{
 const input=fs.readFileSync(0);check(input.length<=4096);const r=JSON.parse(input);const execution=r.purpose==='controlled-pool-swap-execution-1',reverse=r.purpose==='controlled-pool-reverse-swap-1';
 const cycle=r.cycle==='controlled-cycle-0002';
 fields(r,cycle?['directory','purpose','cycle']:execution||reverse?['directory','purpose']:['directory']);directory(r.directory);
 check(!cycle||execution||reverse);
 const journalHome=cycle?path.join(r.directory,r.cycle):r.directory;directory(journalHome);
 check(!stopped(r.directory));
 const child=path.join(journalHome,reverse?'swap-reverse-v1':execution?'swap-execution-v1':'swap-simulation-v1');directory(child);
 const plan=JSON.parse(read(path.join(child,'plan.json'),32768));fields(plan,cycle?['format','scope','packet','recordedAtMs','cycleBinding']:['format','scope','packet','recordedAtMs']);check(plan.format==='swap-signing-plan-1');
 const req=JSON.parse(read(path.join(child,'signing-request.json'),8192));fields(req,['format','planSha256','preflightSha256','expiresAtMs','computeUnits','microLamportsPerCU','messageBase64']);
 check(req.format==='restricted-swap-request-1'&&req.planSha256===hash(plan)&&/^[a-f0-9]{64}$/.test(req.preflightSha256));
 const capture=JSON.parse(read(path.join(child,'preflight.json'),4*1024*1024));check(hash(capture)===req.preflightSha256);
 const cycleState=cycle?verifyCycleReservation(r.directory,journalHome,plan,capture,reverse?'exit':'entry'):null;
 const packet=plan.packet;fields(packet,['format','policy','unsignedTransactionBase64','feeAssertion']);check(packet.format==='unsigned-cpmm-contract-1');
 check(stringify(capture.packet)===stringify(packet));
 const p=packet.policy;fields(p,['format','issuedAtMs','expiresAtMs','blockhash',...stable]);
 fields(plan.scope,['format',...stable]);check(plan.scope.format==='devnet-swap-scope-1');
 for(const k of stable)check(stringify(plan.scope[k])===stringify(p[k]));
 check(p.format==='cpmm-instruction-policy-1'&&p.network==='devnet');
 const now=Date.now();num(p.issuedAtMs,0,now);num(p.expiresAtMs,now+1,p.issuedAtMs+15000);
 num(plan.recordedAtMs,p.issuedAtMs,now);num(req.expiresAtMs,now+1,p.expiresAtMs);
 const received=capture.evidence.accounts.receivedAtMs;num(received,p.issuedAtMs,now);check(now-received<=10000&&req.expiresAtMs<=received+10001);
 fields(p.accounts,roles);const a=p.accounts;check(new Set(Object.values(a)).size===roles.length);
 for(const v of Object.values(a)){raw58(v);check(![PROGRAM,TOKEN,COMPUTE,NATIVE,SYSTEM].includes(v));}
 if(execution){
  check(p.amountIn==='1000'&&p.minimumAmountOut==='990'&&p.maxComputeUnits===300000&&
   p.maxMicroLamportsPerCU==='0'&&p.maxPriorityFeeLamports==='0'&&p.maxTotalFeeLamports==='10000'&&req.microLamportsPerCU==='0');
  const setup=JSON.parse(read(path.join(r.directory,'controlled-pool-v1','plan.json'),512*1024));
  const derived=poolAddresses(setup.pairAccounts);
  const mapping={source:'holder0',destination:'holder1',inputVault:'vault0',outputVault:'vault1',inputMint:'mint0',outputMint:'mint1'};
  for(const name of roles)check(a[name]===derived[mapping[name]||name]);
 }
 if(reverse){
  check(p.maxComputeUnits===300000&&p.maxMicroLamportsPerCU==='0'&&p.maxPriorityFeeLamports==='0'&&p.maxTotalFeeLamports==='10000'&&req.microLamportsPerCU==='0');
  const setup=JSON.parse(read(path.join(r.directory,'controlled-pool-v1','plan.json'),512*1024));
  const first=path.join(journalHome,'swap-execution-v1');directory(first);
  const entryPlan=JSON.parse(read(path.join(first,'plan.json'),32768));
  const entrySigned=JSON.parse(read(path.join(first,'signed.json'),8192));
  const entryReceipt=JSON.parse(read(path.join(first,'receipt-evidence.json'),131072));
  const result=deriveReverse(setup.pairAccounts,entryPlan,entrySigned.wire,entryReceipt);
  if(cycle)check(cycleState.legs.entry.signed.wireSha256===result.forwardWireSha256);
  check(namesMatch(result.accounts,a)&&p.amountIn===result.amountIn&&p.minimumAmountOut===result.minimumAmountOut);
  const executionProof=JSON.parse(read(path.join(child,'execution.json'),32768));
  check(executionProof.format==='controlled-pool-reverse-swap-1'&&executionProof.priorExecution.wireSha256===result.forwardWireSha256);
  const rows=new Map(capture.accountKeys.map((k,i)=>[k,capture.evidence.accounts.result.value[i]]));
  check(rows.get(a.wallet).lamports===result.walletAfterLamports);
  for(const [k,amount] of Object.entries(result.holderAfterAtomic)){
   const row=rows.get(k);check(row.owner===TOKEN&&row.data[1]==='base64');
   const raw=Buffer.from(row.data[0],'base64');check(raw.length===165&&raw.readBigUInt64LE(64).toString()===amount);
  }
 }
 const inputAmount=atomic(p.amountIn,true);check(inputAmount<=1000n);const minimum=atomic(p.minimumAmountOut,true);
 num(p.maxComputeUnits,1,300000);num(req.computeUnits,1,p.maxComputeUnits);
 const price=atomic(req.microLamportsPerCU),maxPrice=atomic(p.maxMicroLamportsPerCU);check(price<=maxPrice&&maxPrice<=10000n);
 const priority=(BigInt(req.computeUnits)*price+999999n)/1000000n;
 const maxPriority=atomic(p.maxPriorityFeeLamports),maxFee=atomic(p.maxTotalFeeLamports,true);
 check(priority<=maxPriority&&maxPriority<=3000n&&maxPriority<=maxFee&&maxFee<=10000n);
 const fee=packet.feeAssertion;fields(fee,['format','network','messageSha256','observedAtMs','lamports']);
 check(fee.format==='message-fee-assertion-1'&&fee.network==='devnet');num(fee.observedAtMs,p.issuedAtMs,now);check(now-fee.observedAtMs<=10000);
 check(atomic(fee.lamports,true)<=maxFee&&atomic(fee.lamports)>=priority);
 const meta=JSON.parse(read(path.join(r.directory,'wallet.json'),4096));check(meta.format==='devnet-wallet-1'&&meta.network==='devnet'&&meta.purpose==='fixed-self-transfer-rehearsal'&&meta.wallet===a.wallet);
 const ordered=[...roles.filter(k=>writable.has(k)).map(k=>a[k]),...roles.filter(k=>!writable.has(k)).map(k=>a[k]),TOKEN,PROGRAM,COMPUTE];
 const all={...a,inputTokenProgram:TOKEN,outputTokenProgram:TOKEN};
 const m=Buffer.concat([Buffer.from([1,0,7,14]),...ordered.map(raw58),raw58(p.blockhash),Buffer.from([3]),
  ix(ordered.indexOf(COMPUTE),[],Buffer.concat([Buffer.from([2]),u32(req.computeUnits)])),
  ix(ordered.indexOf(COMPUTE),[],Buffer.concat([Buffer.from([3]),u64(price)])),
  ix(ordered.indexOf(PROGRAM),ixroles.map(k=>ordered.indexOf(all[k])),Buffer.concat([Buffer.from('8fbe5adac41e33de','hex'),u64(inputAmount),u64(minimum)]))]);
 check(m.toString('base64')===req.messageBase64);
 const unsigned=Buffer.concat([Buffer.from([1]),Buffer.alloc(64),m]);check(unsigned.toString('base64')===packet.unsignedTransactionBase64);
 check(crypto.createHash('sha256').update(m).digest('hex')===fee.messageSha256);
 const der=read(path.join(r.directory,'signer.pk8'),48);check(der.length===48);let key;
 try{key=crypto.createPrivateKey({key:der,format:'der',type:'pkcs8'});}finally{der.fill(0);}
 check(key.asymmetricKeyType==='ed25519');const pub=crypto.createPublicKey(key).export({format:'der',type:'spki'});
 check(pub.length===44&&pub.subarray(12).equals(raw58(a.wallet)));
 check(Date.now()<req.expiresAtMs&&!stopped(r.directory));
 // Exclusive durable attempt precedes crypto.sign; uncertain outcomes are never retried.
 save(path.join(child,'signing-attempt.json'),{planSha256:req.planSha256,atMs:Date.now()});
 check(Date.now()<req.expiresAtMs&&!stopped(r.directory));
 const sig=crypto.sign(null,m,key);const wire=Buffer.concat([Buffer.from([1]),sig,m]).toString('base64');
 save(path.join(child,'signed.json'),{wire});process.stdout.write('{"signed":true}');
}catch{process.stderr.write('Restricted swap signer refused request.\n');process.exitCode=1;}
