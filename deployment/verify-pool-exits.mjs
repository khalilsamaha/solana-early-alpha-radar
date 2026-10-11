const base=`http://127.0.0.1:${process.env.DASHBOARD_PORT||8787}`;
try {
 const response=await fetch(`${base}/api/health`,{headers:{Authorization:`Bearer ${process.env.DASHBOARD_TOKEN||''}`},signal:AbortSignal.timeout(15000)});
 if(!response.ok)throw Error();const h=await response.json(),f=h.research?.fastShadow;
 if(f?.pathEvidenceVersion!=='pool-timing-evidence-1')throw Error();
 console.log(JSON.stringify({capturedAt:new Date().toISOString(),ready:h.ready,scannerVersion:h.scannerVersion,
  pathEvidenceVersion:f.pathEvidenceVersion,fixedExitProtocol:f.fixedExitProtocol,fixedExitRegisteredAt:f.fixedExitRegisteredAt,
  pending:f.pending,trackingActive:f.trackingActive,trackingLimit:f.trackingLimit,
  note:f.fixedExitRegisteredAt?'Fixed exit comparison registered.':'Registration starts with the first newly admitted Fast30 entry.'},null,2));
 if(!h.ready)process.exitCode=1;
} catch {console.error('Verification failed: local dashboard unavailable, authentication failed, or pool evidence update inactive.');process.exitCode=1;}
