// Narrow local signer. No network, key import, arbitrary recipient or general signing.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const check = v => { if (!v) throw new Error('signer-refused'); };
function directory(dir) {
  check(typeof dir === 'string' && path.isAbsolute(dir) && fs.realpathSync(dir) === dir);
  const s=fs.lstatSync(dir);
  check(s.isDirectory() && s.uid===process.getuid() && (s.mode & 0o777)===0o700);
}
function readKey(dir) {
  const fd=fs.openSync(path.join(dir,'signer.pk8'),fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
  try {
    const s=fs.fstatSync(fd);
    check(s.isFile() && s.uid===process.getuid() && (s.mode & 0o777)===0o600 && s.nlink===1 && s.size===48);
    const bytes=fs.readFileSync(fd);
    try { const key=crypto.createPrivateKey({key:bytes,format:'der',type:'pkcs8'}); check(key.asymmetricKeyType==='ed25519'); return key; }
    finally { bytes.fill(0); }
  } finally { fs.closeSync(fd); }
}
function publicBytes(key) {
  const der=crypto.createPublicKey(key).export({format:'der',type:'spki'});
  check(der.length===44); return der.subarray(12);
}
try {
  const input=fs.readFileSync(0); check(input.length<=4096);
  const r=JSON.parse(input); check(r.network==='devnet'); directory(r.directory);
  if (r.action==='generate') {
    const {privateKey}=crypto.generateKeyPairSync('ed25519');
    const der=privateKey.export({format:'der',type:'pkcs8'}); check(der.length===48);
    const fd=fs.openSync(path.join(r.directory,'signer.pk8'),'wx',0o600);
    try { fs.writeFileSync(fd,der); fs.fsyncSync(fd); } finally { fs.closeSync(fd); der.fill(0); }
    const d=fs.openSync(r.directory,'r'); try {fs.fsyncSync(d);} finally {fs.closeSync(d);}
    process.stdout.write(JSON.stringify({publicKeyBase64:publicBytes(privateKey).toString('base64')}));
  } else {
    const key=readKey(r.directory); const pub=publicBytes(key);
    if (r.action==='public') process.stdout.write(JSON.stringify({publicKeyBase64:pub.toString('base64')}));
    else {
      check(r.action==='sign' && typeof r.messageBase64==='string');
      const m=Buffer.from(r.messageBase64,'base64');
      // One signer, payer + System keys, blockhash, Transfer(1) with source=destination.
      const tail=Buffer.from([1,1,2,0,0,12,2,0,0,0,1,0,0,0,0,0,0,0]);
      check(m.length===118 && m.toString('base64')===r.messageBase64 &&
        m.subarray(0,4).equals(Buffer.from([1,0,1,2])) && m.subarray(4,36).equals(pub) &&
        m.subarray(36,68).equals(Buffer.alloc(32)) && m.subarray(100).equals(tail));
      process.stdout.write(JSON.stringify({signatureBase64:crypto.sign(null,m,key).toString('base64')}));
    }
  }
} catch { process.stderr.write('Local signer refused the request.\n'); process.exitCode=1; }
