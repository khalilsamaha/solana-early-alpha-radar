// Research measurements use receive timestamps, not claimed exchange timestamps.
// A new pool, a gap, or a restart starts a new warm-up period.
export const MOMENTUM_VERSION='research-0.2.9';
export const MAX_GAP_MS=45000;
export function turnoverPoints(ratio) {
  const knots=[[0,0],[0.12,5],[0.35,9],[4,9],[8,-3],[16,-8]];
  if(!Number.isFinite(ratio)||ratio<=0)return 0;
  for(let i=1;i<knots.length;i++) {
    const [x,y]=knots[i], [px,py]=knots[i-1];
    if(ratio<=x)return py+(y-py)*(ratio-px)/(x-px);
  }
  return -8;
}
export class MomentumHistory {
  constructor(){this.rows=[];this.pair=null;this.lastChangedAt=null;this.signature=null;this.resetReason='startup';}
  observe(c,at) {
    if(!Number.isFinite(at)||!Number.isFinite(c.priceUsd)||c.priceUsd<=0||!c.pairAddress)return this.describe(at);
    if(this.rows.length&&at<=this.rows.at(-1).at)return this.describe(at);
    const gap=this.rows.length&&at-this.rows.at(-1).at>MAX_GAP_MS;
    if(c.pairAddress!==this.pair||gap) {
      this.resetReason=this.pair!==null&&c.pairAddress!==this.pair?'pool changed':gap?'observation gap':'startup';
      this.rows=[];this.signature=null;this.lastChangedAt=null;this.pair=c.pairAddress;
    }
    const p={at,price:c.priceUsd,volume:c.volume?.m5,buys:c.txns?.m5?.buys,sells:c.txns?.m5?.sells,liquidity:c.liquidityUsd};
    const signature=JSON.stringify([p.price,p.volume,p.buys,p.sells,p.liquidity]);
    p.changed=signature!==this.signature;
    if(p.changed)this.lastChangedAt=at;
    this.signature=signature;this.rows.push(p);
    this.rows=this.rows.filter(p=>at-p.at<=360000).slice(-256);
    return this.describe(at);
  }
  describe(now) {
    const end=this.rows.at(-1);
    const fresh=Boolean(end&&now-end.at<=MAX_GAP_MS);
    const window=ms=>{
      if(!fresh)return null;
      const start=this.rows.findLast(p=>p.at<=end.at-ms);
      if(!start||end.at-start.at>ms+MAX_GAP_MS)return null;
      const subset=this.rows.filter(p=>p.at>=start.at),span=end.at-start.at;
      if(subset.length<3)return null;
      return {spanMs:span,samples:subset.length,changedSamples:subset.filter(p=>p.changed).length,
        returnPct:(end.price/start.price-1)*100,
        volumeDeltaPerMinute:Number.isFinite(end.volume)&&Number.isFinite(start.volume)?(end.volume-start.volume)/(span/60000):null,
        transactionsDeltaPerMinute:[end.buys,end.sells,start.buys,start.sells].every(Number.isFinite)?(end.buys+end.sells-start.buys-start.sells)/(span/60000):null,
        liquidityChangePct:end.liquidity>=0&&start.liquidity>0?(end.liquidity/start.liquidity-1)*100:null};
    };
    const peak=end?Math.max(...this.rows.filter(p=>end.at-p.at<=300000).map(p=>p.price)):null;
    return {version:MOMENTUM_VERSION,at:end?.at??null,pairAddress:this.pair,ready:fresh&&Boolean(window(60000)),
      resetReason:this.resetReason,sampleCount:this.rows.length,lastChangedAt:this.lastChangedAt,
      unchangedForMs:end?Math.max(0,now-this.lastChangedAt):null,receiveAgeMs:end?Math.max(0,now-end.at):null,
      r30:window(30000),r60:window(60000),r120:window(120000),
      lastIntervalReturnPct:fresh&&this.rows.length>=2?(end.price/this.rows.at(-2).price-1)*100:null,
      drawdownPct:peak?(end.price/peak-1)*100:null};
  }
}
