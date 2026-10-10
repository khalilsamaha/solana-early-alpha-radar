import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {Storage} from '../src/core/storage.js';
import {Radar} from '../src/core/radar.js';
import {readConfig} from '../src/config.js';
function setup(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'batch-store-'));const s=new Storage(dir);t.after(()=>{s.close();fs.rmSync(dir,{recursive:true,force:true});});return s;}
test('unchanged state and candidate payloads do not rewrite SQLite rows',t=>{
 const s=setup(t);s.setState({value:1},'test');s.saveCandidate({mint:'a',score:5});
 s.setState({value:1},'test');s.saveCandidate({mint:'a',score:5});
 assert.equal(s.writeStats().stateUnchanged,1);assert.equal(s.writeStats().candidateUnchanged,1);
 s.setState({value:2},'test');s.saveCandidate({mint:'a',score:6});
 assert.equal(s.getState('test').value,2);assert.equal(s.loadCandidates().a.score,6);
});
test('rollback followed by retry cannot be skipped by a stale in-memory deduplication cache',t=>{
 const s=setup(t);s.setState({value:1},'test');
 assert.throws(()=>s.transaction(()=>{s.setState({value:2},'test');throw Error('rollback');}));
 assert.equal(s.getState('test').value,1);s.setState({value:2},'test');assert.equal(s.getState('test').value,2);
});
test('one completed market batch uses one commit after its network response arrives',async t=>{
 const s=setup(t);let fetched=false;
 const r=new Radar({...readConfig({}),notificationsEnabled:false},s,{getTokenPairs:async rows=>{
   assert.equal(Boolean(s.inTransaction),false);fetched=true;
   return new Map(rows.map(c=>[c.mint,{observedAt:Date.now(),market:{mint:c.mint,pairAddress:c.mint,priceUsd:1}}]));
 }});
 for(let n=0;n<30;n++)r.candidates.set('token'+n,{mint:'token'+n,firstSeenAt:Date.now()});
 const before=s.writeStats().transactions;await r.enrichBatch();
 assert.ok(fetched);assert.equal(s.writeStats().transactions-before,1);
 assert.equal(Object.keys(s.loadCandidates()).length,30);
});
test('a failed batch rolls back candidate writes and outcome events together',async t=>{
 const s=setup(t),r=new Radar(readConfig({}),s,{getTokenPairs:async()=>new Map()});
 r.candidates.set('a',{mint:'a'});r.candidates.set('b',{mint:'b'});
 r.applyObservation=(mint)=>{s.saveCandidate({mint});s.append('research-outcomes',{id:mint});if(mint==='b')throw Error('disk error simulation');};
 await assert.rejects(r.enrichBatch([...r.candidates.values()]),/disk error simulation/);
 assert.equal(Object.keys(s.loadCandidates()).length,0);assert.equal(s.readJsonl('research-outcomes').length,0);
 assert.equal(r.inFlight.size,0);
});
