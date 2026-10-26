import fs from 'node:fs';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {createHash,randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const core=path.dirname(fileURLToPath(import.meta.url));
const sha=b=>createHash('sha256').update(b).digest('hex');
export function cacheProvenance(){
 const m=JSON.parse(fs.readFileSync(path.join(core,'stats-compact-manifest.json'),'utf8'));
 for(const [name,hash] of Object.entries(m.semanticFiles)){
  const file=path.resolve(core,'../..',name),s=fs.lstatSync(file);
  if(!s.isFile()||fs.realpathSync(file)!==file||s.size>2097152||sha(fs.readFileSync(file))!==hash)throw Error('source-mismatch');
 }
 if(sha(fs.readFileSync(path.join(core,'stats-compact-store.js')))!==m.storeSha256)throw Error('source-mismatch');
 return {provenance:sha(JSON.stringify({version:m.version,semanticFiles:m.semanticFiles,store:m.storeSha256})),compatibleProvenance:m.compatibleProvenance};
}
function privateFile(file){
 const s=fs.lstatSync(file);
 if(!s.isFile()||s.uid!==process.getuid()||(s.mode&0o077)||s.nlink!==1||fs.realpathSync(file)!==file)throw Error('cache-path');
 return s;
}
function createPrivate(file){try{fs.closeSync(fs.openSync(file,'wx',0o600));}catch(e){if(e.code!=='EEXIST')throw e;}return privateFile(file);}
export function acquireCompactLease(database){
 const data=path.dirname(database);
 if(fs.realpathSync(data)!==data)throw Error('cache-path');
 const directory=path.join(data,'statistics-cache-lab-1');
 try{fs.mkdirSync(directory,{mode:0o700});}catch(e){if(e.code!=='EEXIST')throw e;}
 return leaseInDirectory(directory);
}
function leaseInDirectory(directory){
 const ds=fs.lstatSync(directory);
 if(!ds.isDirectory()||ds.uid!==process.getuid()||(ds.mode&0o077)||fs.realpathSync(directory)!==directory)throw Error('cache-path');
 const leasePath=path.join(directory,'runtime-lease.sqlite'),lock=path.join(directory,'active.lock'),cache=path.join(directory,'compact.sqlite');
 createPrivate(leasePath);
 for(const suffix of ['-journal','-wal','-shm'])if(fs.existsSync(leasePath+suffix))privateFile(leasePath+suffix);
 let db,token;
 try{
  db=new DatabaseSync(leasePath,{timeout:100});
  db.exec('PRAGMA journal_mode=DELETE; CREATE TABLE IF NOT EXISTS lease(version INTEGER); BEGIN EXCLUSIVE');
  // The OS releases this SQLite lock on process death. Holding it proves no
  // other runtime owns a leftover runtime marker, even after PID reuse.
  if(fs.existsSync(lock)){
   const s=privateFile(lock);if(s.size>512)throw Error('cache-busy');
   const text=fs.readFileSync(lock,'utf8');let prior;
   try{prior=JSON.parse(text);}catch{}
   if(prior?.format!=='statistics-runtime-lease-1'){
    if(!/^\d+$/.test(text))throw Error('cache-busy');
    const pid=Number(text);if(!Number.isSafeInteger(pid)||pid<=0)throw Error('cache-busy');
    try{process.kill(pid,0);throw Error('cache-busy');}catch(e){if(e.code!=='ESRCH')throw Error('cache-busy');}
   }
   fs.unlinkSync(lock);
  }
  token=randomUUID();fs.writeFileSync(lock,JSON.stringify({format:'statistics-runtime-lease-1',token,pid:process.pid}),{flag:'wx',mode:0o600});
  createPrivate(cache);
  for(const suffix of ['-journal','-wal','-shm'])if(fs.existsSync(cache+suffix))privateFile(cache+suffix);
  let released=false;
  return {cache,release(){if(released)return;released=true;try{const current=JSON.parse(fs.readFileSync(lock,'utf8'));if(current.token===token)fs.unlinkSync(lock);}finally{db.close();}}};
 }catch(e){
  if(token)try{const current=JSON.parse(fs.readFileSync(lock,'utf8'));if(current.token===token)fs.unlinkSync(lock);}catch{}
  try{db?.close();}catch{}
  if(e.code==='ERR_SQLITE_ERROR'||e.code==='EEXIST')throw Error('cache-busy');throw e;
 }
}
