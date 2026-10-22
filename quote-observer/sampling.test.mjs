import test from 'node:test';
import assert from 'node:assert/strict';
import {samplingDecision,samplingCapacity,admission} from './observer.mjs';
const now=1800000000000,early={cohort:'early-activity',signalAt:now},baseline={cohort:'baseline',signalAt:now};
test('early cohort cannot borrow baseline hourly capacity',()=>{
 const recent=[1,21,41].map(m=>({cohort:'early-activity',at:now-m*60000}));
 assert.equal(samplingDecision(early,now,recent),'cohort-hour-budget');
 assert.equal(samplingDecision(baseline,now,recent),'admitted');
});
test('each cohort has its own thirty-minute spacing boundary',()=>{
 const recent=[{cohort:'early-activity',at:now-1800000+1}];
 assert.equal(samplingDecision(early,now,recent),'cohort-spacing');
 assert.equal(samplingDecision(baseline,now,recent),'admitted');
 assert.equal(samplingDecision({...early,signalAt:now+1},now+1,recent),'admitted');
});
test('hour and day caps count legacy admissions and do not reset at UTC boundaries',()=>{
 const hour=[20,59].map(m=>({at:now-m*60000,cohort:'baseline'}));
 assert.equal(samplingDecision(baseline,now,hour),'cohort-hour-budget');
 assert.equal(samplingCapacity(baseline,now+60000,hour).hourUsed,1);
 assert.equal(samplingDecision(baseline,now+60000,hour),'cohort-spacing');
 const day=Array.from({length:48},(_,i)=>({at:now-7200000-i,cohort:'baseline'}));
 assert.equal(samplingDecision(baseline,now,day),'cohort-day-budget');
 assert.equal(samplingDecision(early,now,day),'admitted');
});
test('capacity does not queue expired signals or bypass global limits',()=>{
 assert.equal(admission({...baseline,signalAt:now-15001},{now,busy:false}),'stale-signal');
 assert.equal(admission(baseline,{now,busy:false,recent:Array(6).fill(now-1)}),'hour-budget');
 assert.equal(admission(baseline,{now,busy:true}),'observer-busy');
 assert.equal(samplingCapacity(early,now,[]).hourUsed,0);
});
test('sustained arrivals obey both cohort and global rolling quotas',()=>{
 const recent=[];
 for(let t=now;t<now+86400000;t+=7000){
  for(const cohort of ['early-activity','baseline','fast30-shadow']){
   const s={cohort,signalAt:t};
   if(admission(s,{now:t,busy:false,recent:recent.map(r=>r.at)})==='admitted'&&samplingDecision(s,t,recent)==='admitted')recent.push({at:t,cohort});
  }
  assert.ok(recent.filter(r=>r.at>t-3600000).length<=6);
  for(const c of ['baseline','early-activity','fast30-shadow'])assert.ok(recent.filter(r=>r.cohort===c&&r.at>t-3600000).length<=2);
 }
 assert.equal(recent.length,144);
 assert.equal(recent.filter(r=>r.cohort==='baseline').length,48);
});
