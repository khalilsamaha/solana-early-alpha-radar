import test from 'node:test';
import assert from 'node:assert/strict';
import {createRefreshLoop} from '../public/refresh-loop.js';
const flush=()=>new Promise(setImmediate);
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function harness(load,render=()=>{}) {
 let now=100000,id=0,tick;const timers=new Map(),states=[];
 const loop=createRefreshLoop({load,render,onState:s=>states.push(s),clock:()=>now,
 setTimer:(fn,ms)=>{timers.set(++id,{fn,at:now+ms});return id;},clearTimer:i=>timers.delete(i),
 setTicker:fn=>{tick=fn;return 1;},clearTicker:()=>{tick=null;}});
 return {loop,states,timers,advance(ms){now+=ms;const due=[...timers.entries()].filter(([,t])=>t.at<=now);for(const [i,t] of due){timers.delete(i);t.fn();}tick?.();},get now(){return now;}};
}
test('hung dashboard request times out, aborts and recovers on automatic retry',async()=>{
 let calls=0,firstSignal;const rendered=[];
 const x=harness(signal=>{calls++;if(calls===1){firstSignal=signal;return new Promise(()=>{});}return {ok:true};},r=>rendered.push(r));
 const first=x.loop.start();await flush();x.advance(15000);await first;
 assert.equal(firstSignal.aborted,true);assert.match(x.states.at(-1).error,/timed out/);assert.equal(x.loop.state().lastSuccessAt,null);
 x.advance(10000);await flush();assert.equal(calls,2);assert.deepEqual(rendered,[{ok:true}]);assert.equal(x.states.at(-1).error,null);assert.equal(x.states.at(-1).stale,false);x.loop.stop();
});
test('manual refresh supersedes an old request and ignores its late response',async()=>{
 const old=deferred(),rendered=[];let calls=0;
 const x=harness(()=>++calls===1?old.promise:Promise.resolve('new'),v=>rendered.push(v));
 const p=x.loop.start();await flush();await x.loop.request();old.resolve('obsolete');await p;await flush();
 assert.deepEqual(rendered,['new']);assert.equal(x.timers.size,1);x.loop.stop();assert.equal(x.timers.size,0);
});
test('failed or unauthorized refresh retains last success time and makes the display stale',async()=>{
 let fail=false;const x=harness(()=>{if(fail){const e=new Error('Denied');e.status=401;throw e;}return {};});
 await x.loop.start();const success=x.loop.state().lastSuccessAt;fail=true;
 x.advance(10000);await flush();assert.match(x.states.at(-1).error,/Authentication required/);assert.equal(x.loop.state().lastSuccessAt,success);
 x.advance(21000);await flush();assert.equal(x.states.at(-1).stale,true);
 fail=false;await x.loop.request();assert.equal(x.states.at(-1).stale,false);assert.equal(x.states.at(-1).error,null);x.loop.stop();
});
test('a rendering exception cannot mark a partial display as successfully refreshed',async()=>{
 const x=harness(()=>({}),()=>{throw new Error('Malformed payload');});await x.loop.start();
 assert.equal(x.loop.state().lastSuccessAt,null);assert.match(x.states.at(-1).error,/Refresh failed/);assert.equal(x.timers.size,1);x.loop.stop();
});
test('stopping the loop aborts pending work and prevents restart from its old finally block',async()=>{
 const x=harness(()=>new Promise(()=>{}));const p=x.loop.start();await flush();x.loop.stop();await p;
 assert.equal(x.timers.size,0);assert.equal(x.loop.state().lastSuccessAt,null);
});
