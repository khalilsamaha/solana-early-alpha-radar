// Bounded authenticated local checks; no external provider requests or notifications.
const base=`http://127.0.0.1:${process.env.DASHBOARD_PORT||8787}`;
const headers={Authorization:`Bearer ${process.env.DASHBOARD_TOKEN||''}`};
const ready=await fetch(`${base}/readyz`,{signal:AbortSignal.timeout(15000)});
const response=await fetch(`${base}/api/health`,{headers,signal:AbortSignal.timeout(15000)});
if(!response.ok)throw Error(`Health HTTP ${response.status}`);
const health=await response.json();
console.log(JSON.stringify({capturedAt:new Date().toISOString(),ready:ready.ok,scannerVersion:health.scannerVersion,
  launchRegistry:health.launchRegistry,pathEvidenceVersion:health.research?.fastShadow?.pathEvidenceVersion,
  statisticsWorker:health.statisticsWorker},null,2));
if(!ready.ok||health.launchRegistry?.version!=='launch-registry-1'||health.research?.fastShadow?.pathEvidenceVersion!=='pool-timing-evidence-1')process.exitCode=1;
