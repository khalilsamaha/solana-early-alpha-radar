// Separate, exact WSOL lifecycle policy. No RPC, arbitrary message signing or key export.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const check=v=>{if(!v)throw new Error('refused');};
const alphabet='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
function raw58(s){let n=0n;for(const c of s){check(alphabet.includes(c));n=n*58n+BigInt(alphabet.indexOf(c));}
 let hex=n.toString(16);if(hex.length%2)hex='0'+hex;const b=Buffer.concat([Buffer.alloc(s.match(/^1*/)[0].length),n?Buffer.from(hex,'hex'):Buffer.alloc(0)]);check(b.length===32);return b;}
const TOKEN=raw58('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA');
const NATIVE=raw58('So11111111111111111111111111111111111111112');
function directory(p){check(typeof p==='string'&&path.isAbsolute(p)&&fs.realpathSync(p)===p);const s=fs.lstatSync(p);
 check(s.isDirectory()&&s.uid===process.getuid()&&(s.mode&0o777)===0o700);}
function readKey(p){const fd=fs.openSync(p,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
 try{const s=fs.fstatSync(fd);check(s.isFile()&&s.uid===process.getuid()&&(s.mode&0o777)===0o600&&s.nlink===1&&s.size===48);
 const bytes=fs.readFileSync(fd);try{const k=crypto.createPrivateKey({key:bytes,format:'der',type:'pkcs8'});check(k.asymmetricKeyType==='ed25519');return k;}finally{bytes.fill(0);}}finally{fs.closeSync(fd);}}
function pub(k){const b=crypto.createPublicKey(k).export({format:'der',type:'spki'});check(b.length===44);return b.subarray(12);}
const u64=n=>{const b=Buffer.alloc(8);b.writeBigUInt64LE(BigInt(n));return b;};
const ix=(p,a,d)=>Buffer.concat([Buffer.from([p,a.length,...a,d.length]),d]);
try{
 const input=fs.readFileSync(0);check(input.length<=4096);const r=JSON.parse(input);
 check(r.network==='devnet');directory(r.directory);
 const child=path.join(r.directory,'token-lifecycle-v1');directory(child);
 if(r.action==='generate'){
  // A partial initialization is deliberately not repaired or overwritten.
  for(const name of ['source.pk8','destination.pk8']){
   const {privateKey}=crypto.generateKeyPairSync('ed25519');const der=privateKey.export({format:'der',type:'pkcs8'});
   const fd=fs.openSync(path.join(child,name),'wx',0o600);
   try{fs.writeFileSync(fd,der);fs.fsyncSync(fd);}finally{fs.closeSync(fd);der.fill(0);}
  }
  const fd=fs.openSync(child,'r');try{fs.fsyncSync(fd);}finally{fs.closeSync(fd);}
 }
 const keys=[readKey(path.join(r.directory,'signer.pk8')),readKey(path.join(child,'source.pk8')),readKey(path.join(child,'destination.pk8'))];
 const pubs=keys.map(pub);
 if(r.action==='generate'||r.action==='public')process.stdout.write(JSON.stringify({publicKeysBase64:pubs.map(x=>x.toString('base64'))}));
 else{
  check(r.action==='sign'&&Number.isSafeInteger(r.rent)&&r.rent>0&&r.rent<=2500000);
  const bh=Buffer.from(r.blockhashBase64,'base64');check(bh.length===32&&bh.toString('base64')===r.blockhashBase64);
  const create=(idx,fund)=>ix(3,[0,idx],Buffer.concat([Buffer.alloc(4),u64(fund),u64(165),TOKEN]));
  const init=idx=>ix(4,[idx,5],Buffer.concat([Buffer.from([18]),pubs[0]]));
  const m=Buffer.concat([Buffer.from([3,0,3,6]),...pubs,Buffer.alloc(32),TOKEN,NATIVE,bh,Buffer.from([7]),
   create(1,r.rent+1000),init(1),create(2,r.rent),init(2),ix(4,[1,5,2,0],Buffer.concat([Buffer.from([12]),u64(1000),Buffer.from([9])])),
   ix(4,[1,0,0],Buffer.from([9])),ix(4,[2,0,0],Buffer.from([9]))]);
  check(m.toString('base64')===r.messageBase64);
  process.stdout.write(JSON.stringify({signaturesBase64:keys.map(k=>crypto.sign(null,m,k).toString('base64'))}));
 }
}catch{process.stderr.write('Token lifecycle signer refused request.\n');process.exitCode=1;}
