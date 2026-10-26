import test from 'node:test';
import assert from 'node:assert/strict';
import {observe} from './verify-statistics-compact.mjs';
function run({changing=true,ready=200,version='stats-compact-worker-1.0.0',ageMs=1}={}){
 let now=0;const read=async route=>({status:route==='/readyz'?ready:200,elapsedMs:1,body:{privateToken:'never-export',statisticsWorker:{version,ageMs,snapshotAt:1,lastError:'secret failure'},statistics:{version,ageMs,snapshotAt:changing?now+1:1},outcomes:['never-export']}});
 return observe({read,now:()=>now,sleep:async()=>{now+=5000;},budgetMs:15000});
}
test('acceptance requires two distinct current snapshots and exports only diagnostic fields',async()=>{
 const r=await run();assert.equal(r.state,'passed');assert.equal(r.samples.length,2);assert.equal(r.distinctServedSnapshots,2);
 assert.equal(r.samples[0].statistics.lastError,'unclassified');assert.ok(!JSON.stringify(r).includes('never-export'));assert.ok(!JSON.stringify(r).includes('secret failure'));
});
test('unchanged snapshots, wrong version, expired results or readiness failures cannot pass',async()=>{
 for(const options of [{changing:false},{version:'old'},{ready:503},{ageMs:120001}])assert.equal((await run(options)).state,'needs-review');
});
