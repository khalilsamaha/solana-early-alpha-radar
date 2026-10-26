import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {CompactStore,KINDS} from './compact-store.mjs';
import {compactSummaryRow} from '../scanner/src/core/stats-memory.js';
import {Radar} from '../scanner/src/core/radar.js';
function fixture(t){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'compact-stats-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const source=path.join(dir,'source.sqlite'),cache=path.join(dir,'cache.sqlite');fs.writeFileSync(cache,'');
 const db=new DatabaseSync(source);db.exec('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,id TEXT NOT NULL,at INTEGER NOT NULL,data TEXT NOT NULL);CREATE INDEX events_kind_seq ON events(kind,seq)');
 let n=0;const add=(kind,data,at=1000,id=`event-${++n}`)=>db.prepare('INSERT INTO events(kind,id,at,data) VALUES(?,?,?,?)').run(kind,id,at,typeof data==='string'?data:JSON.stringify(data));
 return {source,cache,db,add,open:options=>new CompactStore({source,cache,compact:compactSummaryRow,...options})};
}
function build(s){let reads=0,reused=0;for(let i=0;i<1000;i++){const r=s.step();reads+=r.readRows;reused+=r.reusedRows;if(r.phase==='validation-required')return {reads,reused};}throw Error('unfinished');}
const summarize=(storage,now)=>Radar.prototype.getStats.call({storage,config:{horizonToleranceMs:120000},candidates:new Map(),status:[],getHealth:()=>null},now);
function original(db){return {events:kind=>db.prepare('SELECT data FROM events WHERE kind=? ORDER BY seq').all(kind).map(r=>JSON.parse(r.data)),readJsonl:(kind,n)=>db.prepare('SELECT data FROM events WHERE kind=? ORDER BY seq DESC LIMIT ?').all(kind,n).reverse().map(r=>JSON.parse(r.data))};}
test('bootstrap and warm refresh exactly match summaries while warm refresh reads no old payloads',t=>{
 const f=fixture(t);
 for(let i=0;i<160;i++){
  f.add('alerts',{id:`m${i}:1000:first`,candidate:{mint:`m${i}`,history:'x'.repeat(4000)},engineVersion:'0.2.9'});
  f.add('outcomes',{mint:`m${i}`,alertAt:1000,horizon:'60m',version:'price-v2',status:i%3?'observed':'missing',multiple:i%2?1.25:0,maxMultiple:2,coverage:i%4?'sampled':'gapped'});
  f.add('research-entries',{id:`r${i}`,at:1000,cohort:'early-activity',version:'research-0.2.9'});
  f.add('research-outcomes',{entryId:`r${i}`,horizon:'1m',status:'observed',returnPct:-5,tokenFollowup:{status:'observed',returnPct:0,basis:'alternate-pool'}});
 }
 f.add('research-events',{at:1000,stage:'observing'});const before=fs.readFileSync(f.source),s=f.open();
 assert.equal(build(s).reads,640);let r=s.validateAndSummarize(summarize);assert(r.complete);assert.deepEqual(r.result,summarize(original(f.db),r.snapshotAt));
 assert.deepEqual(build(s),{reads:0,reused:640});r=s.validateAndSummarize(summarize);assert.deepEqual(r.result,summarize(original(f.db),r.snapshotAt));
 assert.deepEqual(fs.readFileSync(f.source),before);s.close();f.db.close();
});
test('resumes committed batches after restart and new records are captured',t=>{
 const f=fixture(t);for(let i=0;i<260;i++)f.add('alerts',{id:`m:${i}:a`,candidate:{mint:'m'}});
 let s=f.open();assert.equal(s.step().readRows,128);s.close();s=f.open();assert.equal(build(s).reads,132);
 assert(s.validateAndSummarize(summarize).complete);f.add('alerts',{id:'new:10:a',candidate:{mint:'new'}});
 assert.deepEqual(build(s),{reads:1,reused:260});assert(s.validateAndSummarize(summarize).complete);s.close();f.db.close();
});
test('retention, empty kinds and reused sequence numbers reconcile before publication',t=>{
 const f=fixture(t);f.add('research-entries',{id:'old',at:1000});f.add('research-outcomes',{entryId:'old',horizon:'1m',status:'missing'});
 const s=f.open();build(s);assert(s.validateAndSummarize(summarize).complete);
 f.db.exec('DELETE FROM events');f.add('research-entries',{id:'new',at:2000},2000,'new-event');
 build(s);const r=s.validateAndSummarize(summarize);assert(r.complete);assert.deepEqual(r.result,summarize(original(f.db),r.snapshotAt));
 assert.equal(s.cache.prepare('SELECT count(*) AS n FROM rows').get().n,1);s.close();f.db.close();
});
test('arrival or deletion after batching refuses publication and restarts reconciliation',t=>{
 const f=fixture(t);f.add('alerts',{id:'m:1:a',candidate:{mint:'m'}});const s=f.open();build(s);
 f.add('alerts',{id:'n:2:a',candidate:{mint:'n'}});let called=false;
 assert.equal(s.validateAndSummarize(()=>{called=true;}).phase,'source-changed');assert.equal(called,false);
 build(s);assert(s.validateAndSummarize(summarize).complete);build(s);f.db.exec('DELETE FROM events');
 assert.equal(s.validateAndSummarize(summarize).phase,'source-changed');build(s);assert(s.validateAndSummarize(summarize).complete);s.close();f.db.close();
});
test('malformed and oversized source rows roll back the entire current batch and its cursor',t=>{
 for(const raw of ['{broken',JSON.stringify({large:'x'.repeat(270000)})]){
  const f=fixture(t);f.add('alerts',{id:'m:1:a',candidate:{mint:'m'}});f.add('alerts',raw);const s=f.open();
  assert.throws(()=>s.step());assert.equal(s.cache.prepare('SELECT count(*) AS n FROM rows').get().n,0);assert.deepEqual(s.get('progress'),{kind:0,cursor:0});s.close();f.db.close();
 }
});
test('timeout and summary failure never mark a completed refresh',t=>{
 const f=fixture(t);f.add('alerts',{id:'m:1:a',candidate:{mint:'m'}});let tick=0;
 let s=f.open({now:()=>tick+=9000});assert.throws(()=>s.step(),/read-timeout/);assert.equal(s.get('complete'),null);s.close();
 s=f.open();build(s);assert.throws(()=>s.validateAndSummarize(()=>{throw Error('summary failed');}));assert.equal(s.get('complete'),null);s.close();f.db.close();
});
test('source replacement, source/cache alias and incompatible versions are rejected',t=>{
 const f=fixture(t);f.db.close();assert.throws(()=>new CompactStore({source:f.source,cache:f.source,compact:compactSummaryRow}),/cache-source-alias/);
 const s=f.open();s.close();fs.renameSync(f.source,f.source+'.old');fs.copyFileSync(f.source+'.old',f.source);assert.throws(()=>f.open(),/source-replaced/);
 const f2=fixture(t);f2.db.close();const s2=f2.open();s2.put('version','future');s2.close();assert.throws(()=>f2.open(),/cache-version/);
});
test('source-code provenance changes cannot reuse an old derived cache',t=>{
 const f=fixture(t);let s=f.open({provenance:'reviewed-reader-a'});s.close();
 assert.throws(()=>f.open({provenance:'reviewed-reader-b'}),/cache-version/);f.db.close();
});
test('derived byte counters track replacement and pruning without scanning every cached payload',t=>{
 const f=fixture(t);f.add('research-entries',{id:'first',at:1000,unused:'large'});const s=f.open();build(s);s.validateAndSummarize(summarize);
 f.db.exec('DELETE FROM events');f.add('research-entries',{id:'other',at:2000},2000,'replacement');build(s);s.validateAndSummarize(summarize);
 const total=s.cache.prepare('SELECT n,bytes FROM totals WHERE kind=?').get('research-entries');
 const actual=s.cache.prepare('SELECT count(*) AS n,sum(rawBytes) AS bytes FROM rows WHERE kind=?').get('research-entries');assert.deepEqual(total,actual);
 f.db.exec('DELETE FROM events');build(s);assert.deepEqual({...s.cache.prepare('SELECT n,bytes FROM totals WHERE kind=?').get('research-entries')},{n:0,bytes:0});s.close();f.db.close();
});
