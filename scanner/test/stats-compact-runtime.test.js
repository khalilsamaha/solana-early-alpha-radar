import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {EventEmitter} from 'node:events';
import {setTimeout as delay} from 'node:timers/promises';
import {DatabaseSync} from 'node:sqlite';
import {StatsService} from '../src/core/stats-service.js';
import {CompactStore,CREATE_IDENTITY_INDEX} from '../src/core/stats-compact-store.js';
import {compactSummaryRow} from '../src/core/stats-memory.js';
import {acquireCompactLease,cacheProvenance} from '../src/core/stats-compact-runtime.js';
import {Storage} from '../src/core/storage.js';
function fixture(t,index=true){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'compact-runtime-'));const s=new Storage(dir);if(index)s.db.exec(CREATE_IDENTITY_INDEX);t.after(()=>{s.close();fs.rmSync(dir,{recursive:true,force:true});});return {s,database:path.join(dir,'radar.sqlite')};}
function service(t,database,o={}){const x=new StatsService(database,120000,{autoStart:false,...o});t.after(()=>x.close());return x;}
class Fake extends EventEmitter{terminate(){this.emit('exit',1);return Promise.resolve();}complete(at=Date.now()){this.emit('message',{ok:true,data:{alerts:1},snapshotAt:at,sourceMaxSeq:1,computeMs:1});this.emit('exit',0);}}
test('background refresh runs without stats requests and graceful restart reuses committed cache',async t=>{
 const {s,database}=fixture(t);s.append('alerts',{id:'one',at:1,candidate:{mint:'a'}});
 const x=service(t,database,{autoStart:true,tickMs:10});
 for(let i=0;i<500&&!x.successes;i++)await delay(10);
 assert.equal(x.successes,1);assert.equal((await x.get()).alerts,1);await x.close();
 const y=service(t,database);await y.get();assert.ok(y.cache.reconciliation.reusedRows>=1);assert.equal(y.cache.reconciliation.readRows,0);
});
test('reviewed benchmark provenance is adopted without discarding rows or private cache identity',async t=>{
 const {s,database}=fixture(t);s.append('alerts',{id:'one',at:1,candidate:{mint:'a'}});
 const lease=acquireCompactLease(database),before=fs.statSync(lease.cache),p=cacheProvenance();
 const store=new CompactStore({source:database,cache:lease.cache,compact:compactSummaryRow,provenance:p.compatibleProvenance[0]});
 while(store.step().phase!=='validation-required'){}
 store.validateAndSummarize(()=>({}));store.put('test-preserved',true);store.close();lease.release();
 const x=service(t,database);await x.get();assert.equal(x.cache.reconciliation.readRows,0);assert.equal(x.cache.reconciliation.reusedRows,1);
 const db=new DatabaseSync(lease.cache,{readOnly:true});try{assert.equal(JSON.parse(db.prepare("SELECT value FROM meta WHERE key='test-preserved'").get().value),true);assert.equal(JSON.parse(db.prepare("SELECT value FROM meta WHERE key='previousProvenance'").get().value),p.compatibleProvenance[0]);}finally{db.close();}
 assert.equal(fs.statSync(lease.cache).ino,before.ino);
});
test('unknown cache provenance is refused and retained',async t=>{
 const {database}=fixture(t),lease=acquireCompactLease(database);
 const store=new CompactStore({source:database,cache:lease.cache,compact:compactSummaryRow,provenance:'unreviewed'});store.close();lease.release();
 const x=service(t,database);await assert.rejects(x.get(),{statusCode:503});assert.equal(x.error,'cache-version');assert.ok(fs.existsSync(lease.cache));
});
test('missing source index fails without a slow fallback or published partial summary',async t=>{
 const {database}=fixture(t,false),x=service(t,database);await assert.rejects(x.get(),{statusCode:503});assert.equal(x.error,'source-index-required');assert.equal(x.cache,null);
});
test('runtime SQLite lease prevents overlapping services and recovers after process death',t=>{
 const {database}=fixture(t);const lease=acquireCompactLease(database);
 assert.throws(()=>acquireCompactLease(database),/cache-busy/);lease.release();
 const moduleUrl=new URL('../src/core/stats-compact-runtime.js',import.meta.url).href;
 execFileSync(process.execPath,['--input-type=module','-e',`import {acquireCompactLease} from ${JSON.stringify(moduleUrl)};acquireCompactLease(process.argv[1]);process.exit(0);`,database],{timeout:5000});
 const next=acquireCompactLease(database);next.release();assert.ok(!fs.existsSync(path.join(path.dirname(next.cache),'active.lock')));
});
test('active legacy benchmark lock and unsafe cache paths are refused',t=>{
 const {database}=fixture(t),lease=acquireCompactLease(database);lease.release();const lock=path.join(path.dirname(lease.cache),'active.lock');
 fs.writeFileSync(lock,String(process.pid),{mode:0o600});assert.throws(()=>acquireCompactLease(database),/cache-busy/);fs.unlinkSync(lock);
 fs.chmodSync(lease.cache,0o644);assert.throws(()=>acquireCompactLease(database),/cache-path/);assert.ok(!fs.existsSync(lock));
});
test('cold HTTP wait is bounded while the same refresh continues and later publishes',async t=>{
 const {database}=fixture(t);let w;const x=service(t,database,{requestWaitMs:20,workerFactory:()=>w=new Fake()});
 const alive=setInterval(()=>{},10);
 try{await assert.rejects(x.get(),{statusCode:503});assert.equal(x.attempts,1);assert.ok(x.pending);w.complete();assert.equal((await x.get()).alerts,1);}finally{clearInterval(alive);}
});
test('progress keeps idle watchdog alive but cannot extend the total job deadline',async t=>{
 const {database}=fixture(t);let w;const x=service(t,database,{timeoutMs:40,jobTimeoutMs:90,workerFactory:()=>w=new Fake()});
 const p=x.get(),heartbeat=setInterval(()=>w.emit('message',{progress:{phase:'reconciling',elapsedMs:5}}),10);
 try{await assert.rejects(p,{statusCode:503});assert.equal(x.error,'worker-timeout');assert.equal(x.cache,null);}finally{clearInterval(heartbeat);}
});
test('a late success during watchdog termination cannot replace cache',async t=>{
 const {database}=fixture(t);class Late extends Fake{terminate(){this.complete();return Promise.resolve();}}
 const x=service(t,database,{timeoutMs:20,workerFactory:()=>new Late()});const alive=setInterval(()=>{},10);
 try{await assert.rejects(x.get(),{statusCode:503});assert.equal(x.error,'worker-timeout');assert.equal(x.successes,0);}finally{clearInterval(alive);}
});
test('future or expired worker snapshots are not published as current',async t=>{
 const {database}=fixture(t);
 for(const offset of [1,-120001]){let w;const x=service(t,database,{clock:()=>1000000,workerFactory:()=>w=new Fake()});const p=x.get();w.complete(1000000+offset);await assert.rejects(p,{statusCode:503});assert.equal(x.error,'worker-result-invalid');}
});
test('runtime store exactly matches the host validated candidate',()=>{
 const manifest=JSON.parse(fs.readFileSync(new URL('../src/core/stats-compact-manifest.json',import.meta.url),'utf8'));
 assert.equal(createHash('sha256').update(fs.readFileSync(new URL('../src/core/stats-compact-store.js',import.meta.url))).digest('hex'),manifest.storeSha256);
});

test('source identity failures invalidate published statistics while preserving the private cache',async t=>{
 const {database}=fixture(t);let now=100000,w;
 const x=service(t,database,{clock:()=>now,workerFactory:()=>w=new Fake()});
 const first=x.get();w.complete(now);await first;now+=31000;
 await x.get();w.emit('message',{ok:false,error:'source-replaced'});w.emit('exit',0);
 assert.equal(x.cache,null);await assert.rejects(x.get(),{statusCode:503});
 assert.ok(fs.existsSync(path.join(path.dirname(database),'statistics-cache-lab-1','compact.sqlite')));
});
