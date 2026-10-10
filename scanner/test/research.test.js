import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {MomentumHistory,turnoverPoints} from '../src/core/momentum.js';
import {Research,summarizeResearch} from '../src/core/research.js';
import {scoreCandidate} from '../src/core/scoring.js';
import {Storage} from '../src/core/storage.js';
import {Radar} from '../src/core/radar.js';
import {Notifications} from '../src/core/notifications.js';
import {readConfig} from '../src/config.js';
const T=1800000000000;
const mint='So11111111111111111111111111111111111111112';
const config={...readConfig({}),notificationsEnabled:true};
const token=(i=0,patch={})=>({mint,symbol:'FIXTURE',pairAddress:'pool',priceUsd:1+i*.04,liquidityUsd:20000,
 volume:{m5:10000+i*1500},txns:{m5:{buys:80+i*5,sells:30+i}},priceChange:{m5:20},
 marketObservedAt:T+i*15000,score:75,securityCheckedAt:T,mintAuthority:null,freezeAuthority:null,top10Pct:10,
 firstSeenAt:T,launchAt:T,organicScore:70,holderCount:300,marketCap:100000,...patch});
function setup(t,cfg={}){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'research-'));const storage=new Storage(dir);t.after(()=>{storage.close();fs.rmSync(dir,{recursive:true,force:true});});return {storage,r:new Research({...config,...cfg},storage)};}
function feed(r,i,patch={}){const c=token(i,patch);return r.observe(c,c,{score:c.score},c.marketObservedAt,true);}

