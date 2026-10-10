import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {EventEmitter,once} from 'node:events';
import {setTimeout as delay} from 'node:timers/promises';
import {Worker} from 'node:worker_threads';
import {StatsService} from '../src/core/stats-service.js';
import {Storage} from '../src/core/storage.js';
import {Radar} from '../src/core/radar.js';
import {readConfig} from '../src/config.js';
import {startServer} from '../src/server/server.js';
function database(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'radar-worker-'));const s=new Storage(dir);t.after(()=>{s.close();fs.rmSync(dir,{recursive:true,force:true});});return s;}
function service(t,s,options={}){const x=new StatsService(path.join(s.dir,'radar.sqlite'),120000,options);t.after(()=>x.close());return x;}
function seed(s,n=20){const at=Date.now()-600000;s.transaction(()=>{for(let i=0;i<n;i++){
 const mint=`mint${i}`,id=`research:${i}`,cohort=i%2?'baseline':'early-activity';
 s.append('alerts',{id:`${mint}:${at}:1`,at,candidate:{mint},engineVersion:'0.2.9',qualification:{version:'qualification-1',disposition:i%2?'retain':'defer',state:'observing'}});
 s.append('research-entries',{id,at,version:'research-0.2.9',cohort,evidence:[{at,priceUsd:1}]});
 for(const h of ['5m','15m','60m'])s.append('outcomes',{id:`${mint}:${h}`,at:at+300000,mint,alertAt:at,version:'price-v2',horizon:h,status:i%5?'observed':'missing',multiple:i%2?1.2:.1,maxMultiple:2,coverage:i%3?'sampled':'gapped',score:75,entryMarketCap:100000});
 for(const h of ['30s','1m','2m','5m'])s.append('research-outcomes',{id:`${id}:${h}`,entryId:id,horizon:h,at:at+300000,status:i%5?'observed':'missing',returnPct:i%2?20:-90,coverage:i%3?'sampled':'gapped',reasonCode:'different-pool',tokenFollowup:{status:'observed',returnPct:25,basis:i%2?'alternate-pool':'original-pool',coverage:'sampled'},evidenceHistory:[{at,priceUsd:1}]});
 }});}
