import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import os from 'node:os';
import path from 'node:path';
import {once} from 'node:events';
import {tokenLinks,validSolanaAddress} from '../public/token-links.js';
import {startServer} from '../src/server/server.js';
import {Storage} from '../src/core/storage.js';
import {Radar} from '../src/core/radar.js';
import {readConfig} from '../src/config.js';
const mint='So11111111111111111111111111111111111111112';

// Controller tests use small DOM stubs; they do not claim browser rendering coverage.
function controller() {
 const nodes=new Map(),handlers={};
 const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',checked:true,innerHTML:'',textContent:'',dataset:{},listeners:{},
   addEventListener(event,fn){this.listeners[event]=fn;},showModal(){this.open=true;},close(){this.open=false;},focus(){this.focused=true;},select(){this.selected=true;}});return nodes.get(id);};
 const row={qualification:{state:'deteriorating',disposition:'defer',reasons:['Recent drop <unsafe>']},mint,symbol:'<img src=x onerror=bad()>',score:75,firstSeenAt:Date.now(),discoverySources:['fixture'],decision:{status:'blocked',reasons:['Liquidity unknown <unsafe>'],metadataReason:'Waiting for liquidity'},decisionTimeline:{priorHistoryUnavailable:true,startedAt:Date.now()}};
 const summary={entries:1,horizons:{'60m':{observed:1,medianReturnPct:-90,aboveEntry:0,aboveEntryPct:0,loss50:1,loss50Pct:100,sampledPeak2x:1,checkpoint2x:0,missing:0,gapped:0,pending:0,overdue:0,invalid:0}}};
 const stats={qualification:{version:'qualification-1',entries:1,groups:{defer:summary}},research:{tokenFollowup:{baseline:{entries:1,horizons:{'30s':{originalPool:0,alternatePool:1,medianReturnPct:20,gapped:0,missing:0,pending:0,overdue:0}}}},summary:{baseline:{entries:1,horizons:{'30s':{observed:1,medianReturnPct:12,aboveEntry:1,gapped:0,missing:0,pending:0,overdue:0}}}},events:[{mint,candidate:row,at:Date.now(),event:'early activity',security:'incomplete',reasons:['<unsafe>']}]},paperSummaryV026:summary,paperSummaryV025:summary,paperSummary:summary,paperSummaryCurrent:{entries:0,horizons:{}},health:{research:{enabled:true,notificationsEnabled:false},providers:{},notifications:{},oldestAttemptAgeMs:0},status:[],buckets:{}};
 const responses={'/api/stats':stats,'/api/candidates?active=1&limit=1000':[row],'/api/alerts?limit=50':[{at:Date.now(),candidate:row,qualification:row.qualification,scoring:{score:75,reasons:[]}}],'/api/outcomes?limit=50':[{mint,horizon:'5m',multiple:1.1}]};
 let copied;
 const sandbox={tokenLinks,validSolanaAddress,createRefreshLoop:({load,render,onState})=>{const request=async()=>{render(await load());onState({lastSuccessAt:Date.now(),ageMs:0,stale:false});};return {request,start:request};},document:{querySelector:node,addEventListener:(name,fn)=>handlers[name]=fn},
   navigator:{clipboard:{writeText:async value=>{copied=value;}}},console,Date,clearTimeout:()=>{},setTimeout:()=>1,
   fetch:async url=>({ok:true,json:async()=>responses[url]})};
 const source=fs.readFileSync(new URL('../public/app.js',import.meta.url),'utf8').replace(/^import[^\n]+\n/gm,'');
 vm.runInNewContext(source,sandbox);
 return {node,handlers,sandbox,get copied(){return copied;}};
}
test('dashboard controller renders exact-address links and escapes token metadata',async()=>{
 const c=controller();await new Promise(setImmediate);
 for(const id of ['#candidates','#alerts','#outcomes']) {
   const html=c.node(id).innerHTML;
   assert.ok(html.includes('https://phantom.com/tokens/solana/'+mint));
   assert.ok(html.includes('data-copy-mint="'+mint+'"'));
   assert.ok(html.includes('rel="noopener noreferrer"'));
   assert.ok(!html.includes('<img src=x'));
 }
 assert.ok(c.node('#candidates').innerHTML.includes('&lt;img'));
 c.node('#search').value='no-such-token';c.node('#search').listeners.input();
 assert.ok(c.node('#candidates').innerHTML.includes('No matching candidates'));
 c.node('#search').value=mint;c.node('#search').listeners.input();assert.ok(c.node('#candidates').innerHTML.includes('Copy mint'));
});
test('dashboard copy action handles success and denied clipboard with full-mint fallback',async()=>{
 const c=controller();const event={target:{closest:()=>({dataset:{copyMint:mint}})}};
 await c.handlers.click(event);assert.equal(c.copied,mint);assert.match(c.node('#actionStatus').textContent,/Copied Solana mint/);
 c.sandbox.navigator.clipboard.writeText=async()=>{throw new Error('Denied');};
 await c.handlers.click(event);assert.equal(c.node('#mintDialog').open,true);assert.equal(c.node('#mintValue').value,mint);assert.equal(c.node('#mintValue').selected,true);
 c.node('#closeMintDialog').listeners.click();assert.equal(c.node('#mintDialog').open,false);
});
test('server serves shared browser module under CSP and keeps API authenticated',async t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'radar-link-http-'));const s=new Storage(dir);
 const r=new Radar({...readConfig({}),dashboardToken:'test-token'},s);
 const server=startServer(r,0,path.resolve('public'));await once(server,'listening');
 t.after(()=>{server.close();s.close();fs.rmSync(dir,{recursive:true,force:true});});
 const base=`http://127.0.0.1:${server.address().port}`;
 const response=await fetch(base+'/token-links.js');assert.equal(response.status,200);assert.match(response.headers.get('content-type'),/javascript/);
 assert.match(await response.text(),/export function tokenLinks/);
 const refresh=await fetch(base+'/refresh-loop.js');assert.equal(refresh.status,200);assert.match(refresh.headers.get('content-type'),/javascript/);assert.match(await refresh.text(),/export function createRefreshLoop/);
 const html=await (await fetch(base+'/')).text();assert.match(html,/id="mintDialog"/);assert.match(html,/id="actionStatus"/);
 assert.equal((await fetch(base+'/api/candidates')).status,401);
 assert.equal((await fetch(base+'/api/candidates',{headers:{Authorization:'Bearer test-token'}})).status,200);
 const stats=await (await fetch(base+'/api/stats',{headers:{Authorization:'Bearer test-token'}})).json();
 assert.equal(stats.health.research.enabled,true);assert.equal(stats.health.research.notificationsEnabled,false);
 assert.equal(stats.research.summary.baseline.entries,0);assert.ok(html.includes('id="researchRows"'));
});

