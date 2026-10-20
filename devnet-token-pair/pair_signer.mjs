// Restricted atomic two-mint standard SPL setup. No RPC, arbitrary messages or key export.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const check=v=>{if(!v)throw new Error('refused');};
const alpha='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
function raw58(s){check(typeof s==='string'&&s.length>=32&&s.length<=44);let n=0n;for(const c of s){check(alpha.includes(c));n=n*58n+BigInt(alpha.indexOf(c));}
 let h=n.toString(16);if(h.length%2)h='0'+h;const b=Buffer.concat([Buffer.alloc(s.match(/^1*/)[0].length),n?Buffer.from(h,'hex'):Buffer.alloc(0)]);check(b.length===32);return b;}
function directory(p){check(typeof p==='string'&&path.isAbsolute(p)&&fs.realpathSync(p)===p);const s=fs.lstatSync(p);check(s.isDirectory()&&s.uid===process.getuid()&&(s.mode&0o777)===0o700);}
function read(p,max){const fd=fs.openSync(p,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);try{const s=fs.fstatSync(fd);check(s.isFile()&&s.uid===process.getuid()&&(s.mode&0o777)===0o600&&s.nlink===1&&s.size<=max);return fs.readFileSync(fd);}finally{fs.closeSync(fd);}}
function canonical(v){if(Array.isArray(v))return v.map(canonical);if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])]));return v;}
const encode=v=>JSON.stringify(canonical(v));
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
const names=['wallet','mintA','holderA','mintB','holderB'];
const token=raw58('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA');
try{
 const input=fs.readFileSync(0);check(input.length<=4096);const r=JSON.parse(input);
 fields(r,['directory','action']);check(['generate','public','sign'].includes(r.action));directory(r.directory);
 const child=path.join(r.directory,'test-token-pair-v1');directory(child);
 if(r.action!=='public')check(!stopped(r.directory));
 if(r.action==='generate'){
  for(const n of names.slice(1)){
   const {privateKey}=crypto.generateKeyPairSync('ed25519');const der=privateKey.export({format:'der',type:'pkcs8'});
   const fd=fs.openSync(path.join(child,n+'.pk8'),'wx',0o600);
   try{fs.writeFileSync(fd,der);fs.fsyncSync(fd);}finally{fs.closeSync(fd);der.fill(0);}
  }sync(child);
 }
 const keys=[key(path.join(r.directory,'signer.pk8')),...names.slice(1).map(n=>key(path.join(child,n+'.pk8')))];
 const pubs=keys.map(pub);check(new Set(pubs.map(b=>b.toString('hex'))).size===5);
 const walletMeta=JSON.parse(read(path.join(r.directory,'wallet.json'),4096));
 check(walletMeta.format==='devnet-wallet-1'&&walletMeta.network==='devnet'&&walletMeta.purpose==='fixed-self-transfer-rehearsal'&&raw58(walletMeta.wallet).equals(pubs[0]));
 if(r.action==='generate'||r.action==='public')process.stdout.write(JSON.stringify({publicKeysBase64:pubs.map(b=>b.toString('base64'))}));
 else{
  const i=JSON.parse(read(path.join(child,'plan.json'),16384));
  fields(i,['format','network','genesis','accounts','supplyAtomicPerMint','decimals','mintAuthorityAfter','freezeAuthority','maximumFeeLamports','maximumSpendLamports','mintRentLamports','holderRentLamports','quotedFeeLamports','walletObservedLamports','contextSlot','blockhash','lastValidBlockHeight','recordedAtMs','expiresAtMs','messageSha256']);
  check(i.format==='devnet-token-pair-intent-1'&&i.network==='devnet'&&i.genesis==='EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG');fields(i.accounts,names);
  names.forEach((n,j)=>check(raw58(i.accounts[n]).equals(pubs[j])));
  check(i.supplyAtomicPerMint==='1000000000'&&i.decimals===6&&i.mintAuthorityAfter===null&&i.freezeAuthority===null&&i.maximumFeeLamports===50000&&i.maximumSpendLamports===6000000);
  number(i.mintRentLamports,1,2000000);number(i.holderRentLamports,1,2500000);number(i.quotedFeeLamports,1,50000);
  const spend=2*(i.mintRentLamports+i.holderRentLamports)+50000;check(spend<=6000000);number(i.walletObservedLamports,spend,Number.MAX_SAFE_INTEGER);
  number(i.contextSlot,1,Number.MAX_SAFE_INTEGER);number(i.lastValidBlockHeight,1,Number.MAX_SAFE_INTEGER);
  const now=Date.now();number(i.recordedAtMs,now-30000,now);check(i.expiresAtMs===i.recordedAtMs+30000&&now<i.expiresAtMs);
  const create=(idx,size,rent)=>ix(5,[0,idx],Buffer.concat([Buffer.alloc(4),u64(rent),u64(size),token]));
  const ops=[];
  for(const [m,h] of [[1,2],[3,4]])ops.push(create(m,82,i.mintRentLamports),ix(6,[m],Buffer.concat([Buffer.from([20,6]),pubs[0],Buffer.from([0])])),
    create(h,165,i.holderRentLamports),ix(6,[h,m],Buffer.concat([Buffer.from([18]),pubs[0]])),
    ix(6,[m,h,0],Buffer.concat([Buffer.from([14]),u64(1000000000),Buffer.from([6])])),ix(6,[m,0],Buffer.from([6,0,0])));
  const msg=Buffer.concat([Buffer.from([5,0,2,7]),...pubs,Buffer.alloc(32),token,raw58(i.blockhash),Buffer.from([12]),...ops]);
  check(1+5*64+msg.length<=1232&&crypto.createHash('sha256').update(msg).digest('hex')===i.messageSha256);
  check(Date.now()<i.expiresAtMs&&!stopped(r.directory));
  save(path.join(child,'signing-attempt.json'),{intentSha256:hash(i),atMs:Date.now()});
  check(Date.now()<i.expiresAtMs&&!stopped(r.directory));
  const wire=Buffer.concat([Buffer.from([5]),...keys.map(k=>crypto.sign(null,msg,k)),msg]).toString('base64');
  save(path.join(child,'signed.json'),{wire,intentSha256:hash(i)});process.stdout.write('{"signed":true}');
 }
}catch{process.stderr.write('Test token pair signer refused request.\n');process.exitCode=1;}