test('window growth survives one identical provider refresh; pool changes and gaps require warmup',()=>{
 const h=new MomentumHistory();for(let i=0;i<=4;i++)h.observe(token(i),T+i*15000);
 let c=token(4,{marketObservedAt:T+75000});const m=h.observe(c,c.marketObservedAt);
 assert.ok(m.ready);assert.ok(m.r60.volumeDeltaPerMinute>0);assert.equal(m.r60.spanMs,60000);
 assert.equal(m.unchangedForMs,15000);assert.ok(m.r60.returnPct>0);
 assert.equal(h.observe({...c,priceUsd:99},c.marketObservedAt).r60.returnPct,m.r60.returnPct);
 assert.equal(h.observe(token(6,{pairAddress:'other'}),T+90000).ready,false);
 assert.equal(h.resetReason,'pool changed');
 assert.equal(h.observe(token(10,{pairAddress:'other'}),T+150000).ready,false);
 assert.equal(h.resetReason,'observation gap');
 assert.equal(h.describe(T+210000).ready,false);
});
test('history is bounded and a fully unchanged minute does not claim movement',()=>{
 const h=new MomentumHistory();for(let i=0;i<1000;i++)h.observe(token(0),T+i*1000);
 assert.equal(h.rows.length,256);assert.equal(h.describe(T+999000).r60.changedSamples,0);
 assert.equal(h.describe(T+999000).r60.returnPct,0);
});
test('turnover is continuous at 4x and experimental scoring preserves security caps',()=>{
 assert.ok(Math.abs(turnoverPoints(4.001)-turnoverPoints(3.999))<.01);
 assert.equal(turnoverPoints(8),-3);assert.equal(turnoverPoints(100),-8);
 const metrics={r60:{volumeDeltaPerMinute:10000,transactionsDeltaPerMinute:100}};
 for(const patch of [{mintAuthority:'active'},{freezeAuthority:'active'},{top10Pct:70},{extensions:['transferHook']}])
  assert.ok(scoreCandidate(token(4,patch),null,T+60000,metrics).score<=55);
 assert.ok(scoreCandidate(token(4,{mintAuthority:undefined}),null,T+60000,metrics).score<=57);
 assert.ok(scoreCandidate(token(4,{liquidityUsd:undefined}),null,T+60000,metrics).score<=45);
 assert.ok(scoreCandidate(token(4,{auditIsSus:true}),null,T+60000,metrics).score<=49);
});
test('shadow activity is deduplicated, does not queue Telegram and records all four checkpoints',t=>{
 const {storage,r}=setup(t);for(let i=0;i<=24;i++)feed(r,i);
 const entries=storage.readJsonl('research-entries');assert.equal(entries.length,1);assert.equal(entries[0].cohort,'early-activity');
 assert.equal(storage.readJsonl('research-events').filter(e=>e.event==='early activity').length,1);
 assert.deepEqual(storage.notificationStats(),{});
 const outcomes=storage.readJsonl('research-outcomes');assert.equal(outcomes.length,4);assert.ok(outcomes.every(o=>o.coverage==='sampled'&&o.status==='observed'));
 assert.equal(summarizeResearch(entries,outcomes,T+360000)['early-activity'].horizons['5m'].observed,1);
});
test('severe flags block early activity; incomplete unknown-pumpfun liquidity remains explicitly observational',t=>{
 const a=setup(t);for(let i=0;i<=8;i++)feed(a.r,i,{top10Pct:70});assert.equal(a.storage.readJsonl('research-entries').length,0);
 const b=setup(t);for(let i=0;i<=4;i++)feed(b.r,i,{liquidityUsd:undefined,dexId:'pumpfun',mintAuthority:undefined});
 const e=b.storage.readJsonl('research-events')[0];assert.equal(e.security,'incomplete');assert.match(e.reasons.join(' '),/Liquidity unknown/);assert.ok(e.experimentalScore<=45);
});
test('rapid drop, escalation and recovery use a latch rather than repeated alerts',t=>{
 const {storage,r}=setup(t);for(let i=0;i<=4;i++)feed(r,i);
 const patch=price=>({priceUsd:price,exitRisk:{level:'low'}});
 feed(r,5,patch(.98));feed(r,6,patch(.7));feed(r,7,patch(.7));
 let events=storage.readJsonl('research-events');assert.equal(events.filter(e=>e.event==='rapid drop').length,1);assert.equal(events.filter(e=>e.event==='risk escalation').length,1);
 for(let i=8;i<=12;i++)feed(r,i,patch(1.05+(i-8)*.03));
 events=storage.readJsonl('research-events');assert.equal(events.filter(e=>e.event==='recovery observed').length,1);
});
test('stale prices and repeated timestamps cannot create checkpoints or activity',t=>{
 const {storage,r}=setup(t);for(let i=0;i<=4;i++)feed(r,i);
 const c=token(4);r.observe(c,c,{score:75},T+90000,true);
 assert.equal(storage.readJsonl('research-outcomes').length,0);
 const stale=token(4);r.observe(stale,stale,{score:75},T+120000,true);
 assert.equal(r.describe(mint,T+120000).stage,'data unavailable');
 assert.equal(storage.readJsonl('research-events').length,1);
});
test('a pre-deadline quote cannot count as a post-deadline checkpoint',t=>{
 const {storage,r}=setup(t);r.baseline(token(0),T);
 const c=token(1);r.observe(c,c,{score:75},T+31000,true);assert.equal(storage.readJsonl('research-outcomes').length,0);
 feed(r,3);assert.equal(storage.readJsonl('research-outcomes')[0].horizon,'30s');
});
test('restart preserves cooldown and marks pending outcomes gapped; eviction records missing',t=>{
 const {storage,r}=setup(t);for(let i=0;i<=4;i++)feed(r,i);
 const restarted=new Research(config,storage);for(let i=5;i<=10;i++)feed(restarted,i);
 assert.equal(storage.readJsonl('research-entries').length,1);
 const rows=storage.readJsonl('research-outcomes');assert.ok(rows.every(o=>o.coverage==='gapped'));
 restarted.drop(mint,T+160000);assert.equal(storage.readJsonl('research-outcomes').filter(o=>o.status==='missing').length,2);
 const summary=summarizeResearch(storage.readJsonl('research-entries'),storage.readJsonl('research-outcomes'),T+500000)['early-activity'];
 assert.equal(summary.horizons['30s'].gapped,1);assert.equal(summary.horizons['30s'].medianReturnPct,null);assert.equal(summary.horizons['5m'].missing,1);
});
test('sweep records missing outcomes and summaries distinguish pending from overdue',t=>{
 const {storage,r}=setup(t);r.baseline(token(0),T);const entries=storage.readJsonl('research-entries');
 assert.equal(summarizeResearch(entries,[],T+10000).baseline.horizons['30s'].pending,1);
 assert.equal(summarizeResearch(entries,[],T+100000).baseline.horizons['30s'].overdue,1);
 r.sweep(T+331000);assert.equal(storage.readJsonl('research-outcomes').length,4);
 assert.ok(storage.readJsonl('research-outcomes').every(o=>o.status==='missing'));
});
test('first strong baseline alert enters short-window comparison exactly once',t=>{
 const {storage}=setup(t);const radar=new Radar(config,storage);const c=token(0,{stale:false,exitRisk:{level:'low'}});
 const scoring={...scoreCandidate(c,null,T),score:90,band:'strong'};
 radar.maybeAlert(c,scoring,T);radar.maybeAlert(c,scoring,T+1000);
 assert.equal(storage.readJsonl('alerts').length,1);assert.equal(storage.readJsonl('research-entries').length,1);
 assert.equal(storage.readJsonl('research-entries')[0].cohort,'baseline');
});
test('opt-in research notification expires after 45s; disabling feature cancels pending research only',async t=>{
 const {storage,r}=setup(t,{researchNotifications:true});for(let i=0;i<=4;i++)feed(r,i);
 assert.equal(storage.notificationStats().pending,1);let sends=0;
 const n=new Notifications({...config,researchNotifications:true},storage,async()=>{sends++;return {};});
 await n.flush(T+106000);assert.equal(sends,0);assert.equal(storage.notificationStats().expired,1);
 storage.queue({id:'off',at:T+200000,type:'research'});storage.queue({id:'ordinary',at:T+200000,type:'signal'});
 await new Notifications(config,storage,async()=>{sends++;return {};}).flush(T+200001);
 assert.equal(sends,1);assert.equal(storage.notificationStats().expired,2);
});
test('pruning bounds research state while preserving baseline state and recent entries',t=>{
 const {storage}=setup(t);storage.setState({updatedAt:T},'research:old');storage.setState({updatedAt:T+1},'research:new');storage.setState({updatedAt:T},'paper:old');
 storage.append('research-entries',{id:'old',at:T});storage.append('alerts',{id:'baseline',at:T});storage.prune(T+1);
 assert.deepEqual(storage.getState('research:old'),{});assert.equal(storage.getState('research:new').updatedAt,T+1);
 assert.equal(storage.getState('paper:old').updatedAt,T);assert.equal(storage.readJsonl('alerts').length,1);assert.equal(storage.readJsonl('research-entries').length,0);
});

