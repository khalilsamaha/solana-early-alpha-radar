// Local authenticated health and bounded current candidate projection only.
const base=`http://127.0.0.1:${process.env.DASHBOARD_PORT||8787}`;
const headers={Authorization:`Bearer ${process.env.DASHBOARD_TOKEN||''}`};
async function read(path){const r=await fetch(base+path,{headers,signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error(`HTTP ${r.status}`);return r.json();}
const health=await read('/api/health'),rows=await read('/api/candidates?limit=1000');
const valid=rows.filter(c=>c.feedEvidence?.version==='feed-provenance-1');
console.log(JSON.stringify({capturedAt:new Date().toISOString(),ready:health.ready,scannerVersion:health.scannerVersion,
 feedEvidenceVersion:health.feedEvidenceVersion,candidates:rows.length,withFeedEvidence:valid.length,
 examples:valid.slice(0,3).map(c=>({mint:c.mint,marketObservedAt:c.marketObservedAt,feedEvidence:c.feedEvidence}))},null,2));
if(!health.ready||health.feedEvidenceVersion!=='feed-provenance-1')process.exitCode=1;
