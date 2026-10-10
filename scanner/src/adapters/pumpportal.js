export function startPumpPortal(apiKey,onToken,onStatus=()=>{},health) {
  if(!apiKey){onStatus('PumpPortal disabled: missing API key');return ()=>{};}
  let ws,timer,watchdog,stopped=false,retry=1000,lastMessageAt=0;
  const connect=()=>{
    if(stopped)return;
    try {ws=new WebSocket('wss://pumpportal.fun/api/data');}
    catch {schedule();return;}
    ws.addEventListener('open',()=>{
      retry=1000;lastMessageAt=Date.now();onStatus('PumpPortal connected');health?.success('pumpportal');
      ws.send(JSON.stringify({method:'subscribeNewToken'}));ws.send(JSON.stringify({method:'subscribeMigration'}));
    });
    ws.addEventListener('message',e=>{
      lastMessageAt=Date.now();
      try {
        const row=JSON.parse(String(e.data));
        const errors = [row.error, row.errors].flat().filter(x => x != null && x !== false && x !== '');
        if (errors.length) {
          let reason = JSON.stringify(errors);
          for (const secret of [apiKey, encodeURIComponent(apiKey), JSON.stringify(apiKey).slice(1, -1)]) {
            if (secret) reason = reason.split(secret).join('[REDACTED]');
          }
          reason = reason.replace(/(?:https?|wss?):\/\/[^\s"]+/g, '[URL]').slice(0, 400);
          health?.failure('pumpportal', 'Subscription rejected: ' + reason);
          onStatus('PumpPortal subscription rejected: ' + reason);
          return;
        }
        health?.success('pumpportal');
        if(!row.mint||!['create','migration','migrate'].includes(row.txType))return;
        onToken({mint:row.mint,tokenName:row.name,symbol:row.symbol,creator:row.traderPublicKey||row.creator,
          ...(row.txType==='create'?{launchAt:Date.now()}:{}),discoverySource:`pumpportal:${row.txType}`});
      }catch{onStatus('PumpPortal message rejected');}
    });
    ws.addEventListener('close',()=>{if(stopped)return;health?.failure('pumpportal','Disconnected');onStatus('PumpPortal disconnected; reconnect scheduled');schedule();});
    ws.addEventListener('error',()=>{health?.failure('pumpportal','Connection error');try{ws.close();}catch{}});
  };
  const schedule=()=>{if(stopped)return;clearTimeout(timer);timer=setTimeout(connect,retry+Math.random()*500);retry=Math.min(30000,retry*2);};
  // Silence is observable degradation, not a fabricated application ping protocol.
  watchdog=setInterval(()=>{if(ws?.readyState===1&&Date.now()-lastMessageAt>180000){health?.failure('pumpportal','No messages for 3 minutes');ws.close();}},30000);
  connect();
  return ()=>{stopped=true;clearTimeout(timer);clearInterval(watchdog);try{ws?.close();}catch{}};
}
