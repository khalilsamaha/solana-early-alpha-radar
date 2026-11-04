// Internal restricted devnet key backend. No network, transaction sender or key export.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {raw58} from '../devnet-pool/pool_policy.mjs';
import {check,text,bytesHash,validate} from './exit_signer_contract.mjs';

function directory(p) {
  check(typeof p === 'string' && path.isAbsolute(p) && fs.realpathSync(p) === p);
  const s=fs.lstatSync(p); check(s.isDirectory() && s.uid === process.getuid() && (s.mode&0o777) === 0o700);
  return p;
}
function read(p,max) {
  const fd=fs.openSync(p,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
  try {
    const s=fs.fstatSync(fd); check(s.isFile() && s.uid === process.getuid() && (s.mode&0o777) === 0o600 && s.nlink === 1 && s.size <= max);
    return fs.readFileSync(fd);
  } finally {fs.closeSync(fd);}
}
function exists(p) {try {fs.lstatSync(p); return true;} catch(e) {if(e.code === 'ENOENT') return false; throw e;}}
function save(p,value) {
  const fd=fs.openSync(p,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_NOFOLLOW,0o600);
  try {fs.writeFileSync(fd,text(value)); fs.fsyncSync(fd);} finally {fs.closeSync(fd);}
  const d=fs.openSync(path.dirname(p),'r'); try {fs.fsyncSync(d);} finally {fs.closeSync(d);}
}
try {
  const input=fs.readFileSync(0); check(input.length <= 4096);
  const r=JSON.parse(input); check(Object.keys(r).sort().join('|') === 'directory|requestSha256');
  const root=directory(r.directory), storage=directory(root+'-entry-handoff-v1');
  const attempt=path.join(storage,'exit-signer-attempt.json'), ack=path.join(storage,'exit-signer-ack.json');
  check(!exists(path.join(root,'STOP')) && !exists(attempt) && !exists(ack));
  const file=path.join(storage,'entry.admission.sqlite');
  // Refuse recovery sidecars; the independent process only reads a committed ledger.
  for (const suffix of ['-journal','-wal','-shm']) check(!exists(file+suffix));
  // Validate the file without loading the complete SQLite database into memory.
  const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
  try {const s=fs.fstatSync(fd);check(s.isFile() && s.uid === process.getuid() && (s.mode&0o777) === 0o600 && s.nlink === 1 && s.size <= 64*1024*1024);} finally {fs.closeSync(fd);}
  const db=new DatabaseSync(file,{readOnly:true}); let data;
  try {
    db.exec('PRAGMA trusted_schema=OFF; PRAGMA query_only=ON; PRAGMA busy_timeout=1000; BEGIN');
    check(db.prepare('PRAGMA application_id').get().application_id === 0x52494A31);
    check(db.prepare('PRAGMA user_version').get().user_version === 1 && db.prepare('PRAGMA journal_mode').get().journal_mode === 'delete');
    for (const table of ['admission_policy','admission_events','intents','events','admission_exit_signing','admission_exit_preparation','admission_entry_accounting'])
      check(db.prepare('SELECT type FROM sqlite_master WHERE name=?').get(table)?.type === 'table');
    check(db.prepare('SELECT COUNT(*) n FROM intents').get().n === 0 && db.prepare('SELECT COUNT(*) n FROM events').get().n === 0);
    const p=db.prepare('SELECT CASE WHEN length(value)<=4096 THEN value ELSE NULL END value FROM admission_policy WHERE id=1').get();
    check(p && typeof p.value === 'string');const policy=JSON.parse(p.value);check(text(policy) === p.value);
    const rows=table=>db.prepare(`SELECT seq,at_ms,CASE WHEN length(value)<=8192 THEN value ELSE NULL END value,previous_hash,hash FROM ${table} ORDER BY seq LIMIT 9`).all();
    const single=(table,cap)=>{const rs=db.prepare(`SELECT id,CASE WHEN length(value)<=? THEN value ELSE NULL END value,hash FROM ${table} LIMIT 2`).all(cap);check(rs.length===1);return rs[0];};
    const replacement=db.prepare('SELECT type FROM sqlite_master WHERE name=?').get('admission_exit_replacement');
    check(!replacement || replacement.type==='table');
    data={replacementRow:replacement ? single('admission_exit_replacement',24*1024*1024+16384+2048) : null,
      policy,admissionRows:rows('admission_events'),signingRows:rows('admission_exit_signing'),
      preparationRow:single('admission_exit_preparation',24*1024*1024+16384),accountingRow:single('admission_entry_accounting',8192)};
  const metadata=JSON.parse(read(path.join(root,'wallet.json'),4096));
  const setup=directory(path.join(root,'controlled-pool-v1'));
  const plan=JSON.parse(read(path.join(setup,'plan.json'),512*1024));
  check(plan.format === 'devnet-pool-intent-1' && plan.network === 'devnet' &&
    plan.genesis === 'EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG');
  const checked=validate(data,metadata,plan.pairAccounts,r.requestSha256,Date.now());
  function fresh() {const now=Date.now();check(!exists(path.join(root,'STOP')) && now >= checked.notBeforeMs && now < checked.deadline);return now;}
  fresh();
  const der=read(path.join(root,'signer.pk8'),48); let key;
  try {check(der.length === 48); key=crypto.createPrivateKey({key:der,format:'der',type:'pkcs8'});} finally {der.fill(0);}
  check(key.asymmetricKeyType === 'ed25519');
  const pub=crypto.createPublicKey(key).export({format:'der',type:'spki'});
  check(pub.length === 44 && pub.subarray(12).equals(raw58(checked.wallet)));
  fresh();
  // Exclusive durable marker BEFORE crypto.sign. Refusal/crash after it stays unknown.
  save(attempt,{format:'exit-signer-attempt-1',requestSha256:checked.requestHash,
    signingHeadSha256:checked.signingHead,preparationSha256:checked.preparationHash,atMs:fresh()});
  fresh();
  const signature=crypto.sign(null,checked.message,key);
  const wire=Buffer.concat([Buffer.from([1]),signature,checked.message]);
  save(ack,{format:'exit-signer-ack-1',requestSha256:checked.requestHash,
    signedTransactionBase64:wire.toString('base64'),wireSha256:bytesHash(wire)});
  db.exec('COMMIT');
  process.stdout.write('{"state":"exit-signed-recorded"}');
  } finally {db.close();}
} catch {
  process.stderr.write('Restricted exit signer refused; preserve attempt and acknowledgment files.\n');
  process.exitCode=1;
}
