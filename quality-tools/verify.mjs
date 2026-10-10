const base=`http://127.0.0.1:${process.env.DASHBOARD_PORT||8787}`;
const headers={Authorization:`Bearer ${process.env.DASHBOARD_TOKEN||''}`};
try{
 const get=async path=>{const r=await fetch(base+path,{headers,signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error(`HTTP ${r.status}`);return r.json();};
 const [health,rows]=await Promise.all([get('/api/health'),get('/api/candidates?limit=1000')]);
 if(health.research?.observationQualityVersion!=='observation-quality-1')throw Error('Research quality update is not active');
 console.log(JSON.stringify({capturedAt:new Date().toISOString(),ready:health.ready,scannerVersion:health.scannerVersion,
 research:health.research,candidates:rows.length,withObservationQuality:rows.filter(r=>r.research?.observationQuality).length,
 qualityStates:rows.reduce((a,r)=>{const k=r.research?.observationQuality?.state||'not initialized';a[k]=(a[k]||0)+1;return a;},{})},null,2));
}catch(e){console.error('Verification failed: '+(String(e.message).startsWith('HTTP')?e.message:'update inactive or local dashboard unavailable'));process.exitCode=1;}
