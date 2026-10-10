import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {Storage} from '../src/core/storage.js';
import {Radar} from '../src/core/radar.js';
import {readConfig} from '../src/config.js';
import {scoreCandidate} from '../src/core/scoring.js';
import {describeDecision,recordDecision,ensureTimeline} from '../src/core/decision.js';
import {summarizeOutcomes} from '../src/core/outcome-summary.js';
import {auditToken} from '../scripts/token-audit.mjs';
const mint='So11111111111111111111111111111111111111112';
const market={mint,pairAddress:'pool',priceUsd:1,liquidityUsd:20000,txns:{m5:{buys:80,sells:30}},volume:{m5:15000},priceChange:{m5:25},marketCap:100000,socialCount:2};
function setup(t){
 let now=1800000000000;t.mock.method(Date,'now',()=>now);
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'radar-observe-')),storage=new Storage(dir),config={...readConfig({}),heliusApiKey:'fixture',notificationsEnabled:true};
 const r=new Radar(config,storage,{getMintSecurity:async()=>({mintAuthority:null,freezeAuthority:null,top10Pct:10,securityCheckedAt:now})});
 t.after(()=>{storage.close();fs.rmSync(dir,{recursive:true,force:true});});
 return {storage,r,config,get now(){return now;},advance(ms){now+=ms;}};
}
test('unknown liquidity remains conservatively capped without being labelled measured low',()=>{
 const c={...market,mintAuthority:null,freezeAuthority:null,top10Pct:10,organicScore:80,holderCount:300,launchAt:1000};
 for(const value of [undefined,null,NaN]) {
  const result=scoreCandidate({...c,liquidityUsd:value},null,2000);
  assert.equal(result.score,scoreCandidate({...c,liquidityUsd:0},null,2000).score);
  assert.ok(result.score<=45);assert.ok(result.risks.some(r=>r.reason.startsWith('Liquidity unknown')));
 }
 assert.ok(scoreCandidate({...c,liquidityUsd:100},null,2000).risks.some(r=>r.reason==='very thin liquidity (<$5k)'));
});
test('unknown-liquidity visibility does not promote metadata or emit signals; milestones survive restart',async t=>{
 const x=setup(t);x.r.addCandidate({mint});
 await x.r.enrichOne(mint,{market:{...market,liquidityUsd:undefined},observedAt:x.now});
 let c=x.r.candidates.get(mint);assert.equal(x.r.metadataEligible(c),false);assert.equal(c.decision.liquidity,'unknown');assert.equal(x.storage.readJsonl('alerts').length,0);
 assert.equal(c.decisionTimeline.firstSeenAt,x.now);assert.equal(c.decisionTimeline.priorHistoryUnavailable,false);
 x.advance(15000);await x.r.enrichOne(mint,{market,observedAt:x.now});
 assert.equal(x.r.candidates.get(mint).decisionTimeline.firstLiquidityEligibleAt,x.now);
 await x.r.refreshMetadata('helius',mint);
 assert.equal(x.r.candidates.get(mint).decisionTimeline.firstSecurityCompleteAt,x.now);
 x.r.addCandidate({mint,organicScore:80,holderCount:300,jupiterCheckedAt:x.now});
 x.advance(15000);await x.r.enrichOne(mint,{market,observedAt:x.now});
 const alerts=x.storage.readJsonl('alerts');assert.equal(alerts.length,1);assert.equal(alerts[0].engineVersion,'0.2.9');
 c=x.r.candidates.get(mint);assert.equal(c.decisionTimeline.firstAlertAt,x.now);assert.equal(c.decisionTimeline.firstAlertEligibleAt,x.now);
 assert.equal(c.decision.status,'already-alerted');assert.equal(x.storage.notificationStats().pending,1);
 const r2=new Radar(x.config,x.storage);assert.deepEqual(r2.candidates.get(mint).decisionTimeline,c.decisionTimeline);
 assert.equal(x.storage.getState(`paper:${mint}`).decisionTimeline.firstAlertAt,x.now);
 x.advance(15000);await r2.enrichOne(mint,{market,observedAt:x.now});assert.equal(x.storage.readJsonl('alerts').length,1);
});
test('trace does not fabricate old milestones and limits ordinary state-change events',t=>{
 const x=setup(t),c={...market,firstSeenAt:x.now-100000,marketObservedAt:x.now,score:50};
 recordDecision(x.storage,c,x.config,x.now);assert.equal(c.decisionTimeline.priorHistoryUnavailable,true);
 assert.equal(c.decisionTimeline.firstMarketAt,x.now);const n=x.storage.readJsonl('decisions').length;
 for(let i=0;i<3;i++){x.advance(15000);c.stale=!c.stale;recordDecision(x.storage,c,x.config,x.now);}
 assert.equal(x.storage.readJsonl('decisions').length,n);
 x.advance(20000);c.stale=true;recordDecision(x.storage,c,x.config,x.now);assert.equal(x.storage.readJsonl('decisions').length,n+1);
 c.stale=false;c.securityCheckedAt=x.now;c.mintAuthority=null;c.freezeAuthority=null;c.top10Pct=10;
 recordDecision(x.storage,c,x.config,x.now,'metadata');assert.equal(c.decisionTimeline.firstSecurityCompleteAt,x.now);
 assert.equal(x.storage.readJsonl('decisions').length,n+2);
});
test('API decision recomputes expiration without changing stored score or original trace',t=>{
 const x=setup(t),c={...market,firstSeenAt:x.now,marketObservedAt:x.now,securityCheckedAt:x.now,mintAuthority:null,freezeAuthority:null,top10Pct:10,score:90};
 ensureTimeline(c,x.now);x.r.save(c);const before=JSON.stringify(x.storage.loadCandidates());x.advance(400000);
 const d=x.r.getCandidates()[0].decision;assert.equal(d.marketFresh,false);assert.equal(d.securityFresh,false);assert.equal(d.status,'blocked');
 assert.equal(JSON.stringify(x.storage.loadCandidates()),before);
});
test('audit retains decision milestones after eviction and reports API acknowledgement without payloads',t=>{
 const x=setup(t),c={...market,firstSeenAt:x.now,marketObservedAt:x.now,score:40};recordDecision(x.storage,c,x.config,x.now);
 x.storage.queue({id:'signal',at:x.now,candidate:{mint},secret:'do-not-export'});x.storage.updateNotification('signal',{status:'sent',attempts:1,nextAt:x.now,deliveredAt:x.now+1200});
 const report=auditToken(x.storage.db,mint,x.now+5000);assert.equal(report.currentlyRetained,false);assert.equal(report.decisionTimeline.firstMarketAt,x.now);
 assert.equal(report.notificationDeliveries[0].acknowledgementDelayMs,1200);assert.ok(!JSON.stringify(report).includes('do-not-export'));
 x.storage.append('decisions',{mint,at:x.now-8*86400000});x.storage.append('alerts',{mint,at:x.now-8*86400000});
 x.storage.prune(x.now-7*86400000);assert.equal(x.storage.readJsonl('decisions').length,1);assert.equal(x.storage.readJsonl('alerts').length,1);
});
test('outcome summaries separate peaks, terminal losses, missing, pending, invalid and overdue',()=>{
 const entries=Array.from({length:6},(_,i)=>({id:`mint${i}:${1000+i}:1`,candidate:{mint:`mint${i}`}}));
 const rows=[{mint:'mint0',alertAt:1000,horizon:'60m',version:'price-v2',status:'observed',multiple:.1,maxMultiple:3,coverage:'sampled'},
  {mint:'mint1',alertAt:1001,horizon:'60m',version:'price-v2',status:'observed',multiple:2,maxMultiple:4,coverage:'gapped'},
  {mint:'mint2',alertAt:1002,horizon:'60m',version:'price-v2',status:'missing'},
  {mint:'mint3',alertAt:1003,horizon:'60m',version:'price-v2',status:'observed',multiple:null},
  {mint:'not-our-entry',alertAt:1003,horizon:'60m',version:'price-v2',status:'observed',multiple:100}];
 const h=summarizeOutcomes(entries,rows,10000).horizons['60m'];
 assert.deepEqual(h,{observed:2,missing:1,pending:2,overdue:0,invalid:1,gapped:1,aboveEntry:1,aboveEntryPct:50,loss50:1,loss50Pct:50,medianReturnPct:5,sampledPeak2x:2,checkpoint2x:1});
 assert.equal(summarizeOutcomes(entries,rows,5000000).horizons['60m'].overdue,2);
 assert.equal(summarizeOutcomes([],[]).horizons['60m'].medianReturnPct,null);
});
test('summary version cohort belongs to first entry, never to a later score upgrade',t=>{
 const x=setup(t);x.storage.append('alerts',{id:`${mint}:1000:1`,at:1000,candidate:{mint},scoring:{score:75}});
 x.storage.append('alerts',{id:`${mint}:1000:2`,at:2000,candidate:{mint},scoring:{score:90},engineVersion:'0.2.4'});
 const s=x.r.getStats();assert.equal(s.uniquePaperEntries,1);assert.equal(s.paperSummary.entries,1);assert.equal(s.paperSummaryCurrent.entries,0);
});
