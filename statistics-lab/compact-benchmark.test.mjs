import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {DatabaseSync} from 'node:sqlite';
import {createHash} from 'node:crypto';
import {EventEmitter} from 'node:events';
import {benchmark} from './compact-benchmark.mjs';
function fixture(t){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'compact-bench-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const database=path.join(dir,'source.sqlite'),cache=path.join(dir,'cache.sqlite');fs.writeFileSync(cache,'');
 const db=new DatabaseSync(database);db.exec('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,id TEXT NOT NULL,at INTEGER NOT NULL,data TEXT NOT NULL,UNIQUE(kind,id));CREATE INDEX events_kind_seq ON events(kind,seq);CREATE INDEX events_at ON events(kind,at)');
 db.prepare('INSERT INTO events VALUES(?,?,?,?,?)').run(1,'alerts','private-id',1000,JSON.stringify({id:'private-mint:1000:a',candidate:{mint:'private-mint',evidence:'private detail'}}));db.close();
 const radar=path.resolve('scanner/src/core/radar.js');return {database,cache,storeSource:fs.readFileSync('statistics-lab/compact-store.mjs','utf8'),expected:{[radar]:createHash('sha256').update(fs.readFileSync(radar)).digest('hex')},radarUrl:pathToFileURL(radar).href,compactUrl:pathToFileURL(path.resolve('scanner/src/core/stats-memory.js')).href,toleranceMs:120000,budgetMs:120000};
}
test('isolated benchmark completes two rounds with no source writes or outcome exports',async t=>{
 const o=fixture(t),before=fs.readFileSync(o.database),r=await benchmark(o);
 assert.equal(r.state,'completed');assert.equal(r.diagnostic.rounds.length,2);
 assert.equal(r.diagnosticVersion,'query-timing-3');
 for(const round of r.diagnostic.rounds){assert(round.inventoryMs>=0);assert(round.summaryMs>=0);assert(round.validationAndSummaryMs>=round.inventoryMs+round.summaryMs);}
 assert.equal(r.diagnostic.rounds[0].readRows,1);assert.equal(r.diagnostic.rounds[1].readRows,0);assert.equal(r.diagnostic.rounds[1].reusedRows,1);
 assert.deepEqual(fs.readFileSync(o.database),before);assert(!JSON.stringify(r).includes('private'));assert(!JSON.stringify(r).includes('paperSummary'));
});
test('budget pause resumes safely and source hash mismatch never starts a cache',async t=>{
 const o=fixture(t);assert.equal((await benchmark({...o,budgetMs:0})).state,'paused');assert.equal((await benchmark(o)).state,'completed');
 const f=fixture(t);f.expected[Object.keys(f.expected)[0]]='0'.repeat(64);const r=await benchmark(f);assert.equal(r.error,'source-mismatch');assert.equal(fs.statSync(f.cache).size,0);
});
test('worker timeout rejects late completion and preserves explicit failure',async()=>{
 class W extends EventEmitter{terminate(){this.emit('message',{terminal:{state:'completed'}});this.emit('exit',1);return Promise.resolve();}}
 const r=await benchmark({}, {watchdogMs:5,workerFactory:()=>new W()});assert.equal(r.state,'stopped');assert.equal(r.error,'worker-timeout');
});
test('worker memory failure keeps its specific category on nonzero exit',async()=>{
 const r=await benchmark({}, {workerFactory:()=>{const w=new EventEmitter();queueMicrotask(()=>{w.emit('error',{code:'ERR_WORKER_OUT_OF_MEMORY'});w.emit('exit',1);});return w;}});
 assert.equal(r.error,'worker-memory-limit');
});
test('summary failure retains its phase and a resumable cache without exporting evidence',async t=>{
 const o=fixture(t),file=path.join(path.dirname(o.cache),'failing-radar.mjs');
 fs.writeFileSync(file,"export class Radar { getStats(){throw Error('read-timeout');} }");
 const r=await benchmark({...o,radarUrl:pathToFileURL(file).href});
 assert.equal(r.error,'read-timeout');assert.equal(r.diagnostic.failedPhase,'summary-calculation');
 assert.equal(r.diagnostic.rounds.length,0);assert(r.diagnostic.timings.inventoryMs>0);
 assert(!JSON.stringify(r).includes('private'));
 const resumed=await benchmark(o);assert.equal(resumed.state,'completed');assert.equal(resumed.diagnostic.rounds[0].readRows,0);
 assert.equal(resumed.diagnostic.rounds[0].reusedRows,0); // inventory already complete before failed summary
});
test('inventory failure and watchdog retain the last active phase',async t=>{
 const o=fixture(t);
 const stub="export class CompactStore { get(){return {kind:4,cursor:0}} step(){return {phase:'validation-required',readRows:0,reusedRows:0}} validateAndSummarize(){throw Error('read-timeout')} close(){} }";
 const r=await benchmark({...o,storeSource:stub});assert.equal(r.diagnostic.failedPhase,'inventory-validation');assert(r.diagnostic.timings.inventoryMs>=0);
 class W extends EventEmitter{terminate(){this.emit('exit',1);return Promise.resolve();}}
 const timeout=await benchmark({}, {watchdogMs:5,workerFactory:()=>{const w=new W();queueMicrotask(()=>w.emit('message',{progress:{activePhase:'summary-calculation',rounds:[]}}));return w;}});
 assert.equal(timeout.error,'worker-timeout');assert.equal(timeout.diagnostic.activePhase,'summary-calculation');
});

