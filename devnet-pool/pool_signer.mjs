// Restricted devnet pool signer: independent message reconstruction, no RPC.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const check=v=>{if(!v)throw new Error('refused');};
const alpha='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
function raw58(s){check(typeof s==='string'&&s.length>=32&&s.length<=44);let n=0n;for(const c of s){check(alpha.includes(c));n=n*58n+BigInt(alpha.indexOf(c));}
 let h=n.toString(16);if(h.length%2)h='0'+h;const b=Buffer.concat([Buffer.alloc(s.match(/^1*/)[0].length),n?Buffer.from(h,'hex'):Buffer.alloc(0)]);check(b.length===32);return b;}
function directory(p){check(typeof p==='string'&&path.isAbsolute(p)&&fs.realpathSync(p)===p);const s=fs.lstatSync(p);check(s.isDirectory()&&s.uid===process.getuid()&&(s.mode&0o777)===0o700);}
function read(p,max){const fd=fs.openSync(p,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);try{const s=fs.fstatSync(fd);check(s.isFile()&&s.uid===process.getuid()&&(s.mode&0o777)===0o600&&s.nlink===1&&s.size<=max);return fs.readFileSync(fd);}finally{fs.closeSync(fd);}}
const encode=v=>Array.isArray(v)?'['+v.map(encode).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+encode(v[k])).join(',')+'}':JSON.stringify(v);
const hash=v=>crypto.createHash('sha256').update(encode(v)).digest('hex');
function sync(p){const fd=fs.openSync(p,'r');try{fs.fsyncSync(fd);}finally{fs.closeSync(fd);}}
function save(p,value){const fd=fs.openSync(p,'wx',0o600);try{fs.writeFileSync(fd,encode(value));fs.fsyncSync(fd);}finally{fs.closeSync(fd);}sync(path.dirname(p));}
function fields(v,names){check(v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join('|')===[...names].sort().join('|'));}
function stopped(p){try{fs.lstatSync(path.join(p,'STOP'));return true;}catch(e){if(e.code==='ENOENT')return false;throw e;}}
function key(p){const der=read(p,48);check(der.length===48);try{const k=crypto.createPrivateKey({key:der,format:'der',type:'pkcs8'});check(k.asymmetricKeyType==='ed25519');return k;}finally{der.fill(0);}}
function pub(k){const b=crypto.createPublicKey(k).export({format:'der',type:'spki'});check(b.length===44);return b.subarray(12);}
function number(v,min,max){check(Number.isSafeInteger(v)&&min<=v&&v<=max);return v;}
const u64=v=>{const b=Buffer.alloc(8);b.writeBigUInt64LE(BigInt(v));return b;};
const ix=(p,a,d)=>Buffer.concat([Buffer.from([p,a.length,...a,d.length]),d]);
import {addresses, message} from './pool_policy.mjs';
try {
 const input=fs.readFileSync(0);check(input.length<=4096);const r=JSON.parse(input);
 fields(r,['directory','action']);check(r.action==='sign');directory(r.directory);check(!stopped(r.directory));
 const child=path.join(r.directory,'controlled-pool-v1');directory(child);
 const pairDir=path.join(r.directory,'test-token-pair-v1');directory(pairDir);
 const i=JSON.parse(read(path.join(child,'plan.json'),524288));
 fields(i,['format','network','genesis','pairAccounts','accounts','depositAtomicPerMint','openTime','maximumFeeLamports','maximumCreationFeeLamports','maximumSpendLamports','computeUnits','rents','creationFeeLamports','quotedFeeLamports','walletObservedLamports','contextSlot','blockhash','lastValidBlockHeight','recordedAtMs','expiresAtMs','messageSha256','preAccounts']);
 check(i.format==='devnet-pool-intent-1'&&i.network==='devnet'&&i.genesis==='EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG');
 const walletKey=key(path.join(r.directory,'signer.pk8'));const walletPub=pub(walletKey);
 const meta=JSON.parse(read(path.join(r.directory,'wallet.json'),4096));
 check(meta.format==='devnet-wallet-1'&&meta.network==='devnet'&&meta.purpose==='fixed-self-transfer-rehearsal'&&raw58(meta.wallet).equals(walletPub));
 const pair=JSON.parse(read(path.join(pairDir,'accounts.json'),4096)).accounts;
 fields(pair,['wallet','mintA','holderA','mintB','holderB']);check(raw58(pair.wallet).equals(walletPub));
 for(const n of ['mintA','holderA','mintB','holderB'])check(raw58(pair[n]).equals(pub(key(path.join(pairDir,n+'.pk8')))));
 check(encode(i.pairAccounts)===encode(pair)&&encode(i.accounts)===encode(addresses(pair)));
 check(i.depositAtomicPerMint==='500000000'&&i.openTime===0&&i.maximumFeeLamports===10000&&i.maximumCreationFeeLamports===150000000&&i.maximumSpendLamports===190000000&&i.computeUnits===300000);
 fields(i.rents,['82','165','637','4075']);for(const [s,c] of [[82,2000000],[165,2500000],[637,5000000],[4075,25000000]])number(i.rents[s],1,c);
 number(i.creationFeeLamports,0,150000000);number(i.quotedFeeLamports,1,10000);
 const spend=i.rents[82]+3*i.rents[165]+i.rents[637]+i.rents[4075]+i.creationFeeLamports+10000;
 check(spend<=190000000);number(i.walletObservedLamports,spend,Number.MAX_SAFE_INTEGER);
 number(i.contextSlot,1,Number.MAX_SAFE_INTEGER);number(i.lastValidBlockHeight,1,Number.MAX_SAFE_INTEGER);
 const now=Date.now();number(i.recordedAtMs,now-30000,now);check(i.expiresAtMs===i.recordedAtMs+30000&&now<i.expiresAtMs);
 const msg=message(pair,i.blockhash);check(65+msg.length<=1232&&crypto.createHash('sha256').update(msg).digest('hex')===i.messageSha256);
 check(Date.now()<i.expiresAtMs&&!stopped(r.directory));
 save(path.join(child,'signing-attempt.json'),{intentSha256:hash(i),atMs:Date.now()});
 check(Date.now()<i.expiresAtMs&&!stopped(r.directory));
 const wire=Buffer.concat([Buffer.from([1]),crypto.sign(null,msg,walletKey),msg]).toString('base64');
 save(path.join(child,'signed.json'),{wire,intentSha256:hash(i)});process.stdout.write('{"signed":true}');
}catch{process.stderr.write('Devnet pool signer refused request.\n');process.exitCode=1;}
