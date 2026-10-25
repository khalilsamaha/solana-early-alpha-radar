import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {EventEmitter} from 'node:events';
import {DatabaseSync} from 'node:sqlite';
import {profile,sanitize} from './stats-profile.mjs';
const realRadar=path.resolve('scanner/src/core/radar.js');
function setup(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'stats-profile-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const database=path.join(dir,'data.sqlite'),db=new DatabaseSync(database);
 db.exec('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT,data TEXT);CREATE INDEX kind_seq ON events(kind,seq)');
 db.prepare('INSERT INTO events(kind,data) VALUES(?,?)').run('alerts',JSON.stringify({id:'test:1:1',legacy:false,candidate:{mint:'test'},engineVersion:'0.2.9'}));
 db.close();return {dir,database};}
const options=(database,radar=realRadar)=>({database,radarUrl:pathToFileURL(radar).href,toleranceMs:120000,expected:{[radar]:createHash('sha256').update(fs.readFileSync(radar)).digest('hex')}});
test('standalone reader completes real summaries but exports only bounded timings and preserves rows',async t=>{
 const {database}=setup(t),before=fs.readFileSync(database);const r=await profile(options(database));
 assert.equal(r.state,'completed');assert.equal(r.statisticsExported,false);assert.equal(r.diagnostic.kinds.alerts.rows,1);
 assert(r.diagnostic.rawBytes>0);assert(!JSON.stringify(r).includes('uniquePaperEntries'));assert(!JSON.stringify(r).includes('test:1'));
 assert.deepEqual(fs.readFileSync(database),before);
});
test('source mismatch is rejected before loading the statistics module',async t=>{
 const {database,dir}=setup(t),module=path.join(dir,'bad.mjs');fs.writeFileSync(module,'throw Error("private text");');
 const o=options(database,module);o.expected[module]='0'.repeat(64);const r=await profile(o);
 assert.equal(r.state,'stopped');assert.equal(r.error,'source-mismatch');assert(!JSON.stringify(r).includes('private text'));
});
test('oversized and malformed rows remain explicit failures without partial statistics',async t=>{
 const {database}=setup(t);let db=new DatabaseSync(database);db.prepare('UPDATE events SET data=?').run(JSON.stringify({id:'x',large:'x'.repeat(270000)}));db.close();
 const r=await profile(options(database));assert.equal(r.error,'row-size-limit');assert.equal(r.diagnostic.kinds.alerts.rows,1);
 db=new DatabaseSync(database);db.prepare('UPDATE events SET data=?').run('{broken');db.close();
 assert.equal((await profile(options(database))).error,'statistics-read-failed');
});
test('watchdog keeps the last safe progress and never accepts a late successful message',async()=>{
 class W extends EventEmitter{terminate(){this.emit('message',{ok:true,diagnostic:{phase:'complete'}});this.emit('exit',1);return Promise.resolve();}}
 const r=await profile({}, {timeoutMs:5,workerFactory:()=>{const w=new W();queueMicrotask(()=>w.emit('message',{diagnostic:{phase:'reading:alerts',rawBytes:10}}));return w;}});
 assert.equal(r.state,'stopped');assert.equal(r.error,'worker-timeout');
});
test('diagnostic sanitizer drops arbitrary fields, unknown phases and nonfinite counts',()=>{
 const r=sanitize({phase:'private',rawBytes:Infinity,secret:'token',kinds:{alerts:{rows:NaN,rawBytes:20,secret:'token'},other:{rows:1}},phases:[{phase:'reading:secret',elapsedMs:2}]});
 assert.equal(r.phase,'unknown');assert.equal(r.rawBytes,null);assert.equal(r.kinds.alerts.rows,null);
 assert(!JSON.stringify(r).includes('secret'));assert(!JSON.stringify(r).includes('token'));
});
