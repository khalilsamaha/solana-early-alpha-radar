import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {once} from 'node:events';
import {Storage} from '../src/core/storage.js';
import {Radar} from '../src/core/radar.js';
import {createEntry,updatePaper} from '../src/core/paper.js';
import {Notifications} from '../src/core/notifications.js';
import {readConfig} from '../src/config.js';
import {scoreCandidate} from '../src/core/scoring.js';
import {getTokenPair} from '../src/adapters/dexscreener.js';
import {searchToken,normalizeDiscoveryRow} from '../src/adapters/jupiter.js';
import {getMintSecurity} from '../src/adapters/helius.js';
import {sendTelegram} from '../src/adapters/telegram.js';
import {startServer} from '../src/server/server.js';
import {exitRisk} from '../src/core/exit.js';
const mint='So11111111111111111111111111111111111111112';
const other='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v';
const cfg=overrides=>({...readConfig({}),...overrides});
const fixture=JSON.parse(fs.readFileSync(new URL('../fixtures/scoring-cases.json',import.meta.url)))[0].current;
function store(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'radar-v2-'));const s=new Storage(dir);t.after(()=>{try{s.close();}catch{}fs.rmSync(dir,{recursive:true,force:true});});return s;}
const candidate=()=>({mint,symbol:'TEST',score:88,pairAddress:'pair',priceUsd:1,marketCap:100000});

