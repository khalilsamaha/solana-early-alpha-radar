export class Health {
  constructor(config,clock=Date.now) {
    this.clock=clock;this.startedAt=clock();this.lastLoopAt=0;this.lastMarketAt=0;this.mode='starting';
    this.providers=Object.fromEntries(['dex','jupiter','helius','pumpportal'].map(name=>[name,{
      enabled:name==='dex'||Boolean(config[`${name==='pumpportal'?'pumpPortal':name}ApiKey`]),lastSuccessAt:null,lastErrorAt:null,failures:0,requests:0
    }]));
  }
  success(name,latencyMs=0) { const p=this.providers[name]; if(!p)return;Object.assign(p,{lastSuccessAt:this.clock(),failures:0,lastError:null,latencyMs,requests:p.requests+1}); }
  failure(name,message) { const p=this.providers[name]; if(!p)return;Object.assign(p,{lastErrorAt:this.clock(),failures:p.failures+1,lastError:String(message).slice(0,160)}); }
  snapshot(config,notifications={}) {
    const now=this.clock();
    const providers=Object.fromEntries(Object.entries(this.providers).map(([name,p])=>[name,{...p,state:!p.enabled?'disabled':p.failures?'error':!p.lastSuccessAt?'waiting':now-p.lastSuccessAt>Math.max(180000,config.securityTtlMs*2)?'stale':'ok'}]));
    const ready=this.mode==='live' && now-this.lastLoopAt<180000 && this.lastMarketAt>0 && now-this.lastMarketAt<config.freshMs;
    return {ready,mode:this.mode,uptimeSeconds:Math.floor((now-this.startedAt)/1000),lastLoopAt:this.lastLoopAt,lastMarketAt:this.lastMarketAt,providers,notifications};
  }
}