test('dashboard renders loss metrics, unknown liquidity, blockers and version cohort selection',async()=>{
 const c=controller();await new Promise(setImmediate);
 assert.match(c.node('#candidates').innerHTML,/Not reported by source/);
 assert.match(c.node('#candidates').innerHTML,/Liquidity unknown &lt;unsafe&gt;/);
 assert.match(c.node('#candidates').innerHTML,/Earlier milestones are unknown/);
 assert.match(c.node('#metrics').innerHTML,/-90.0%/);
 assert.match(c.node('#resultRows').innerHTML,/1 \/ 0/);
 assert.match(c.node('#resultScope').textContent,/1 unique entries/);
 c.node('#resultCohort').value='current';c.node('#resultCohort').listeners.change();
 assert.match(c.node('#resultScope').textContent,/0 unique entries/);
 assert.match(c.node('#resultScope').textContent,/v0.2.4/);
});

test('research dashboard separates cohorts and escapes event text',async()=>{
 const c=controller();await new Promise(setImmediate);
 assert.match(c.node('#researchMode').textContent,/SHADOW MODE/);
 assert.match(c.node('#researchRows').innerHTML,/12.0%/);
 assert.match(c.node('#continuityRows').innerHTML,/20.0%/);
 assert.match(c.node('#continuityRows').innerHTML,/0 \/ 1/);
 assert.match(c.node('#researchEvents').innerHTML,/early activity/);
 assert.match(c.node('#researchEvents').innerHTML,/&lt;unsafe&gt;/);
 assert.ok(!c.node('#researchEvents').innerHTML.includes('<img'));
 c.node('#resultCohort').value='v025';c.node('#resultCohort').listeners.change();
 assert.match(c.node('#resultScope').textContent,/v0.2.5/);
 c.node('#resultCohort').value='v026';c.node('#resultCohort').listeners.change();assert.match(c.node('#resultScope').textContent,/v0.2.6/);
 c.node('#resultCohort').value='v028';c.node('#resultCohort').listeners.change();assert.match(c.node('#resultScope').textContent,/v0.2.8/);
 c.node('#resultCohort').value='v027';c.node('#resultCohort').listeners.change();assert.match(c.node('#resultScope').textContent,/v0.2.7/);
});

test('qualification dashboard leads with deterioration and escapes reasons',async()=>{
 const c=controller();await new Promise(setImmediate);
 assert.match(c.node('#candidates').innerHTML,/deteriorating/);
 assert.match(c.node('#alerts').innerHTML,/shadow defer/);
 assert.match(c.node('#alerts').innerHTML,/&lt;unsafe&gt;/);
 assert.match(c.node('#qualificationRows').innerHTML,/defer/);
 assert.match(c.node('#qualificationScope').textContent,/baseline alerts continue/);
 c.node('#resultCohort').value='v029';c.node('#resultCohort').listeners.change();
 assert.match(c.node('#resultScope').textContent,/v0.2.9/);
});
