import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {qualify,qualificationSummary} from '../src/core/qualification.js';
import {Research} from '../src/core/research.js';
import {Storage} from '../src/core/storage.js';
import {Radar} from '../src/core/radar.js';
import {readConfig} from '../src/config.js';
import {formatAlert} from '../src/adapters/telegram.js';
const T=1800000000000,mint='So11111111111111111111111111111111111111112';
const c={mint,pairAddress:'p',marketObservedAt:T,priceUsd:1,liquidityUsd:20000,txns:{m5:{buys:100,sells:50}},volume:{m5:1500},organicScore:0};
const research=(m={},stage='rising')=>({stage,metrics:{at:T,pairAddress:'p',ready:true,unchangedForMs:0,drawdownPct:0,lastIntervalReturnPct:1,r30:{returnPct:5,liquidityChangePct:0},r60:{returnPct:12,changedSamples:4},...m}});
function setup(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qualification-'));const storage=new Storage(dir);t.after(()=>{storage.close();fs.rmSync(dir,{recursive:true,force:true});});return storage;}
test('shadow retain requires fresh changing rising history, never just a high score',()=>{
 assert.equal(qualify(c,research(),T).disposition,'retain');
 assert.equal(qualify({...c,score:99},null,T).disposition,'defer');
 assert.equal(qualify(c,research({ready:false}),T).state,'insufficient history');
 for(const m of [{at:T+1},{at:T-45001},{pairAddress:'another'},{r30:null},{r60:null}])assert.equal(qualify(c,research(m),T).disposition,'defer');
 assert.equal(qualify({...c,stale:true},research(),T).disposition,'defer');
});
test('a collapse overrides positive five-minute metrics including during warmup',()=>{
 for(const metrics of [{drawdownPct:-82},{r30:{returnPct:-21}},{r30:{returnPct:1,liquidityChangePct:-31}},{ready:false,lastIntervalReturnPct:-81}]) {
  const q=qualify({...c,score:85,priceChange:{m5:57.93}},research(metrics),T);
  assert.equal(q.state,'deteriorating');assert.equal(q.disposition,'defer');
 }
});
test('unconfirmed recovery, repeated markets and falling direction remain distinct',()=>{
 assert.equal(qualify(c,research({},'recovery unconfirmed'),T).state,'recovery unconfirmed');
 assert.equal(qualify(c,research({unchangedForMs:46000}),T).state,'unchanged market');
 assert.equal(qualify(c,research({r30:{returnPct:-1,liquidityChangePct:null}}),T).state,'falling');
 assert.equal(qualify(c,research({},'recovery observed'),T).disposition,'retain');
 assert.equal(qualify(c,research({r60:{returnPct:0,changedSamples:0}}),T).state,'observing');
});
test('zero organic and small average trade are descriptive flags, not automatic exclusions',()=>{
 const q=qualify({...c,volume:{m5:150}},research(),T);
 assert.equal(q.metrics.averageReportedTradeUsd,1);assert.equal(q.flags.length,2);assert.equal(q.disposition,'retain');
 assert.equal(qualify({...c,txns:{m5:{buys:null,sells:4}}},research(),T).metrics.averageReportedTradeUsd,null);
});
test('archived Mr Beast alert is labelled deteriorating despite score 85',()=>{
 const fixture=JSON.parse(fs.readFileSync(new URL('../fixtures/qualification-collapse.json',import.meta.url)));
 const q=qualify(fixture.candidate,fixture.research,fixture.at);
 assert.equal(q.state,'deteriorating');assert.equal(q.disposition,'defer');assert.equal(fixture.score,85);
 const message=formatAlert({id:'test',at:fixture.at,candidate:fixture.candidate,qualification:q,scoring:{score:85,band:'strong',metrics:{ageMin:4,buys5m:1841,sells5m:1351},reasons:[],risks:[]}});
 assert.match(message,/RADAR DETERIORATING/);assert.doesNotMatch(message,/RADAR STRONG/);assert.match(message,/baseline alert retained for comparison/);
});
test('same-cycle collapse qualification preserves baseline entry, queue and immutable evidence',t=>{
 const storage=setup(t),config={...readConfig({}),notificationsEnabled:true};const radar=new Radar(config,storage);
 for(let i=0;i<6;i++) {
  const row={...c,marketObservedAt:T-90000+i*15000,priceUsd:1+i*.01,score:50};
  radar.research.observe(row,row,{score:50},row.marketObservedAt,true);
 }
 const row={...c,priceUsd:.18,score:85,stale:false,exitRisk:{level:'high'}};
 radar.research.observe(row,row,{score:85},T,true);
 radar.maybeAlert(row,{score:85,band:'strong',metrics:{ageMin:4},reasons:[],risks:[]},T);
 const a=storage.readJsonl('alerts')[0];assert.equal(a.qualification.state,'deteriorating');assert.equal(storage.notificationStats().pending,1);
 assert.equal(storage.readJsonl('research-entries').filter(e=>e.cohort==='baseline').length,1);
 assert.equal(row.paperEntry.priceUsd,.18);assert.equal(a.evidence.inputs.priceUsd,.18);
 radar.research.observe({...row,priceUsd:1,marketObservedAt:T+15000},row,{score:85},T+15000,true);
 assert.equal(a.evidence.samples.at(-1).price,.18);
 assert.equal(storage.readJsonl('alerts')[0].qualification.state,'deteriorating');
 assert.equal(radar.getStats().qualification.groups.defer.entries,1);
});
test('event history is bounded; checkpoint evidence is shorter and excludes a falsely current sample',t=>{
 const storage=setup(t);const r=new Research(readConfig({}),storage);
 for(let i=0;i<500;i++) {
  const row={...c,marketObservedAt:T+i*1000,priceUsd:1};r.observe(row,row,{score:40},row.marketObservedAt,true);
 }
 assert.equal(r.evidence(mint).samples.length,24);assert.equal(r.evidence(mint,8).samples.length,8);
 const restarted=new Research(readConfig({}),storage);assert.equal(restarted.evidence(mint).samples.length,0);
 assert.equal(qualify({...c,marketObservedAt:T+500000},restarted.describe(mint,T+500000),T+500000).state,'insufficient history');
});
test('shadow summaries preserve maturity and separate gapped returns from means',()=>{
 const a=(id,disposition)=>({candidate:{mint:id},id:`${id}:${T}:1`,engineVersion:'0.2.9',qualification:{version:'qualification-1',state:disposition,disposition}});
 const outcome=(mint,multiple,coverage='sampled')=>({mint,alertAt:T,version:'price-v2',horizon:'5m',status:'observed',multiple,coverage});
 const s=qualificationSummary([a('a','retain'),a('b','retain'),a('c','defer')],[outcome('a',.5),outcome('b',100,'gapped')],T+1000000,120000);
 const h=s.groups.retain.horizons['5m'];assert.equal(h.observed,1);assert.equal(h.gapped,1);assert.equal(h.meanReturnPct,-50);assert.equal(h.overdue,0);
 assert.equal(s.groups.defer.horizons['5m'].overdue,1);assert.equal(s.groups.defer.horizons['60m'].pending,1);
});
