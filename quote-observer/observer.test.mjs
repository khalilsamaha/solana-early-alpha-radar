import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {Observer,openLedger,signalRecord,admission,sourceRows,recover} from './observer.mjs';
import {USDC,SOL} from './quote-check.mjs';
const M='6x4B4emuM8dLPhxkG6or7kAeM11oUG86Pr7bBmnopump';
const now=1791207205000;
const raw=(seq=1,kind='research-entries',at=now,extra={})=>({seq,kind,at,data:JSON.stringify({id:`research-0.2.9:early-activity:${M}:${at}`,version:'research-0.2.9',cohort:'early-activity',at,mint:M,candidate:{mint:M,priceUsd:0.001,liquidityUsd:null},security:'expired or unavailable',...extra})});
const ctx={now,busy:false,recent:[]};
function fixture(){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'quotes-test-'));const file=path.join(dir,'source.sqlite');const writer=new DatabaseSync(file);writer.exec('PRAGMA journal_mode=WAL; CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT,at INTEGER,data TEXT);CREATE INDEX events_kind_seq ON events(kind,seq)');const source=new DatabaseSync(file,{readOnly:true}),db=openLedger(path.join(dir,'ledger.sqlite'));return {dir,file,writer,source,db,add(r){writer.prepare('INSERT INTO events VALUES(?,?,?,?)').run(r.seq,r.kind,r.at,r.data);},close(){source.close();writer.close();db.close();fs.rmSync(dir,{recursive:true});}};}
test('entry schema preserves unknown security/liquidity and full entry id',()=>{const s=signalRecord(raw());assert.equal(s.cohort,'early-activity');assert.equal(s.features.liquidityUsd,null);assert.equal(s.features.security,'expired or unavailable');assert.equal(s.entryId,JSON.parse(raw().data).id);});
test('only first baseline alert accepted, upgrades excluded',()=>{assert.equal(signalRecord(raw(1,'alerts',now,{engineVersion:'0.2.9',id:`${M}:${now}:1`})).cohort,'baseline');assert.equal(signalRecord(raw(1,'alerts',now+1,{engineVersion:'0.2.9',id:`${M}:${now}:2`})).error,'later-alert');});
test('non-early research, old versions, malformed data rejected',()=>{assert.equal(signalRecord(raw(1,'research-entries',now,{cohort:'baseline'})).error,'other-cohort');assert.equal(signalRecord(raw(1,'research-entries',now,{version:'old'})).error,'unsupported-version');assert.equal(signalRecord({...raw(),data:'bad'}).error,'invalid-event');});
test('freshness and future timestamps are explicit exclusions',()=>{const s=signalRecord(raw());assert.equal(admission(s,ctx),'admitted');assert.equal(admission(s,{...ctx,now:now+15001}),'stale-signal');assert.equal(admission(s,{...ctx,now:now-1}),'future-timestamp');});
test('busy, repeated mint, hourly/day budgets and spacing are independent',()=>{const s=signalRecord(raw());for(const [extra,reason] of [[{busy:true},'observer-busy'],[{sameMint:true},'mint-already-sampled-24h'],[{recent:Array(6).fill(now)},'hour-budget'],[{recent:Array(144).fill(now-7200000)},'day-budget'],[{nextRequestAt:now+15001},'spacing-would-expire-signal']])assert.equal(admission(s,{...ctx,...extra}),reason);});
test('provider halt and cooldown exclude admission',()=>{const s=signalRecord(raw());assert.equal(admission(s,{...ctx,halted:true}),'provider-halted');assert.equal(admission(s,{...ctx,blockedUntil:now+1}),'provider-cooldown');});
test('indexed feed cursor merges cohorts, caps rows and does not read snapshots',()=>{const f=fixture();try{for(let i=1;i<=205;i++)f.add(raw(i));f.add(raw(300,'alerts',now,{engineVersion:'0.2.9',id:`${M}:${now}:1`}));f.add(raw(301,'snapshots'));const rows=sourceRows(f.source,{alerts:0,'research-entries':0});assert.equal(rows.length,201);assert.equal(rows.at(-1).seq,300);assert.equal(sourceRows(f.source,{alerts:300,'research-entries':200}).length,5);assert.throws(()=>f.source.exec('DELETE FROM events'),/readonly/);}finally{f.close();}});
test('registration starts at tail; source replacement is rejected',()=>{const f=fixture();try{f.add(raw());const o=new Observer(f.source,f.db,{now:()=>now});o.init('a');o.tick();assert.equal(f.db.prepare('SELECT count(*) n FROM signals').get().n,0);assert.throws(()=>o.init('b'),/changed/);}finally{f.close();}});
test('restart marks unfinished probes interrupted, preserves observations',()=>{const f=fixture();try{f.db.prepare('INSERT INTO probes VALUES(?,?,?,?,?)').run(1,now,M,'running',JSON.stringify({observations:[{status:'quoted'}]}));recover(f.db,now+1);const r=f.db.prepare('SELECT * FROM probes').get();assert.equal(r.state,'interrupted-restart');assert.equal(JSON.parse(r.data).observations.length,1);}finally{f.close();}});
test('end-to-end observer records fixed quantity, five HTTP attempts and signal timing',async()=>{const f=fixture();let t=now,calls=[];try{
const o=new Observer(f.source,f.db,{now:()=>t,sleep:async ms=>{t+=ms;},log:()=>{},quote:async(a,b,n)=>{calls.push([a,b,n,t]);const start=t;t+=250;return {status:'quoted',startedAt:start,receivedAt:t,latencyMs:250,outAmount:a===USDC?'123456789':'9000000',routePlan:[]};}});
o.init('test');f.add(raw());o.tick();await o.active;
assert.equal(calls.length,5);assert.ok(calls.slice(1).every(x=>x[2]==='123456789'));assert.ok(calls.every((x,i)=>i===0||x[3]-calls[i-1][3]>=10000));
const r=JSON.parse(f.db.prepare('SELECT data FROM probes').get().data);assert.equal(r.state,'complete');assert.equal(r.requests,5);assert.equal(r.signalToBuyRequestMs,10000);assert.equal(r.observations.at(-1).actualStartOffsetMs,120000);assert.equal(r.observations[1].quotedUsdcChangePct,-10);assert.equal(r.signal.features.security,'expired or unavailable');
const before=f.writer.prepare('SELECT * FROM events').all();o.tick();assert.deepEqual(f.writer.prepare('SELECT * FROM events').all(),before);assert.equal(f.db.prepare('SELECT count(*) n FROM signals').get().n,1);
}finally{f.close();}});
test('concurrent arrivals are retained as busy, no hidden queue',async()=>{const f=fixture();let finish;const waiting=new Promise(r=>finish=r);try{const o=new Observer(f.source,f.db,{now:()=>now,sleep:async()=>{},log:()=>{},quote:async()=>{await waiting;return {status:'no-route-evidence',startedAt:now,receivedAt:now};}});o.init('test');f.add(raw());f.add(raw(2,'research-entries',now,{mint:SOL,candidate:{mint:SOL}}));o.tick();assert.deepEqual(f.db.prepare('SELECT decision FROM signals ORDER BY seq').all().map(x=>x.decision),['admitted','observer-busy']);finish();await o.active;}finally{f.close();}});
test('rate limit halts remaining watch and persists cooldown',async()=>{const f=fixture();let t=now;try{const o=new Observer(f.source,f.db,{now:()=>t,sleep:async ms=>t+=ms,log:()=>{},quote:async()=>({status:'rate-limited',startedAt:t,receivedAt:t})});o.init('test');f.add(raw());o.tick();await o.active;assert.equal(JSON.parse(f.db.prepare("SELECT v FROM meta WHERE k='blockedUntil'").get().v),t+900000);assert.equal(JSON.parse(f.db.prepare('SELECT data FROM probes').get().data).requests,1);}finally{f.close();}});
test('expired signal after scheduler wait does not send a request',async()=>{const f=fixture();let t=now,calls=0;try{const o=new Observer(f.source,f.db,{now:()=>t,sleep:async ms=>t+=ms+20000,log:()=>{},quote:async()=>{calls++;}});o.init('test');f.add(raw());o.tick();await o.active;assert.equal(calls,0);const r=JSON.parse(f.db.prepare('SELECT data FROM probes').get().data);assert.equal(r.requests,0);assert.equal(r.observations[0].status,'signal-expired-before-request');}finally{f.close();}});
test('retention removes only old observer records',()=>{const f=fixture();try{f.db.prepare('INSERT INTO signals VALUES(?,?,?,?,?,?,?)').run(99,1,'baseline',M,'stale-signal',1,'{}');const o=new Observer(f.source,f.db,{now:()=>now});o.init('test');o.tick();assert.equal(f.db.prepare('SELECT count(*) n FROM signals').get().n,0);assert.equal(f.writer.prepare('SELECT count(*) n FROM events').get().n,0);}finally{f.close();}});
test('oversized events are classified without parsing large payloads',()=>{const f=fixture();try{f.add({...raw(),data:JSON.stringify({x:'x'.repeat(33000)})});const rows=sourceRows(f.source,{alerts:0,'research-entries':0});assert.equal(rows[0].data,'{}');}finally{f.close();}});
test('access denial persists a halt across observer reconstruction',async()=>{const f=fixture();let t=now;try{const o=new Observer(f.source,f.db,{now:()=>t,sleep:async ms=>t+=ms,log:()=>{},quote:async()=>({status:'access-denied',startedAt:t,receivedAt:t})});o.init('test');f.add(raw());o.tick();await o.active;const restarted=new Observer(f.source,f.db,{now:()=>t});restarted.init('test');f.add(raw(2,'research-entries',t,{mint:SOL,candidate:{mint:SOL}}));restarted.tick();assert.equal(f.db.prepare('SELECT decision FROM signals WHERE seq=2').get().decision,'provider-halted');}finally{f.close();}});
test('normal stop preserves completed quotes and labels remaining samples',async()=>{const f=fixture();let t=now,count=0;const c=new AbortController();try{const o=new Observer(f.source,f.db,{signal:c.signal,now:()=>t,sleep:async ms=>t+=ms,log:()=>{},quote:async()=>{count++;c.abort();return {status:'quoted',startedAt:t,receivedAt:t,outAmount:'123',routePlan:[]};}});o.init('test');f.add(raw());o.tick();await o.active;const r=JSON.parse(f.db.prepare('SELECT data FROM probes').get().data);assert.equal(count,1);assert.equal(r.state,'stopped');assert.equal(r.observations.filter(x=>x.reason==='interrupted').length,4);}finally{f.close();}});
test('rewound source sequence cannot silently stall the observer',()=>{const f=fixture();try{f.add(raw(100));const o=new Observer(f.source,f.db,{now:()=>now});o.init('test');f.writer.exec('DELETE FROM events');assert.throws(()=>o.tick(),/rewound/);}finally{f.close();}});
test('HTTP 400 does not trigger global transport cooldown; 5xx and timeouts do',async()=>{const {transientFailure}=await import('./observer.mjs');assert.equal(transientFailure({status:'http-error',httpStatus:400}),false);assert.equal(transientFailure({status:'http-error',httpStatus:503}),true);assert.equal(transientFailure({status:'timeout'}),true);});
test('cohort reservation and sampling registration survive restart',async()=>{const f=fixture();let t=now;try{const o=new Observer(f.source,f.db,{now:()=>t,sleep:async ms=>t+=ms,log:()=>{},quote:async()=>({status:'http-error',httpStatus:400,startedAt:t,receivedAt:t})});o.init('test');f.add(raw());o.tick();assert.equal(JSON.parse(f.db.prepare('SELECT data FROM probes').get().data).samplingPolicy,'three-cohort-budgets-v3');await o.active;const reg=f.db.prepare("SELECT v FROM meta WHERE k='samplingRegistration'").get().v;const restarted=new Observer(f.source,f.db,{now:()=>t});restarted.init('test');assert.equal(f.db.prepare("SELECT v FROM meta WHERE k='samplingRegistration'").get().v,reg);f.add(raw(2,'research-entries',t,{mint:SOL,candidate:{mint:SOL}}));restarted.tick();assert.equal(f.db.prepare('SELECT decision FROM signals WHERE seq=2').get().decision,'cohort-spacing');assert.equal(f.db.prepare("SELECT v FROM meta WHERE k='blockedUntil'").get(),undefined);}finally{f.close();}});
test('upgrade preserves legacy registration, cursor, probes and rolling cohort budget',()=>{const f=fixture();try{
 const meta=f.db.prepare('INSERT INTO meta VALUES(?,?)');
 meta.run('sourceIdentity',JSON.stringify('test'));meta.run('cursor',JSON.stringify({alerts:0,'research-entries':0}));
 meta.run('registeredAt',JSON.stringify(now-86400000));
 meta.run('samplingRegistration',JSON.stringify({id:'paced-cohorts-v1',registeredAt:now-3600000}));
 const original=JSON.stringify({samplingPolicy:'paced-cohorts-v1',observations:[{status:'quoted'}]});
 for(let i=1;i<=3;i++){
  const at=now-i*600000;
  f.db.prepare('INSERT INTO signals VALUES(?,?,?,?,?,?,?)').run(-i,at,'early-activity',M,'admitted',at,'{}');
  f.db.prepare('INSERT INTO probes VALUES(?,?,?,?,?)').run(-i,at,M,'complete',original);
 }
 const o=new Observer(f.source,f.db,{now:()=>now});o.init('test');f.add(raw(1,'research-entries',now,{mint:SOL,candidate:{mint:SOL}}));o.tick();
 assert.equal(f.db.prepare('SELECT decision FROM signals WHERE seq=1').get().decision,'cohort-hour-budget');
 assert.equal(JSON.parse(f.db.prepare("SELECT v FROM meta WHERE k='previousSamplingRegistration'").get().v).id,'paced-cohorts-v1');
 assert.equal(JSON.parse(f.db.prepare("SELECT v FROM meta WHERE k='registeredAt'").get().v),now-86400000);
 assert.equal(f.db.prepare('SELECT data FROM probes WHERE seq=-1').get().data,original);
 assert.equal(JSON.parse(f.db.prepare("SELECT v FROM meta WHERE k='cursor'").get().v)['research-entries'],1);
}finally{f.close();}});
test('feature registration and completed evidence persist while sampling registration is versioned',()=>{
 const f=fixture();try{
  const put=f.db.prepare('INSERT INTO meta VALUES(?,?)');
  put.run('sourceIdentity',JSON.stringify('test'));put.run('cursor',JSON.stringify({alerts:0,'research-entries':0}));
  const sampling=JSON.stringify({id:'cohort-budgets-v2',registeredAt:now-100000});
  put.run('samplingRegistration',sampling);
  const old=JSON.stringify({state:'complete',observations:[{leg:'buy',status:'quoted'}],signal:{seq:-1}});
  f.db.prepare('INSERT INTO probes VALUES(?,?,?,?,?)').run(-1,now-1000,M,'complete',old);
  new Observer(f.source,f.db,{now:()=>now}).init('test');
  const first=f.db.prepare("SELECT v FROM meta WHERE k='featureCaptureRegistration'").get().v;
  const reg=JSON.parse(first);assert.equal(reg.id,'entry-features-1');assert.equal(reg.shadow.changesAdmissions,false);assert.equal(reg.registeredAt,now);
  new Observer(f.source,f.db,{now:()=>now+10000}).init('test');
  assert.equal(f.db.prepare("SELECT v FROM meta WHERE k='featureCaptureRegistration'").get().v,first);
  assert.equal(f.db.prepare("SELECT v FROM meta WHERE k='previousSamplingRegistration'").get().v,sampling);
  assert.equal(JSON.parse(f.db.prepare("SELECT v FROM meta WHERE k='samplingRegistration'").get().v).id,'three-cohort-budgets-v3');
  assert.equal(f.db.prepare('SELECT data FROM probes WHERE seq=-1').get().data,old);
 }finally{f.close();}
});

