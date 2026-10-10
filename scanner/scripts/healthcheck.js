try {
  const r=await fetch(`http://127.0.0.1:${process.env.DASHBOARD_PORT||8787}/healthz`,{signal:AbortSignal.timeout(4000)});
  process.exitCode=r.ok?0:1;
}catch{process.exitCode=1;}