test('invalid numeric config and unprotected remote bind fail before startup',()=>{
 assert.throws(()=>readConfig({DEX_RPM:'oops'}));assert.throws(()=>readConfig({DASHBOARD_HOST:'0.0.0.0'}));
 assert.throws(()=>readConfig({NOTIFICATIONS_ENABLED:'true'}));assert.equal(readConfig({DEX_RPM:''}).dexRpm,120);
});
test('missing/null security cannot produce a strong signal',()=>{
 const c={...fixture,mintAuthority:undefined,freezeAuthority:undefined,top10Pct:null};
 assert.ok(scoreCandidate(c).score<58);
});
test('a single active authority or extreme concentration imposes a cap',()=>{
 for(const change of [{mintAuthority:'active'},{freezeAuthority:'active'},{top10Pct:75},{extensions:['transferFeeConfig']}])assert.ok(scoreCandidate({...fixture,...change}).score<=55);
});
test('Jupiter never substitutes a different mint, and null is unknown',async()=>{
 assert.equal(await searchToken(mint,'key',{json:async()=>[{id:other,organicScore:100}]}),null);
 assert.equal(normalizeDiscoveryRow({id:mint,organicScore:null}).organicScore,undefined);
 assert.equal(normalizeDiscoveryRow({id:mint}).auditIsSus,undefined);
});
test('DEX requires exact Solana base mint and retains the paper pair',async()=>{
 const make=(id,address,liquidity)=>({chainId:'solana',pairAddress:id,baseToken:{address},liquidity:{usd:liquidity},priceUsd:'1'});
 const http={json:async()=>[make('wrong',other,999999),make('original',mint,10000),make('larger',mint,40000)]};
 assert.equal((await getTokenPair(mint,http,'original')).pairAddress,'original');
 assert.equal((await getTokenPair(mint,http)).pairAddress,'larger');
});
test('Helius rejects non-mint and malformed accounts instead of treating authorities as revoked',async()=>{
 await assert.rejects(getMintSecurity(mint,'key',{json:async()=>({result:{value:null}})}),/unavailable/);
});
test('Helius uses exact integer balances for account concentration',async()=>{
 let call=0;const http={json:async()=>({result:call++===0?{value:{owner:'token',data:{parsed:{type:'mint',info:{mintAuthority:null,freezeAuthority:null,supply:'100000000000000000000'}}}}}:{value:[{amount:'25000000000000000000'}]}})};
 assert.equal((await getMintSecurity(mint,'key',http)).top10Pct,25);
});
test('storage alert, candidate, and notification commit or roll back together',t=>{
 const s=store(t),c=candidate(),a={id:'signal-1',at:1,candidate:c};
 assert.throws(()=>s.transaction(()=>{s.recordAlert(c,a,true);throw new Error('crash');}));
 assert.equal(s.readJsonl('alerts').length,0);assert.equal(s.dueNotifications(2).length,0);assert.deepEqual(s.loadCandidates(),{});
 s.recordAlert(c,a,true);assert.equal(s.dueNotifications(2).length,1);
});
test('outcome identity deduplicates retried checkpoint writes',t=>{
 const s=store(t),o={mint,alertAt:1,horizon:'5m',at:2};s.append('outcomes',o);s.append('outcomes',o);assert.equal(s.readJsonl('outcomes').length,1);
});
test('legacy import aborts on corruption and preserves original file',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'radar-legacy-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 fs.writeFileSync(path.join(dir,'alerts.jsonl'),'bad json\n');assert.throws(()=>new Storage(dir),/Legacy import aborted/);assert.equal(fs.readFileSync(path.join(dir,'alerts.jsonl'),'utf8'),'bad json\n');
});
test('legacy outcomes stay explicitly separate from price-v2 statistics',t=>{
 const s=store(t);s.append('outcomes',{mint,alertAt:1,horizon:'60m',at:2,legacy:true,maxMultiple:100});
 assert.equal(new Radar(cfg(),s).getStats().evaluated60m,0);
});
test('paper return follows price even when market cap changes independently',()=>{
 const c=candidate();c.paperEntry=createEntry(c,0);c.priceUsd=2;c.marketCap=50000;
 const rows=updatePaper(c,300000,90000,true);assert.equal(rows[0].multiple,2);
});
test('missing checkpoint is never filled by much later price',()=>{
 const c=candidate();c.paperEntry=createEntry(c,0);c.priceUsd=50;
 const rows=updatePaper(c,900000,90000,true);assert.equal(rows.find(x=>x.horizon==='5m').status,'missing');assert.equal(rows.find(x=>x.horizon==='15m').status,'observed');
});
test('stale data and changed pairs cannot fill checkpoints',()=>{
 for(const stale of [true,false]){const c=candidate();c.paperEntry=createEntry(c,0);if(!stale)c.pairAddress='changed';const rows=updatePaper(c,400000,90000,!stale);assert.equal(rows[0].status,'missing');}
});
test('post-horizon rally does not count as a within-horizon high',()=>{
 const c=candidate();c.paperEntry=createEntry(c,0);c.priceUsd=4;
 const rows=updatePaper(c,301000,90000,true);assert.equal(rows[0].maxMultiple,1);assert.equal(rows[0].multiple,4);assert.equal(rows[0].lagMs,1000);
});
test('peak-to-trough drawdown is distinguished from drawdown below entry',()=>{
 const c=candidate();c.paperEntry=createEntry(c,0);c.priceUsd=2;updatePaper(c,60000,90000,true);c.priceUsd=1.5;updatePaper(c,120000,90000,true);assert.equal(c.paperEntry.maxDrawdownPct,-25);
});
test('notification retry survives worker recreation and is marked delivered only after success',async t=>{
 const s=store(t),config=cfg({notificationsEnabled:true});s.queue({id:'a',at:100});let calls=0;
 await new Notifications(config,s,async()=>{calls++;throw new Error('offline');}).flush(101);
 assert.equal(s.notificationStats().pending,1);
 await new Notifications(config,s,async()=>{calls++;return {messageId:1};}).flush(3000);
 assert.equal(s.notificationStats().sent,1);assert.equal(calls,2);
});
test('expired alerts are recorded without sending late signals',async t=>{
 const s=store(t);s.queue({id:'old',at:1});let calls=0;
 await new Notifications(cfg({notificationsEnabled:true}),s,async()=>{calls++;}).flush(1000000);
 assert.equal(calls,0);assert.equal(s.notificationStats().expired,1);
});
test('Telegram flood cooldown blocks subsequent queued messages',async t=>{
 const s=store(t);s.queue({id:'a',at:1});s.queue({id:'b',at:2});let calls=0;
 const send=async()=>{calls++;throw Object.assign(new Error('429'),{retryAfterMs:60000});};
 await new Notifications(cfg({notificationsEnabled:true}),s,send).flush(10);
 await new Notifications(cfg({notificationsEnabled:true}),s,send).flush(5000);assert.equal(calls,1);
});
test('Telegram HTTP success with ok:false is a failed delivery',async t=>{
 const original=global.fetch;t.after(()=>global.fetch=original);global.fetch=async()=>({ok:true,status:200,json:async()=>({ok:false,error_code:403})});
 await assert.rejects(sendTelegram(cfg({notificationsEnabled:true,telegramBotToken:'x',telegramChatId:'y'}),{text:'test'}),e=>e.permanent===true);
});
test('fair scheduler includes new, paper-tracked, and lower-ranked candidates',t=>{
 const r=new Radar(cfg({batchSize:3}),store(t));
 r.candidates=new Map([[mint,{mint,firstSeenAt:1,score:100,lastAttemptAt:1}],['new',{mint:'new',firstSeenAt:2}],['paper',{mint:'paper',firstSeenAt:1,lastAttemptAt:1,paperEntry:{version:'price-v2',horizons:{}}}]]);
 assert.deepEqual(new Set(r.selectBatch(100000).map(x=>x.mint)),new Set(['new','paper',mint]));
});
test('failed market enrichment cannot create a new alert from cached strong data',async t=>{
 const s=store(t),r=new Radar(cfg(),s,{getTokenPair:async()=>{throw new Error('offline');}});
 r.addCandidate({...fixture,mint,firstSeenAt:Date.now(),pairCreatedAt:Date.now(),priceUsd:1,securityCheckedAt:Date.now()});
 await r.enrichOne(mint);assert.equal(s.readJsonl('alerts').length,0);assert.equal(r.candidates.get(mint).stale,true);
});
test('live-fixture pipeline persists alert and paper entry once across restart',async t=>{
 const s=store(t),now=Date.now();const market={...fixture,mint,pairCreatedAt:now,priceUsd:1,pairAddress:'pair'};
 const adapters={getTokenPair:async()=>market,getMintSecurity:async()=>({mintAuthority:null,freezeAuthority:null,top10Pct:18,securityCheckedAt:Date.now()}),searchToken:async()=>({organicScore:80,holderCount:300})};
 const c=cfg({heliusApiKey:'test',jupiterApiKey:'test'});let r=new Radar(c,s,adapters);r.addCandidate({mint});await r.enrichOne(mint);await r.refreshMetadata('helius',mint);await r.refreshMetadata('jupiter',mint);await r.enrichOne(mint);
 assert.equal(s.readJsonl('alerts').length,1);assert.equal(s.loadCandidates()[mint].paperEntry.version,'price-v2');
 r=new Radar(c,s,adapters);await r.enrichOne(mint);assert.equal(s.readJsonl('alerts').length,1);
});
test('old candidate remains tracked until its paper checkpoints resolve',async t=>{
 const s=store(t),r=new Radar(cfg(),s,{getTokenPair:async()=>null});const c={...candidate(),firstSeenAt:Date.now()-10e6,pairCreatedAt:Date.now()-10e6};c.paperEntry=createEntry(c,Date.now()-4000000);r.candidates.set(mint,c);
 await r.enrichOne(mint);assert.equal(s.readJsonl('outcomes').length,3);assert.equal(r.candidates.get(mint).paperEntry.horizons['60m'].status,'missing');
});
test('exit engine identifies deterioration and rejects stale conclusions',()=>{
 const c={...candidate(),txns:{m5:{buys:5,sells:20}},priceChange:{m5:-25}};
 assert.equal(exitRisk(c,null,true).level,'high');assert.equal(exitRisk(c,null,false).level,'unknown');
});
test('HTTP auth, methods, readiness, and static allowlist',async t=>{
 const r=new Radar(cfg({dashboardToken:'secret'}),store(t));
 const server=startServer(r,0,path.resolve('public'));t.after(()=>server.close());await once(server,'listening');
 const base=`http://127.0.0.1:${server.address().port}`;
 assert.equal((await fetch(base+'/api/stats')).status,401);
 assert.equal((await fetch(base+'/api/stats',{headers:{Authorization:'Bearer secret'}})).status,200);
 assert.equal((await fetch(base+'/readyz')).status,503);
 assert.equal((await fetch(base+'/healthz')).status,200);
 assert.equal((await fetch(base+'/.env')).status,404);
 assert.equal((await fetch(base+'/api/stats',{method:'POST'})).status,405);
 assert.ok((await fetch(base+'/')).headers.get('content-security-policy').includes("frame-ancestors 'none'"));
});

