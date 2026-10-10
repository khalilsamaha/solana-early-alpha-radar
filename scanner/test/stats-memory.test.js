import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {Storage} from '../src/core/storage.js';
import {Radar} from '../src/core/radar.js';
import {summaryEvents,compactSummaryRow,statisticsHealth} from '../src/core/stats-memory.js';
import {summarizeOutcomes} from '../src/core/outcome-summary.js';
import {qualificationSummary} from '../src/core/qualification.js';
import {summarizeResearch,RESEARCH_HORIZONS} from '../src/core/research.js';
import {summarizeContinuity} from '../src/core/continuity.js';
import {MOMENTUM_VERSION} from '../src/core/momentum.js';
const T=1791450000000;
function fixture(){
 const events={'alerts':[],'outcomes':[],'research-entries':[],'research-outcomes':[],'research-events':[]};
 for(let i=0;i<24;i++){
  const mint=`mint${i}`,at=T+i*1000,id=`alert:${at}:${mint}`;
  events.alerts.push({id,at,candidate:{mint,research:{huge:'preserve me'}},engineVersion:i%4?'0.2.9':'0.2.4',legacy:i===0,
    qualification:{version:'qualification-1',disposition:i%2?'retain':'defer',state:i%2?'rising activity':'deteriorating',metrics:{some:'evidence'}}});
  if(i===3)events.alerts.push({...events.alerts.at(-1),id:`upgrade:${at}:${mint}`});
  for(const horizon of ['5m','15m','60m'])if(i%7!==0)events.outcomes.push({id:`${mint}:${horizon}`,at:T+5000000,mint,alertAt:at,version:i===2?'old':'price-v2',horizon,
    status:i%5?'observed':'missing',multiple:i===4?null:i===6?0:i%2?1.2:0.1,maxMultiple:2.1,coverage:i%3?'sampled':'gapped',score:72+i,entryMarketCap:50000+i*15000,unused:{x:'saved'}});
  const entryId=`research:${i}`;
  events['research-entries'].push({id:entryId,at,cohort:i%2?'baseline':'early-activity',version:i===1?'old':MOMENTUM_VERSION,evidence:[{priceUsd:1}],features:{x:1}});
  for(const horizon of Object.keys(RESEARCH_HORIZONS))if(i%7!==0)events['research-outcomes'].push({id:`${entryId}:${horizon}`,entryId,at:T+5000000,horizon,
   status:i%5?'observed':'missing',returnPct:i===4?null:i%2?15:-90,coverage:i%3?'sampled':'gapped',reasonCode:i%5?undefined:'different-pool',
   evidenceHistory:[{at:1,priceUsd:1,liquidityUsd:10000}],tokenFollowup:i===1?undefined:{status:i%5?'observed':'missing',returnPct:20,coverage:i%4?'sampled':'gapped',basis:i%3?'original-pool':'alternate-pool',evidence:{samples:24}}});
 }
 return events;
}
function harness(storage){return {storage,config:{horizonToleranceMs:120000},candidates:new Map(),status:[],getHealth:()=>({ready:true})};}
const legacySource=Radar.prototype.getStats.toString().replaceAll(/summaryEvents\(this.storage,'([^']+)'\)/g,"this.storage.events('$1')");
const legacy=Function('summarizeOutcomes','qualificationSummary','MOMENTUM_VERSION','summarizeResearch','summarizeContinuity','RESEARCH_HORIZONS',`return (${legacySource.replace(/^getStats\(/,'function(')});`)(summarizeOutcomes,qualificationSummary,MOMENTUM_VERSION,summarizeResearch,summarizeContinuity,RESEARCH_HORIZONS);
test('all statistics match the original reader, including missing, pending, legacy and alternate-pool rows',()=>{
 const rows=fixture(),storage={events:kind=>rows[kind],readJsonl:(kind,n)=>rows[kind].slice(-n)};
 const clock=Date.now;Date.now=()=>T+200000;
 try {assert.deepEqual(Radar.prototype.getStats.call(harness(storage)),legacy.call(harness(storage)));}finally{Date.now=clock;}
});
test('SQLite iterator retains summary equality and leaves detailed evidence unchanged',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'radar-stats-'));const storage=new Storage(dir);
 t.after(()=>{storage.close();fs.rmSync(dir,{recursive:true,force:true});});
 storage.transaction(()=>{for(const [kind,rows] of Object.entries(fixture()))for(const row of rows)storage.append(kind,row);});
 const before=JSON.stringify([...storage.db.prepare('SELECT * FROM events ORDER BY seq').iterate()]);
 const clock=Date.now;Date.now=()=>T+6000000;
 try{assert.deepEqual(Radar.prototype.getStats.call(harness(storage)),legacy.call(harness(storage)));}finally{Date.now=clock;}
 assert.equal(JSON.stringify([...storage.db.prepare('SELECT * FROM events ORDER BY seq').iterate()]),before);
 assert.equal([...storage.events('research-outcomes')][0].evidenceHistory.length,1);
});
test('summary iteration reads lazily and releases references to detailed nested evidence',()=>{
 let read=0;const full=fixture()['research-outcomes'].find(o=>o.tokenFollowup);
 const iter=summaryEvents({*events(){read++;yield full;read++;yield full;}},'research-outcomes');
 assert.equal(read,0);const row=iter.next().value;assert.equal(read,1);
 assert.equal(row.evidenceHistory,undefined);assert.equal(row.tokenFollowup.evidence,undefined);
 assert.notEqual(row.tokenFollowup,full.tokenFollowup);assert.equal(full.evidenceHistory.length,1);
});
test('null follow-up remains unavailable, zero values remain zero, unsupported kinds fail',()=>{
 const row=compactSummaryRow('research-outcomes',{returnPct:0,tokenFollowup:null});
 assert.equal(row.returnPct,0);assert.equal(row.tokenFollowup,undefined);
 assert.throws(()=>compactSummaryRow('snapshots',{}));
});
test('health identifies the fix and reports numeric heap and resident memory',()=>{
 const h=statisticsHealth();assert.equal(h.version,'stats-memory-1.0.0');
 assert.ok(h.heapUsedBytes>0);assert.ok(h.heapLimitBytes>=h.heapUsedBytes);assert.ok(h.rssBytes>0);
});
