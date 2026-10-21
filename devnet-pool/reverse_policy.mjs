// Pure independent entry-wire/receipt checks for the restricted reverse signer.
// No files, network, signing, arbitrary route instructions or mutable configuration.
import crypto from 'node:crypto';
import {addresses, raw58} from './pool_policy.mjs';
const check=v=>{if(!v)throw new Error('reverse-policy');};
const TOKEN='TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA';
const PROGRAM='DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb';
const COMPUTE='ComputeBudget111111111111111111111111111111';
const names=['wallet','authority','config','pool','source','destination','inputVault','outputVault','inputMint','outputMint','observation'];
const writable=new Set(['wallet','pool','source','destination','inputVault','outputVault','observation']);
const ixnames=['wallet','authority','config','pool','source','destination','inputVault','outputVault','inputTokenProgram','outputTokenProgram','inputMint','outputMint','observation'];
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const whole=n=>Number.isSafeInteger(n)&&n>=0;
function atomic(s){check(typeof s==='string'&&/^(0|[1-9][0-9]{0,19})$/.test(s));const n=BigInt(s);check(n<2n**64n);return n;}
function bytes(s){check(typeof s==='string');const b=Buffer.from(s,'base64');check(b.toString('base64')===s);return b;}
const u64=n=>{const b=Buffer.alloc(8);b.writeBigUInt64LE(BigInt(n));return b;};
function fixedEntryMessage(a,blockhash){
 const keys=[...names.filter(k=>writable.has(k)).map(k=>a[k]),...names.filter(k=>!writable.has(k)).map(k=>a[k]),TOKEN,PROGRAM,COMPUTE];
 const all={...a,inputTokenProgram:TOKEN,outputTokenProgram:TOKEN};
 const ix=(program,accounts,data)=>Buffer.concat([Buffer.from([keys.indexOf(program),accounts.length,...accounts.map(k=>keys.indexOf(k)),data.length]),data]);
 const cu=Buffer.alloc(5);cu[0]=2;cu.writeUInt32LE(300000,1);
 const instructions=[ix(COMPUTE,[],cu),ix(COMPUTE,[],Buffer.concat([Buffer.from([3]),u64(0)])),
  ix(PROGRAM,ixnames.map(k=>all[k]),Buffer.concat([Buffer.from('8fbe5adac41e33de','hex'),u64(1000),u64(990)]))];
 return {keys,message:Buffer.concat([Buffer.from([1,0,7,14]),...keys.map(raw58),raw58(blockhash),Buffer.from([3]),...instructions])};
}
export function deriveReverse(pair,plan,wireText,record){
 const d=addresses(pair);
 const a={wallet:d.wallet,authority:d.authority,config:d.config,pool:d.pool,source:d.holder0,destination:d.holder1,
  inputVault:d.vault0,outputVault:d.vault1,inputMint:d.mint0,outputMint:d.mint1,observation:d.observation};
 check(plan.format==='swap-signing-plan-1');const p=plan.packet.policy;
 check(p.network==='devnet'&&p.amountIn==='1000'&&p.minimumAmountOut==='990'&&p.maxComputeUnits===300000&&
  p.maxMicroLamportsPerCU==='0'&&p.maxPriorityFeeLamports==='0'&&p.maxTotalFeeLamports==='10000');
 check(Object.keys(p.accounts).length===11&&names.every(k=>p.accounts[k]===a[k]));
 const {keys,message}=fixedEntryMessage(a,p.blockhash),wire=bytes(wireText);
 check(wire.length===65+message.length&&wire[0]===1&&wire.subarray(65).equals(message));
 const publicKey=crypto.createPublicKey({key:Buffer.concat([Buffer.from('302a300506032b6570032100','hex'),raw58(a.wallet)]),format:'der',type:'spki'});
 check(crypto.verify(null,message,publicKey,wire.subarray(1,65)));
 const tx=record.transaction,st=record.status,m=tx.meta;
 check(st.confirmationStatus==='finalized'&&st.confirmations===null&&st.err===null&&whole(st.slot)&&
  tx.slot===st.slot&&tx.version==='legacy'&&Array.isArray(tx.transaction)&&tx.transaction.length===2&&
  tx.transaction[0]===wireText&&tx.transaction[1]==='base64'&&m.err===null);
 const fee=atomic(plan.packet.feeAssertion.lamports);
 check(fee>0n&&fee<=10000n&&whole(m.fee)&&BigInt(m.fee)===fee&&plan.packet.feeAssertion.messageSha256===hash(message));
 check(m.loadedAddresses===undefined||(Array.isArray(m.loadedAddresses.writable)&&m.loadedAddresses.writable.length===0&&
  Array.isArray(m.loadedAddresses.readonly)&&m.loadedAddresses.readonly.length===0));
 check(Array.isArray(m.preBalances)&&Array.isArray(m.postBalances)&&m.preBalances.length===14&&m.postBalances.length===14&&
  m.preBalances.every(whole)&&m.postBalances.every(whole));
 check(BigInt(m.preBalances[0])-BigInt(m.postBalances[0])===fee&&m.preBalances.slice(1).every((v,i)=>m.postBalances[i+1]===v));
 const tokenNames=['source','destination','inputVault','outputVault'];
 function index(rows){
  check(Array.isArray(rows)&&rows.length===4);const out=new Map();
  for(const row of rows){check(whole(row.accountIndex)&&row.accountIndex<14);const k=keys[row.accountIndex];
   check(!out.has(k));out.set(k,row);}
  check(tokenNames.every(n=>out.has(a[n])));return out;
 }
 const before=index(m.preTokenBalances),after=index(m.postTokenBalances),effects={};
 for(const [i,n] of tokenNames.entries()){
  const k=a[n],mint=a[i===0||i===2?'inputMint':'outputMint'],owner=a[i<2?'wallet':'authority'];
  const amounts=[before.get(k),after.get(k)].map(row=>{
   check(row.mint===mint&&row.owner===owner&&row.programId===TOKEN&&row.uiTokenAmount.decimals===6);
   return atomic(row.uiTokenAmount.amount);
  });effects[n]={before:amounts[0],after:amounts[1],delta:amounts[1]-amounts[0]};
 }
 const qty=effects.destination.delta;
 check(effects.source.delta===-1000n&&qty>=990n&&qty<=1000n&&effects.inputVault.delta===1000n&&effects.outputVault.delta===-qty);
 const reverse={...a,source:a.destination,destination:a.source,inputVault:a.outputVault,outputVault:a.inputVault,inputMint:a.outputMint,outputMint:a.inputMint};
 return {accounts:reverse,amountIn:qty.toString(),minimumAmountOut:(qty*99n/100n).toString(),
  forwardWireSha256:hash(wire),walletAfterLamports:m.postBalances[0],
  holderAfterAtomic:{[a.source]:effects.source.after.toString(),[a.destination]:effects.destination.after.toString()}};
}