test('SGI archived replay recognizes the early drawdown and later escalation without inventing pre-alert observations',t=>{
 const {storage,r}=setup(t);
 const input=JSON.parse(fs.readFileSync(new URL('../fixtures/sgi-research-history.json',import.meta.url)));
 let paper=null;
 for(const {data:c} of input.events){
  if(c.at>=1790930427251&&!paper)paper={pairAddress:c.pairAddress,peakPrice:.0002366};
  if(paper&&c.pairAddress===paper.pairAddress)paper.peakPrice=Math.max(paper.peakPrice,c.priceUsd);
  const row={...c,marketObservedAt:c.at,paperEntry:paper};
  r.observe(row,row,{score:c.score},c.at,true);
 }
 const events=storage.readJsonl('research-events');
 assert.equal(events.find(e=>e.event==='rapid drop').at,1790930590250);
 assert.equal(events.find(e=>e.event==='risk escalation').at,1790930686585);
 assert.ok(!events.some(e=>e.event!=='pool changed'&&e.at<1790930427251));
 for(const event of events.filter(e=>e.event==='pool changed')){
  const index=input.events.findIndex(x=>x.data.at===event.at);assert.ok(index>0);
  assert.equal(event.poolChange.from,input.events[index-1].data.pairAddress);
  assert.equal(event.poolChange.to,input.events[index].data.pairAddress);
  assert.equal(event.poolChange.migrationVerified,false);
 }
 assert.equal(storage.notificationStats().sent,undefined);
});

test('shadow engine does not change baseline alert sequence or paper prices',async t=>{
 let now=T;t.mock.method(Date,'now',()=>now);
 const on=setup(t),off=setup(t);
 const a=new Radar(config,on.storage),b=new Radar({...config,researchEnabled:false},off.storage);
 a.addCandidate(token(0));b.addCandidate(token(0));
 for(let i=0;i<=24;i++){
  now=T+i*15000;const c=token(i,{jupiterCheckedAt:now,securityCheckedAt:now});
  a.addCandidate(c);b.addCandidate(c);
  await a.enrichOne(mint,{market:c,observedAt:now});await b.enrichOne(mint,{market:c,observedAt:now});
 }
 const normalize=rows=>rows.map(({marketContext,qualification,evidence,...rest})=>rest);
 assert.deepEqual(normalize(on.storage.readJsonl('alerts')),normalize(off.storage.readJsonl('alerts')));
 assert.deepEqual(on.storage.readJsonl('outcomes'),off.storage.readJsonl('outcomes'));
 assert.equal(on.storage.notificationStats().pending,off.storage.notificationStats().pending);
 assert.ok(on.storage.readJsonl('research-entries').length>0);assert.equal(off.storage.readJsonl('research-entries').length,0);
});
