// Local health only; no statistics scan, market requests, or notifications.
const port=process.env.DASHBOARD_PORT||8787;
if(!/^\d{1,5}$/.test(port)||+port<1||+port>65535)throw Error('Invalid dashboard port');
try {
 const response=await fetch(`http://127.0.0.1:${port}/api/health`,{
  headers:{Authorization:`Bearer ${process.env.DASHBOARD_TOKEN||''}`},signal:AbortSignal.timeout(15000)});
 if(!response.ok)throw Error('Health unavailable');
 const h=await response.json();
 console.log(JSON.stringify({capturedAt:new Date().toISOString(),ready:h.ready,scannerVersion:h.scannerVersion,
  entryContextVersion:h.entryContextVersion??null,metadataProvenanceVersion:h.metadataProvenanceVersion??null,statisticsReader:h.statisticsReader},null,2));
 if(!h.ready||h.entryContextVersion!=='entry-context-1'||h.metadataProvenanceVersion!=='metadata-provenance-1')process.exitCode=1;
} catch {console.error('Metadata provenance check failed. Check local service and dashboard authentication.');process.exitCode=1;}