test('database reopen restores alerts, candidate and pending notification',t=>{
 const s=store(t),c={...candidate(),paperEntry:createEntry(candidate(),10),alertLevel:1};
 s.recordAlert(c,{id:`${mint}:10:1`,at:10,candidate:c},true);s.close();
 const restored=new Storage(s.dir);
 try{assert.equal(restored.loadCandidates()[mint].paperEntry.at,10);assert.equal(restored.readJsonl('alerts').length,1);assert.equal(restored.dueNotifications(20).length,1);}finally{restored.close();}
});
test('native live backup restores with SQLite integrity intact',async t=>{
 const s=store(t);s.saveCandidate(candidate());s.append('alerts',{id:'backup-alert',at:1});
 const dest=path.join(s.dir,'backup.sqlite');await s.backup(dest);
 const {DatabaseSync}=await import('node:sqlite');const db=new DatabaseSync(dest);
 try{assert.equal(db.prepare('PRAGMA integrity_check').get().integrity_check,'ok');assert.equal(db.prepare('SELECT count(*) AS n FROM candidates').get().n,1);assert.equal(db.prepare('SELECT count(*) AS n FROM events').get().n,1);}finally{db.close();}
});
test('rediscovery restores archived first paper entry after candidate eviction',t=>{
 const s=store(t),r=new Radar(cfg(),s),c={...candidate(),paperEntry:createEntry(candidate(),10),alertLevel:2};
 r.save(c);s.deleteCandidate(mint);r.candidates.delete(mint);const next=r.addCandidate({mint});assert.equal(next.paperEntry.at,10);assert.equal(next.alertLevel,2);
});
test('statistics retain missing and gapped results in explicit denominators',t=>{
 const s=store(t),r=new Radar(cfg(),s);
 for(const [i,status] of [[1,'observed'],[2,'missing']]) {
  s.append('alerts',{id:`${mint}:${i}:1`,at:i,candidate:{mint}});
  s.append('outcomes',{mint,alertAt:i,horizon:'60m',at:5,version:'price-v2',status,coverage:'gapped',maxMultiple:2,score:88,entryMarketCap:50000});
 }
 const stats=r.getStats();assert.equal(stats.evaluated60m,1);assert.equal(stats.missing60m,1);assert.equal(stats.gapped60m,1);assert.equal(stats.doubleHitRate60m,1);assert.equal(stats.conservativeObservedDoubleRate,0.5);
});
