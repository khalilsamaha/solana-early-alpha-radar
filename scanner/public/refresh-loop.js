// One current refresh, bounded end-to-end, with superseded responses ignored.
export function createRefreshLoop({load,render,onState,clock=Date.now,timeoutMs=15000,
  intervalMs=10000,staleMs=30000,setTimer=setTimeout,clearTimer=clearTimeout,
  setTicker=setInterval,clearTicker=clearInterval}) {
  let generation=0,controller,retry,ticker,deadline,lastSuccessAt=null,error=null,busy=false,stopped=false;
  const publish=()=>onState({lastSuccessAt,ageMs:lastSuccessAt===null?null:Math.max(0,clock()-lastSuccessAt),
    busy,error,stale:lastSuccessAt===null||clock()-lastSuccessAt>staleMs});
  async function request() {
    if(stopped)return;
    const id=++generation;
    clearTimer(retry);clearTimer(deadline);controller?.abort(new Error('Superseded'));
    controller=new AbortController();const current=controller;
    busy=true;error=null;publish();
    const expired=new Error('Dashboard request timed out');expired.name='TimeoutError';
    deadline=setTimer(()=>current.abort(expired),timeoutMs);
    try {
      const aborted=new Promise((_,reject)=>current.signal.addEventListener('abort',()=>reject(current.signal.reason),{once:true}));
      const result=await Promise.race([Promise.resolve().then(()=>load(current.signal)),aborted]);
      if(id!==generation||stopped)return;
      render(result);lastSuccessAt=clock();error=null;
    } catch(e) {
      if(id!==generation||stopped)return;
      error=e?.status===401?'Authentication required. Enter the dashboard token.':e?.name==='TimeoutError'?'Request timed out; retrying automatically.':'Refresh failed; retrying automatically.';
      current.abort();
    } finally {
      if(id===generation&&!stopped){clearTimer(deadline);busy=false;publish();retry=setTimer(request,intervalMs);}
    }
  }
  return {request,start(){stopped=false;if(ticker===undefined)ticker=setTicker(publish,1000);return request();},
    stop(){stopped=true;generation++;controller?.abort();clearTimer(deadline);clearTimer(retry);clearTicker(ticker);ticker=undefined;},
    state:()=>({lastSuccessAt,busy,error})};
}
