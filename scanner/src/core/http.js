import {transportEvidence} from './feed-evidence.js';
const wait = ms => new Promise(r=>setTimeout(r,ms));
export class HttpClient {
  constructor(config, health) {
    this.health=health; this.lanes=new Map(); this.next=new Map(); this.backoff=new Map();
    this.rpm={dex:config.dexRpm,jupiter:config.jupiterRpm,helius:config.heliusRpm};
  }
  async json(provider,url,options={},recordEvidence=null) {
    const queuedAt=Date.now();
    const previous=this.lanes.get(provider)||Promise.resolve();
    let release;
    const turn=new Promise(r=>{release=r;}); this.lanes.set(provider,turn);
    await previous;
    try {
      if((this.backoff.get(provider)||0)>Date.now()) throw new Error(`${provider} cooling down after rate limit`);
      await wait(Math.max(0,(this.next.get(provider)||0)-Date.now()));
      this.next.set(provider,Date.now()+60000/this.rpm[provider]);
      const start=Date.now();
      const response=await fetch(url,{...options,signal:AbortSignal.timeout(10000)});
      const headersAt=Date.now();
      if(response.status===429) {
        const raw=response.headers.get('retry-after');
        const seconds=Number(raw);
        const delay=raw && Number.isFinite(seconds)?seconds*1000:Math.max(0,Date.parse(raw)-Date.now())||60000;
        this.backoff.set(provider,Date.now()+Math.min(3600000,Math.max(1000,delay)));
      }
      if(!response.ok)throw new Error(`${provider} HTTP ${response.status}`);
      const body=await response.json();
      if(body?.error)throw new Error(`${provider} returned RPC error`);
      const bodyAt=Date.now();
      if(recordEvidence) {try {recordEvidence(transportEvidence(response,queuedAt,start,headersAt,bodyAt));} catch {} }
      this.health.success(provider,Date.now()-start);
      return body;
    } catch(error) { this.health.failure(provider,error.message); throw error; }
    finally {release();}
  }
}
