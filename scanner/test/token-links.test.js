import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {tokenLinks} from '../public/token-links.js';
import {alertButtons,formatAlert,sendTelegram} from '../src/adapters/telegram.js';
import {auditToken} from '../scripts/token-audit.mjs';
import {Storage} from '../src/core/storage.js';
import {DatabaseSync} from 'node:sqlite';
const mint='So11111111111111111111111111111111111111112';
const pair='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v';

test('platform links use exact mint and exact pool on fixed trusted origins',()=>{
 const links=tokenLinks({mint,pairAddress:pair,dexUrl:'https://evil.invalid',symbol:'wrong-ticker'});
 assert.deepEqual(links.map(x=>new URL(x.url).hostname),['phantom.com','jup.ag','dexscreener.com','solscan.io']);
 for(const link of links)assert.ok(link.url.endsWith(link.label==='DEX Screener'?pair:mint));
 assert.ok(!JSON.stringify(links).includes('evil'));
});
test('invalid mint and other chains never generate misleading Solana links',()=>{
 for(const c of [{mint:'javascript:alert(1)'},{mint:'<script>'},{mint:'0x1234'},{mint,chainId:'ethereum'},{},null])assert.deepEqual(tokenLinks(c),[]);
 assert.equal(tokenLinks({mint,pairAddress:'unverified'}).length,3);
});
test('signal and exit alerts have token buttons; operational alerts do not',()=>{
 for(const alert of [{candidate:{mint,pairAddress:pair}},{text:'Deterioration',candidate:{mint}}]) {
   const keyboard=alertButtons(alert).inline_keyboard.flat();
   assert.equal(keyboard.find(x=>x.copy_text).copy_text.text,mint);
   assert.ok(keyboard.some(x=>x.text==='Phantom'));
 }
 assert.equal(alertButtons({text:'Service recovered'}),undefined);
});
test('Telegram request includes links and copy control without enabling parse mode',async t=>{
 let sent;t.mock.method(globalThis,'fetch',async(url,options)=>{sent=JSON.parse(options.body);return {ok:true,json:async()=>({ok:true,result:{message_id:5}})};});
 const alert={text:'Paper observation',candidate:{mint,pairAddress:pair}};
 const result=await sendTelegram({notificationsEnabled:true,telegramBotToken:'test',telegramChatId:'test'},alert);
 assert.equal(result.messageId,5);assert.equal(sent.text,'Paper observation');assert.ok(sent.reply_markup);
 assert.equal(sent.parse_mode,undefined);assert.deepEqual(sent.link_preview_options,{is_disabled:true});
});
test('signal text retains full mint and explicit Solana network',()=>{
 const alert={id:'test',at:Date.now(),candidate:{mint},scoring:{band:'watch',score:72,metrics:{ageMin:2}}};
 assert.ok(formatAlert(alert).includes(`Network: Solana | Mint: ${mint}`));
});
test('read-only mint audit distinguishes inactive, archived, and absent evidence',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'radar-audit-'));const s=new Storage(dir);
 s.saveCandidate({mint,inactive:true,score:25,firstSeenAt:1,discoverySources:['test']});
 s.append('alerts',{id:'test',at:2,candidate:{mint}});s.setState({paperEntry:{at:2}},`paper:${mint}`);
 const db=new DatabaseSync(path.join(dir,'radar.sqlite'),{readOnly:true});db.exec('PRAGMA query_only=ON');
 t.after(()=>{db.close();s.close();fs.rmSync(dir,{recursive:true,force:true});});
 const current=auditToken(db,mint);assert.equal(current.current.hiddenByActiveOnlyFilter,true);assert.equal(current.retainedEvents[0].count,1);
 s.deleteCandidate(mint);const archived=auditToken(db,mint);assert.equal(archived.currentlyRetained,false);assert.ok(archived.evidenceNote.includes('historical evidence'));
 const absent=auditToken(db,pair);assert.equal(absent.currentlyRetained,false);assert.ok(absent.evidenceNote.includes('does not prove'));
 assert.throws(()=>auditToken(db,"' OR 1=1 --"));assert.equal(s.readJsonl('alerts').length,1);
});
