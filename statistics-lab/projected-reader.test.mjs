import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {projectedStatement,projectionSql} from './projected-reader.mjs';
import {compactSummaryRow} from '../scanner/src/core/stats-memory.js';
import {Radar} from '../scanner/src/core/radar.js';
const kinds=['alerts','outcomes','research-entries','research-outcomes'];
function database(t){const db=new DatabaseSync(':memory:');db.exec('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT,data TEXT);CREATE INDEX events_kind_seq ON events(kind,seq)');t.after(()=>db.close());return db;}
function compare(db,kind,raw){
 db.exec('DELETE FROM events');db.prepare('INSERT INTO events(kind,data) VALUES(?,?)').run(kind,raw);
 const row=projectedStatement(db,kind).get(kind);assert.equal(row.rawBytes,Buffer.byteLength(raw));
 assert.deepEqual(compactSummaryRow(kind,JSON.parse(row.data)),compactSummaryRow(kind,JSON.parse(raw)));
 return row;
}
test('projection preserves missing, null, boolean, zero, Unicode, numeric precision and nested truthiness',t=>{
 const db=database(t);
 const values=[null,false,true,0,-0,'','x',[],{},1.0000000000000002,1.2345678901234567,9007199254740991,1e-200,{mint:'币🧪',version:'v',disposition:null,state:false,returnPct:0,basis:'original-pool'}];
 for(const v of values)for(const kind of kinds){compare(db,kind,JSON.stringify({id:'a:1:x',legacy:v,engineVersion:v,candidate:v,qualification:v,version:v,mint:v,alertAt:v,horizon:v,status:v,coverage:v,multiple:v,maxMultiple:v,score:v,entryMarketCap:v,at:v,cohort:v,entryId:v,returnPct:v,reasonCode:v,tokenFollowup:v,ignored:{history:'x'.repeat(1000)}}));}
 for(const kind of kinds){compare(db,kind,'{}');compare(db,kind,'[]');compare(db,kind,'42');compare(db,kind,'"text"');}
});
test('duplicate selected keys preserve last-key-wins including later null nested objects',t=>{
 const db=database(t);
 compare(db,'alerts','{"id":"x:1:y","id":"x:2:y","candidate":{"mint":"first"},"candidate":null}');
 compare(db,'alerts','{"id":"x:1:y","candidate":{"mint":"first","mint":"last"},"qualification":{"state":"x","state":"y"}}');
 compare(db,'outcomes','{"multiple":1.0000000000000002,"multiple":1.2345678901234567}');
 compare(db,'research-outcomes','{"tokenFollowup":{"returnPct":1,"returnPct":2}}');
});
test('projection excludes bulky evidence and preserves original byte accounting',t=>{
 const db=database(t);const raw=JSON.stringify({id:'x:1:y',candidate:{mint:'m',history:'x'.repeat(100000)},qualification:{version:'qualification-1',metrics:{ignored:'x'.repeat(10000)}},evidence:'x'.repeat(10000)});
 const r=compare(db,'alerts',raw);assert(Buffer.byteLength(r.data)<200);assert(r.rawBytes>120000);
 assert(!r.data.includes('history'));assert(!r.data.includes('metrics'));
});
test('malformed JSON, JSON5 and oversized rows cannot become apparently valid summaries',t=>{
 const db=database(t);
 for(const raw of ['{bad','{"id":1,}',JSON.stringify({id:'x',huge:'x'.repeat(262145)})]){
  db.exec('DELETE FROM events');db.prepare('INSERT INTO events(kind,data) VALUES(?,?)').run('alerts',raw);
  assert.equal(projectedStatement(db,'alerts').get('alerts').data,null);
 }
 assert.throws(()=>projectionSql('snapshots'));
});
test('all statistics equal the current reader across versions, gaps, missing evidence and alternate pools',t=>{
 const db=database(t),at=1700000000000;
 const add=(kind,row)=>db.prepare('INSERT INTO events(kind,data) VALUES(?,?)').run(kind,JSON.stringify(row));
 for(let i=0;i<40;i++){
  const mint=`m${i}`,id=`r${i}`;
  add('alerts',{id:`${mint}:${at}:first`,candidate:{mint,history:['private']},engineVersion:['0.2.4','0.2.5','0.2.6','0.2.7','0.2.8','0.2.9'][i%6],legacy:i===0,qualification:{version:'qualification-1',disposition:i%2?'retain':'defer',state:'ready'}});
  add('research-entries',{id,at,cohort:i%2?'baseline':'early-activity',version:i%3?'research-0.2.9':'old',evidence:['private']});
  for(const h of ['5m','15m','60m'])if(i%7)add('outcomes',{version:'price-v2',mint,alertAt:at,horizon:h,status:i%4?'observed':'missing',multiple:i%3?1.2345678901234567:0,maxMultiple:2,coverage:i%5?'sampled':'gapped',score:75,entryMarketCap:100000});
  for(const h of ['30s','1m','2m','5m'])if(i%7)add('research-outcomes',{entryId:id,horizon:h,status:i%4?'observed':'missing',returnPct:i%2?25:-80,coverage:i%5?'sampled':'gapped',reasonCode:'different-pool',tokenFollowup:i%3?{status:'observed',returnPct:0,basis:'alternate-pool',coverage:'sampled'}:null,evidenceHistory:['private']});
 }
 const source=()=>JSON.stringify(db.prepare('SELECT * FROM events ORDER BY seq').all());const before=source();
 const storage=projected=>({*events(kind){for(const r of (projected?projectedStatement(db,kind):db.prepare('SELECT data FROM events WHERE kind=? ORDER BY seq')).iterate(kind))yield JSON.parse(r.data);},readJsonl:(kind,n)=>db.prepare('SELECT data FROM events WHERE kind=? ORDER BY seq DESC LIMIT ?').all(kind,n).reverse().map(r=>JSON.parse(r.data))});
 const stats=projected=>Radar.prototype.getStats.call({storage:storage(projected),config:{horizonToleranceMs:120000},candidates:new Map(),status:[],getHealth:()=>null},at+4000000);
 assert.deepEqual(stats(true),stats(false));assert.equal(source(),before);
});
