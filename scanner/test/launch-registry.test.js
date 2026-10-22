import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {Storage} from '../src/core/storage.js';
import {creationEvidence,LaunchRegistry,LAUNCH_LIMITS} from '../src/core/launch-registry.js';
import {startPumpPortal} from '../src/adapters/pumpportal.js';
const mint='A'.repeat(32),now=1800000000000;
const fixture=(extra={})=>({txType:'create',mint,creator:'B'.repeat(32),traderPublicKey:'C'.repeat(32),initialBuy:0,uri:'ipfs://example',...extra});
const setup=(limits=LAUNCH_LIMITS)=>{const db=new DatabaseSync(':memory:');db.exec('CREATE TABLE kv(key TEXT PRIMARY KEY,data TEXT);CREATE TABLE candidates(mint TEXT PRIMARY KEY,data TEXT)');return {db,registry:new LaunchRegistry(db,limits)};};

test('launch evidence preserves zero, unknown roles and receipt clocks; drops arbitrary payload',()=>{
  const e=creationEvidence(fixture({signature:'D'.repeat(88),solAmount:'0.000000000000000001',secret:'never-store',slot:0,decimals:300}),now);
  assert.equal(e.fields.initialBuyReported,'0');assert.equal(e.fields.solAmountReported,'0.000000000000000001');
  assert.equal(e.fields.slotReported,0);assert.equal(e.fields.decimalsReported,null);
  assert.notEqual(e.fields.creatorReported,e.fields.traderReported);assert.equal(e.chainTime,null);assert.equal(e.availableAt,now);
  assert.equal(e.fields.metadataUriSha256.length,64);assert.ok(!JSON.stringify(e).includes('never-store'));assert.ok(!JSON.stringify(e).includes('ipfs://'));
  assert.equal(creationEvidence(fixture({txType:'migration'}),now),null);
  assert.equal(creationEvidence(fixture({mint:'name'}),now),null);
  assert.equal(creationEvidence(fixture({initialBuy:NaN}),now).fields.initialBuyReported,null);
});
test('first creation survives candidate deletion, duplicate replay, migration and reopening',()=>{
  const {db,registry}=setup();const e=creationEvidence(fixture(),now);
  assert.equal(registry.record(e,now),'inserted');
  db.prepare('INSERT INTO candidates VALUES(?,?)').run(mint,'{}');db.exec('DELETE FROM candidates');
  assert.equal(registry.record(creationEvidence(fixture({creator:'E'.repeat(32)}),now+1),now+1),'duplicate');
  assert.equal(JSON.parse(db.prepare('SELECT data FROM launch_registry').get().data).fields.creatorReported,'B'.repeat(32));
  assert.equal(new LaunchRegistry(db).health().retained,1);
  assert.equal(registry.record(null,now),'rejected');db.close();
});
test('hard capacity never evicts younger registry evidence and bounded retention frees capacity',()=>{
  const {db,registry}=setup({...LAUNCH_LIMITS,maxRows:1,retentionDays:1,pruneBatch:1});
  assert.equal(registry.record(creationEvidence(fixture(),now),now),'inserted');
  const newer=creationEvidence(fixture({mint:'F'.repeat(32)}),now+1);
  assert.equal(registry.record(newer,now+1),'capacity-dropped');assert.equal(registry.health().sinceRestart.capacityDropped,1);
  const later=now+86400001;assert.equal(registry.record(creationEvidence(fixture({mint:'F'.repeat(32)}),later),later),'inserted');
  assert.equal(registry.health().retained,1);assert.equal(registry.health().sinceRestart.pruned,1);db.close();
});
test('future, oversized and expired records do not enter evidence',()=>{
  const {db,registry}=setup();const e=creationEvidence(fixture(),now);
  assert.equal(registry.record(e,now-1),'rejected');assert.equal(registry.record({...e,extra:'x'.repeat(5000)},now),'rejected');
  assert.equal(registry.record(e,now+31*86400000),'rejected');assert.equal(registry.health().retained,0);db.close();
});
test('adapter captures creations before admission, keeps free subscriptions and continues after registry failure',()=>{
  const Original=globalThis.WebSocket;let socket;const candidates=[],creations=[],messages=[];
  class Socket{constructor(){this.handlers={};this.sent=[];socket=this;}addEventListener(k,fn){this.handlers[k]=fn;}send(s){this.sent.push(JSON.parse(s));}close(){}}
  globalThis.WebSocket=Socket;let stop;
  try{
    stop=startPumpPortal('test',c=>candidates.push(c),m=>messages.push(m),null,e=>{creations.push(e);throw Error('storage failure');});
    socket.handlers.open();assert.deepEqual(socket.sent.map(s=>s.method),['subscribeNewToken','subscribeMigration']);
    socket.handlers.message({data:JSON.stringify(fixture())});
    socket.handlers.message({data:JSON.stringify(fixture({txType:'migration'}))});
    assert.equal(creations.length,1);assert.equal(candidates.length,2);assert.ok(messages.some(s=>s.includes('write failed')));
    socket.handlers.message({data:'x'.repeat(65537)});assert.equal(candidates.length,2);
  }finally{stop?.();globalThis.WebSocket=Original;}
});


test('whole scanner backup retains registry; failed SQL rolls back capture accounting',async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'launch-backup-'));const storage=new Storage(dir);
  try{
    const at=Date.now();storage.recordLaunch(creationEvidence(fixture(),at));
    const copy=path.join(dir,'snapshot.sqlite');await storage.backup(copy);
    const restored=new DatabaseSync(copy,{readOnly:true});
    assert.equal(restored.prepare('SELECT count(*) AS n FROM launch_registry').get().n,1);restored.close();
    storage.db.exec("CREATE TRIGGER reject_launch BEFORE INSERT ON launch_registry BEGIN SELECT RAISE(ABORT,'test failure'); END");
    assert.throws(()=>storage.recordLaunch(creationEvidence(fixture({mint:'G'.repeat(32)}),Date.now())));
    assert.equal(storage.launchRegistry.health().retained,1);assert.equal(storage.launchRegistry.health().sinceRestart.errors,1);
    assert.equal(storage.db.prepare('SELECT count(*) AS n FROM launch_registry').get().n,1);
  }finally{storage.close();fs.rmSync(dir,{recursive:true,force:true});}
});