test('query-level reports include bounded completed scans and parent elapsed time',async t=>{
 const r=await benchmark(fixture(t));assert.equal(r.state,'completed');
 assert(r.parentElapsedMs>=r.diagnostic.elapsedMs);assert(r.lastProgressAgeMs>=0);
 for(const round of r.diagnostic.rounds){
  assert.equal(round.inventoryQueries.filter(q=>q.operation==='scan-additions').length,4);
  assert.equal(round.inventoryQueries.filter(q=>q.operation==='scan-deletions').length,4);
  assert(round.inventoryQueries.length<=16);assert(round.inventoryQueries.every(q=>q.state==='complete'&&q.elapsedMs>=0));
 }
});
test('watchdog reports time since last progress separately from worker elapsed time',async()=>{
 class W extends EventEmitter{terminate(){this.emit('exit',1);return Promise.resolve();}}
 const r=await benchmark({}, {watchdogMs:30,workerFactory:()=>{const w=new W();queueMicrotask(()=>w.emit('message',{progress:{elapsedMs:1,activePhase:'inventory-validation',inventoryQuery:{operation:'scan-additions',kind:'alerts',state:'running',elapsedMs:0}}}));return w;}});
 assert.equal(r.error,'worker-timeout');assert(r.parentElapsedMs>=20);assert(r.lastProgressAgeMs>=20);
 assert.equal(r.diagnostic.elapsedMs,1);assert.equal(r.diagnostic.inventoryQuery.operation,'scan-additions');
});

test('query preparation failure identifies the operation without leaking SQLite errors',async t=>{
 const o=fixture(t);const r1=await benchmark(o);assert.equal(r1.state,'completed');
 const cache=new DatabaseSync(o.cache);cache.prepare('UPDATE meta SET value=? WHERE key=?').run(JSON.stringify({kind:4,cursor:0}),'progress');cache.close();
 const db=new DatabaseSync(o.database);db.exec('DROP INDEX events_kind_seq');db.close();
 const r=await benchmark(o);assert.equal(r.state,'stopped');assert.equal(r.error,'benchmark-failed');
 assert.equal(r.diagnostic.failedPhase,'inventory-validation');assert.equal(r.diagnostic.inventoryQuery.operation,'prepare-additions');assert.equal(r.diagnostic.inventoryQuery.state,'running');
 assert(!JSON.stringify(r).includes('no such index'));assert(!JSON.stringify(r).includes('private'));
});
test('reviewed predecessor provenance is rejected with an unrelated scanner manifest',async t=>{
 const o=fixture(t);assert.equal((await benchmark(o)).state,'completed');
 const cache=new DatabaseSync(o.cache);cache.prepare('UPDATE meta SET value=? WHERE key=?').run(JSON.stringify('c794dc1883cab815e52974a4a9eef0c02b53f4bc47348b72d8a16a8cabd39a02'),'provenance');cache.close();
 assert.equal((await benchmark(o)).error,'cache-version');
});