test('fast feed upgrade starts at tail without skipping existing feeds or rewriting old evidence',()=>{
 const f=fixture();try{
  f.add(raw(5,'fast-shadow-entries'));
  f.db.prepare('INSERT INTO meta VALUES(?,?)').run('cursor',JSON.stringify({alerts:1,'research-entries':2}));
  const o=new Observer(f.source,f.db,{now:()=>now});o.init('test');
  const cursor=JSON.parse(f.db.prepare("SELECT v FROM meta WHERE k='cursor'").get().v);
  assert.deepEqual(cursor,{alerts:1,'research-entries':2,'fast-shadow-entries':5});
  assert.equal(sourceRows(f.source,cursor).length,0);
  f.add(raw(6,'fast-shadow-entries'));assert.equal(sourceRows(f.source,cursor)[0].seq,6);
  o.init('test');assert.equal(JSON.parse(f.db.prepare("SELECT v FROM meta WHERE k='cursor'").get().v)['fast-shadow-entries'],5);
 }finally{f.close();}
});
test('fresh Fast30 signal produces a five-request fixed-quantity watch, preserves unknowns',async()=>{
 const f=fixture();let t=now,calls=[];try{
  const obs=new Observer(f.source,f.db,{now:()=>t,sleep:async ms=>t+=ms,log:()=>{},quote:async(a,b,n)=>{
   calls.push([a,b,n]);return {status:'quoted',startedAt:t,receivedAt:t,outAmount:a===USDC?'123':'9000000',routePlan:[]};}});
  obs.init('test');const event={id:`fast30-shadow-1:${M}:${now}`,at:now,mint:M,cohort:'fast30-shadow',version:'fast30-shadow-1',ruleId:'fast30-shadow-1',liquidityUsd:null,
   security:{status:'expired or unavailable'},decision:{return30sPct:12},quality:{lastObservedAt:now},followup:{policy:'fast-followup-1',admitted:false}};
  f.add({seq:1,kind:'fast-shadow-entries',at:now,data:JSON.stringify(event)});obs.tick();await obs.active;
  const probe=JSON.parse(f.db.prepare('SELECT data FROM probes').get().data);
  assert.equal(probe.signal.cohort,'fast30-shadow');assert.equal(probe.samplingPolicy,'three-cohort-budgets-v3');
  assert.equal(probe.signal.features.liquidityUsd,null);assert.equal(probe.signal.features.security,'expired or unavailable');
  assert.equal(probe.signal.featureCapture.version,'fast-entry-features-1');assert.equal(probe.signal.followup.admitted,false);
  assert.equal(calls.length,5);assert.ok(calls.slice(1).every(x=>x[2]==='123'));
  assert.equal(signalRecord({seq:2,kind:'fast-shadow-entries',at:now,data:JSON.stringify({...event,version:'other'})}).error,'unsupported-version');
 }finally{f.close();}
});
