// Experimental derived cache. The reviewed source inserts immutable events and prunes rows.
import fs from 'node:fs';
import {DatabaseSync} from 'node:sqlite';
import {performance} from 'node:perf_hooks';
export const CACHE_VERSION='compact-statistics-1';
export const KINDS=['alerts','outcomes','research-entries','research-outcomes'];
const MAX_ROW=262144,MAX_BYTES=1073741824,MAX_ROWS=100000;
export class CompactStore {
 constructor({source,cache,compact,provenance=CACHE_VERSION,now=()=>performance.now()}) {
  this.sourcePath=source;this.compact=compact;this.now=now;
  const a=fs.statSync(source),b=fs.statSync(cache);
  if(a.dev===b.dev&&a.ino===b.ino)throw Error('cache-source-alias');
  this.identity=`${a.dev}:${a.ino}`;
  this.source=new DatabaseSync(source,{readOnly:true,timeout:500});
  try{
   this.source.exec('PRAGMA query_only=ON; PRAGMA cache_size=-4096');
   this.cache=new DatabaseSync(cache,{timeout:500});
   this.cache.exec(`PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL; PRAGMA cache_size=-4096;
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS rows(kind TEXT NOT NULL,seq INTEGER NOT NULL,id TEXT NOT NULL,at INTEGER NOT NULL,rawBytes INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(kind,seq));
    CREATE TABLE IF NOT EXISTS totals(kind TEXT PRIMARY KEY,n INTEGER NOT NULL CHECK(n>=0),bytes INTEGER NOT NULL CHECK(bytes>=0));
    CREATE TRIGGER IF NOT EXISTS rows_insert AFTER INSERT ON rows BEGIN
      INSERT INTO totals VALUES(new.kind,1,new.rawBytes) ON CONFLICT(kind) DO UPDATE SET n=n+1,bytes=bytes+new.rawBytes;
    END;
    CREATE TRIGGER IF NOT EXISTS rows_delete AFTER DELETE ON rows BEGIN
      UPDATE totals SET n=n-1,bytes=bytes-old.rawBytes WHERE kind=old.kind;
    END;
    CREATE TRIGGER IF NOT EXISTS rows_update AFTER UPDATE ON rows BEGIN
      UPDATE totals SET bytes=bytes-old.rawBytes+new.rawBytes WHERE kind=new.kind;
    END;`);
   const registered=this.get('identity');
   if(registered&&registered!==this.identity)throw Error('source-replaced');
   const version=this.get('version');if(version&&version!==CACHE_VERSION)throw Error('cache-version');
   if(this.get('provenance')&&this.get('provenance')!==provenance)throw Error('cache-version');
   this.cache.exec('BEGIN IMMEDIATE');
   this.put('identity',this.identity);this.put('version',CACHE_VERSION);this.put('provenance',provenance);
   if(!this.get('progress'))this.put('progress',{kind:0,cursor:0});
   this.cache.exec('COMMIT');
  }catch(e){this.cache?.close();this.source.close();throw e;}
 }
 get(key){const r=this.cache.prepare('SELECT value FROM meta WHERE key=?').get(key);return r?JSON.parse(r.value):null;}
 put(key,value){this.cache.prepare('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value').run(key,JSON.stringify(value));}
 checkIdentity(){const s=fs.statSync(this.sourcePath);if(`${s.dev}:${s.ino}`!==this.identity)throw Error('source-replaced');}
 transaction(fn){
  this.checkIdentity();const start=this.now();let wal=0;
  const walSize=()=>{try{return fs.statSync(this.sourcePath+'-wal').size;}catch{return 0;}};
  wal=walSize();const guard=()=>{if(this.now()-start>8000)throw Error('read-timeout');if(walSize()-wal>67108864)throw Error('wal-growth-limit');};
  this.source.exec('BEGIN');
  try{this.cache.exec('BEGIN IMMEDIATE');try{const value=fn(guard);guard();this.checkIdentity();this.cache.exec('COMMIT');return value;}catch(e){this.cache.exec('ROLLBACK');throw e;}}
  finally{this.source.exec('ROLLBACK');}
 }
 decode(row,kind){
  if(!Number.isSafeInteger(row.seq)||row.seq<=0||typeof row.id!=='string'||Buffer.byteLength(row.id)>4096||!Number.isSafeInteger(row.at))throw Error('source-row-invalid');
  if(row.rawBytes>MAX_ROW)throw Error('row-size-limit');
  if(typeof row.data!=='string')throw Error('source-row-invalid');
  return kind==='research-events'?JSON.parse(row.data):this.compact(kind,JSON.parse(row.data));
 }
 step(){return this.transaction(guard=>{
  let p=this.get('progress');
  if(p.kind>=KINDS.length)return {phase:'validation-required',readRows:0,reusedRows:0};
  const kind=KINDS[p.kind],page=this.source.prepare('SELECT seq,id,at FROM events WHERE kind=? AND seq>? ORDER BY seq LIMIT 128').all(kind,p.cursor);
  let readRows=0,reusedRows=0;
  const lookup=this.cache.prepare('SELECT id,at FROM rows WHERE kind=? AND seq=?');
  const raw=this.source.prepare('SELECT seq,id,at,length(CAST(data AS BLOB)) AS rawBytes,CASE WHEN length(CAST(data AS BLOB))<=262144 THEN data ELSE NULL END AS data FROM events WHERE kind=? AND seq=?');
  const save=this.cache.prepare('INSERT INTO rows VALUES(?,?,?,?,?,?) ON CONFLICT(kind,seq) DO UPDATE SET id=excluded.id,at=excluded.at,rawBytes=excluded.rawBytes,data=excluded.data');
  for(const row of page){guard();const old=lookup.get(kind,row.seq);
   if(old?.id===row.id&&old?.at===row.at){reusedRows++;continue;}
   const full=raw.get(kind,row.seq),value=this.decode(full,kind);
   save.run(kind,row.seq,row.id,row.at,full.rawBytes,JSON.stringify(value));readRows++;
  }
  if(page.length){
   const end=page.at(-1).seq;
   this.cache.prepare(`DELETE FROM rows WHERE kind=? AND seq>? AND seq<=? AND seq NOT IN (${page.map(()=>'?').join(',')})`).run(kind,p.cursor,end,...page.map(r=>r.seq));
   p={kind:p.kind,cursor:end};
  }else{
   this.cache.prepare('DELETE FROM rows WHERE kind=? AND seq>?').run(kind,p.cursor);p={kind:p.kind+1,cursor:0};
  }
  const totals=this.cache.prepare('SELECT kind,n,bytes FROM totals').all();
  if(totals.some(r=>r.n>MAX_ROWS))throw Error('row-limit');
  if(totals.reduce((a,r)=>a+r.bytes,0)>MAX_BYTES)throw Error('read-size-limit');
  this.put('progress',p);this.put('complete',null);
  return {phase:p.kind===KINDS.length?'validation-required':'building',readRows,reusedRows};
 });}
 validateAndSummarize(summarize){return this.transaction(guard=>{
  if(this.get('progress').kind<KINDS.length)return {phase:'building',complete:false};
  const sourceMaxSeq=this.source.prepare('SELECT COALESCE(MAX(seq),0) AS seq FROM events').get().seq,snapshotAt=Date.now();
  let compared=0;
  for(const kind of KINDS){
   const a=this.source.prepare('SELECT seq,id,at FROM events WHERE kind=? ORDER BY seq').iterate(kind);
   const b=this.cache.prepare('SELECT seq,id,at FROM rows WHERE kind=? ORDER BY seq').iterate(kind);
   try{while(true){guard();const x=a.next(),y=b.next();if(x.done&&y.done)break;
    if(x.done!==y.done||x.value.seq!==y.value.seq||x.value.id!==y.value.id||x.value.at!==y.value.at){
     this.put('progress',{kind:0,cursor:0});this.put('complete',null);return {phase:'source-changed',complete:false};
    }
    if(++compared>4*MAX_ROWS)throw Error('row-limit');
   }}finally{a.return?.();b.return?.();}
  }
  let rawBytes=0;const counts={};
  const storage={
   events:(kind)=>{
    if(!KINDS.includes(kind))throw Error('unsupported-kind');
    const db=this.cache;
    return (function*(){for(const r of db.prepare('SELECT rawBytes,data FROM rows WHERE kind=? ORDER BY seq').iterate(kind)){
     guard();counts[kind]=(counts[kind]||0)+1;rawBytes+=r.rawBytes;
     if(counts[kind]>MAX_ROWS)throw Error('row-limit');if(rawBytes>MAX_BYTES)throw Error('read-size-limit');
     yield JSON.parse(r.data);
    }})();
   },
   readJsonl:(kind,limit)=>{
    if(kind!=='research-events'||limit!==30)throw Error('unsupported-kind');
    return this.source.prepare('SELECT seq,id,at,length(CAST(data AS BLOB)) AS rawBytes,CASE WHEN length(CAST(data AS BLOB))<=262144 THEN data ELSE NULL END AS data FROM events WHERE kind=? ORDER BY seq DESC LIMIT 30').all(kind).reverse().map(r=>{
     guard();rawBytes+=r.rawBytes;if(rawBytes>MAX_BYTES)throw Error('read-size-limit');return this.decode(r,kind);
    });
   }
  };
  const result=summarize(storage,snapshotAt);guard();
  const complete={snapshotAt,sourceMaxSeq,counts,rawBytes};
  this.put('complete',complete);this.put('progress',{kind:0,cursor:0});
  return {phase:'complete',complete:true,...complete,result};
 });}
 close(){this.cache.close();this.source.close();}
}
