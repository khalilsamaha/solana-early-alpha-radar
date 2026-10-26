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
 const db=new DatabaseSync(database);db.exec('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT,id TEXT,at INTEGER,data TEXT);CREATE INDEX events_kind_seq ON events(kind,seq)');
 db.prepare('INSERT INTO events VALUES(?,?,?,?,?)').run(1,'alerts','private-id',1000,JSON.stringify({id:'private-mint:1000:a',candidate:{mint:'private-mint',evidence:'private detail'}}));db.close();
 const radar=path.resolve('scanner/src/core/radar.js');return {database,cache,storeSource:fs.readFileSync('statistics-lab/compact-store.mjs','utf8'),expected:{[radar]:createHash('sha256').update(fs.readFileSync(radar)).digest('hex')},radarUrl:pathToFileURL(radar).href,compactUrl:pathToFileURL(path.resolve('scanner/src/core/stats-memory.js')).href,toleranceMs:120000,budgetMs:120000};
}
test('isolated benchmark completes two rounds with no source writes or outcome exports',async t=>{
 const o=fixture(t),before=fs.readFileSync(o.database),r=await benchmark(o);
 assert.equal(r.state,'completed');assert.equal(r.diagnostic.rounds.length,2);
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