class FakeWorker extends EventEmitter{terminate(){this.emit('exit',1);return Promise.resolve(1);}complete(message){this.emit('message',message);this.emit('exit',0);}}
function success(at,n=1){return {ok:true,data:{alerts:n},snapshotAt:at,sourceMaxSeq:n,computeMs:4,workerHeapUsedBytes:1000};}
test('worker summary equals the synchronous reader and does not change evidence',async t=>{
 const s=database(t);seed(s);const before=s.db.prepare('SELECT COUNT(*) n,SUM(length(data)) bytes FROM events').get();
 const x=service(t,s);const result=await x.get();
 const expected=Radar.prototype.getStats.call({storage:s,config:{horizonToleranceMs:120000},candidates:new Map(),status:[],getHealth:()=>null},result.statistics.snapshotAt);
 const {totalCandidates,activeCandidates,health,status,...data}=expected;const {statistics,...actual}=result;
 assert.deepEqual(actual,data);assert.equal(statistics.servedFromCache,false);assert.equal(statistics.successes,1);
 assert.deepEqual(s.db.prepare('SELECT COUNT(*) n,SUM(length(data)) bytes FROM events').get(),before);
 assert.equal(s.readJsonl('research-outcomes')[0].evidenceHistory.length,1);
});
test('concurrent cold requests share one calculation, cache ages and replacement is atomic',async t=>{
 let now=100000,w,count=0;const s=database(t),x=service(t,s,{clock:()=>now,workerFactory:()=>{count++;return w=new FakeWorker();}});
 const a=x.get(),b=x.get();assert.equal(count,1);w.complete(success(now));
 assert.deepEqual(await a,await b);now+=31000;const stale=await x.get();assert.equal(count,2);assert.equal(stale.alerts,1);assert.equal(stale.statistics.refreshing,true);assert.equal(stale.statistics.servedFromCache,true);
 w.complete(success(now,2));assert.equal((await x.get()).alerts,2);assert.equal(x.health().successes,2);
});
test('worker failure keeps labelled cache, enforces cooldown and refuses expired statistics',async t=>{
 let now=100000,w,count=0;const s=database(t),x=service(t,s,{clock:()=>now,workerFactory:()=>{count++;return w=new FakeWorker();}});
 const first=x.get();w.complete(success(now));await first;
 now+=61000;await x.get();w.complete({ok:false,error:'read-timeout'});await Promise.resolve();
 const cached=await x.get();assert.equal(cached.statistics.stale,true);assert.equal(cached.statistics.lastError,'read-timeout');assert.equal(count,2);
 now+=60001;await assert.rejects(x.get(),{statusCode:503});w.complete({ok:false,error:'read-timeout'});
});
test('cold failure returns 503, retries after cooldown and never calls synchronous scanner statistics',async t=>{
 let now=100000,w;const s=database(t),x=service(t,s,{clock:()=>now,workerFactory:()=>w=new FakeWorker()});
 const first=x.get();w.emit('error',Object.assign(Error('private detail'),{code:'ERR_WORKER_OUT_OF_MEMORY'}));w.emit('exit',1);
 await assert.rejects(first,{statusCode:503});assert.equal(x.health().lastError,'worker-memory-limit');await assert.rejects(x.get(),{statusCode:503});
 now+=30001;const retry=x.get();w.complete(success(now));assert.equal((await retry).alerts,1);
});
test('watchdog terminates an unresponsive worker and shutdown rejects an active cold request',async t=>{
 const s=database(t),x=service(t,s,{timeoutMs:30,workerFactory:()=>new FakeWorker()});
 const keepAlive=setInterval(()=>{},10);try{await assert.rejects(x.get(),{statusCode:503});}finally{clearInterval(keepAlive);}
 assert.equal(x.health().lastError,'worker-timeout');
 const y=service(t,s,{workerFactory:()=>new FakeWorker()});const p=y.get();await y.close();await assert.rejects(p,{statusCode:503});
});
test('worker-start failure is sanitized and receives a cooldown',async t=>{
 const s=database(t),x=service(t,s,{workerFactory:()=>{throw Error('private path and credentials');}});
 await assert.rejects(x.get(),{statusCode:503});assert.equal(x.health().lastError,'worker-start-failed');assert.ok(x.health().retryAt>Date.now());
});
test('malformed or oversized database events fail explicitly without a partial result',async t=>{
 const s=database(t);s.append('research-entries',{id:'large',at:1,evidence:'x'.repeat(270000)});const x=service(t,s);
 await assert.rejects(x.get(),{statusCode:503});assert.equal(x.health().lastError,'row-size-limit');assert.equal(x.cache,null);
});
test('authenticated stats and metrics use worker; health remains responsive during its work',async t=>{
 const s=database(t);seed(s);const radar=new Radar({...readConfig({}),dashboardToken:'test',dashboardHost:'127.0.0.1'},s);
 radar.getStats=()=>{throw Error('Synchronous path must not be called');};
 const server=startServer(radar,0);await once(server,'listening');t.after(async()=>{await radar.statisticsService.close();await new Promise(r=>server.close(r));});
 const url=`http://127.0.0.1:${server.address().port}`,headers={Authorization:'Bearer test'};
 assert.equal((await fetch(url+'/api/stats')).status,401);
 assert.equal(radar.statisticsService.attempts,0);
 radar.statisticsService.workerFactory=()=>new Worker(`const {parentPort}=require('node:worker_threads');const t=Date.now();while(Date.now()-t<250){};parentPort.postMessage({ok:true,data:{uniquePaperEntries:2,missing60m:0},snapshotAt:Date.now(),computeMs:250});`,{eval:true,env:{}});
 let complete=false;const request=fetch(url+'/api/stats',{headers}).then(r=>r.json()).then(x=>{complete=true;return x;});
 while(!radar.statisticsService.pending)await delay(2);
 const health=await fetch(url+'/api/health',{headers});assert.equal(health.status,200);assert.equal(complete,false);
 assert.equal((await request).uniquePaperEntries,2);assert.equal((await fetch(url+'/metrics',{headers})).status,200);
});
