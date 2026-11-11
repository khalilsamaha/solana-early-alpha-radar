import test from 'node:test';
import assert from 'node:assert/strict';
import {PassThrough} from 'node:stream';
import {consumeSharedDiscovery,connectSharedDiscovery} from '../src/adapters/pumpportal-shared.js';
import {startPumpPortalSource} from '../src/adapters/pumpportal-source.js';
import {readConfig} from '../src/config.js';

const event={txType:'create',mint:'1'.repeat(31)+'2',signature:'2'.repeat(88),initialBuy:0};
const row=(seq=1,e=event)=>Buffer.from(JSON.stringify({v:1,seq,event:e})+'\n');
function setup(){
  const stream=new PassThrough(),tokens=[],creations=[],failures=[],messages=[];
  const stop=consumeSharedDiscovery(stream,x=>tokens.push(x),x=>messages.push(x),
    {success(){},failure(...x){failures.push(x);}},x=>creations.push(x));
  return {stream,tokens,creations,failures,messages,stop};
}
test('fragmented and combined discovery frames preserve launch/candidate callbacks',()=>{
  const t=setup(),first=row();
  try{
    t.stream.write(first.subarray(0,5));
    t.stream.write(Buffer.concat([first.subarray(5),row(2,{...event,txType:'migration'})]));
    assert.equal(t.tokens.length,2);assert.equal(t.creations.length,1);
    assert.equal(t.creations[0].fields.initialBuyReported,'0');assert.equal(t.failures.length,0);
  }finally{t.stop();}
});
for(const [name,bytes] of [
  ['sequence gap',row(2)],['duplicate',Buffer.concat([row(),row()])],
  ['trade event',row(1,{...event,txType:'buy'})],['malformed',Buffer.from('not-json\n')],
  ['invalid UTF8',Buffer.from([255,10])],['unknown envelope',Buffer.from('{"v":1,"seq":1,"event":{},"secret":"redact"}\n')],
  ['oversized chunk',Buffer.alloc(65537)]
])test(`${name} ends shared discovery with fixed diagnostics`,()=>{
  const t=setup();try{t.stream.write(bytes);assert.equal(t.failures.length,1);assert.equal(t.stream.destroyed,true);
    assert.ok(!JSON.stringify(t.messages).includes('redact'));}finally{t.stop();}
});
test('bounded incomplete line is rejected across chunks',()=>{
  const t=setup();try{t.stream.write(Buffer.alloc(40000,32));t.stream.write(Buffer.alloc(26000,32));assert.equal(t.failures.length,1);}finally{t.stop();}
});
test('EOF is visible and never constructs an upstream socket',async()=>{
  const original=globalThis.WebSocket;globalThis.WebSocket=class{constructor(){throw Error('must not dial');}};
  const t=setup();try{t.stream.end();await new Promise(r=>setImmediate(r));assert.equal(t.failures.length,1);}finally{t.stop();globalThis.WebSocket=original;}
});
test('registry write failure preserves discovery dispatch',()=>{
  const stream=new PassThrough(),tokens=[],messages=[];
  const stop=consumeSharedDiscovery(stream,x=>tokens.push(x),x=>messages.push(x),null,()=>{throw Error('fixture');});
  try{stream.write(row());assert.equal(tokens.length,1);assert.ok(messages.some(x=>x.includes('discovery continues')));}finally{stop();}
});
test('configuration selects only explicit direct/shared modes',()=>{
  assert.equal(readConfig({}).pumpPortalSource,'direct');
  assert.equal(readConfig({PUMPPORTAL_SOURCE:'shared',PUMPPORTAL_SOCKET:'/tmp/private/discovery.sock'}).pumpPortalSource,'shared');
  for(const e of [{PUMPPORTAL_SOURCE:'other'},{PUMPPORTAL_SOURCE:'shared'},
    {PUMPPORTAL_SOURCE:'shared',PUMPPORTAL_SOCKET:'relative'},
    {PUMPPORTAL_SOCKET:'/tmp/x'},{PUMPPORTAL_SOURCE:'shared',PUMPPORTAL_SOCKET:'/tmp/../x'}])assert.throws(()=>readConfig(e));
});
test('shared source failure never starts direct reconnect loop',()=>{
  const original=globalThis.WebSocket;let calls=0;
  globalThis.WebSocket=class{constructor(){calls++;}};
  try{
    assert.throws(()=>startPumpPortalSource({pumpPortalSource:'shared',pumpPortalSocket:'invalid',pumpPortalApiKey:'fixture'},()=>{}));
    assert.throws(()=>connectSharedDiscovery('https://example.invalid',()=>{}));
    assert.equal(calls,0);
  }finally{globalThis.WebSocket=original;}
});
