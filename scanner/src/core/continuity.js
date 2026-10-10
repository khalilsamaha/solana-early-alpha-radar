// Alternate-pool prices are research evidence, never verified migrations or fills.
export const CONTINUITY_VERSION='token-followup-1';
const MAX_GAP=45000,MIN_SPAN=15000;
export function observeContinuity(p,c,now,valid) {
  if(!c)return null;
  if(!valid||c?.mint!==p.mint||!c.pairAddress||!Number.isFinite(c.priceUsd)||c.priceUsd<=0
    ||!Number.isFinite(c.marketObservedAt)||now-c.marketObservedAt<0||now-c.marketObservedAt>MAX_GAP) {
    p.alternateConfirmation=null;return null;
  }
  const at=c.marketObservedAt;
  if(c.pairAddress===p.pairAddress) {
    p.alternateConfirmation=null;
    return {status:'observed',basis:'original-pool',sampleAt:at,pairAddress:c.pairAddress,
      priceUsd:c.priceUsd,returnPct:(c.priceUsd/p.priceUsd-1)*100};
  }
  const buys=c.txns?.m5?.buys,sells=c.txns?.m5?.sells;
  if(!(Number.isFinite(c.liquidityUsd)&&c.liquidityUsd>=5000)
    ||!Number.isFinite(buys)||!Number.isFinite(sells)||buys<0||sells<0||buys+sells<15) {
    p.alternateConfirmation=null;return null;
  }
  const signature=JSON.stringify([c.priceUsd,c.volume?.m5,buys,sells,c.liquidityUsd]);
  let state=p.alternateConfirmation;
  if(!state||state.pairAddress!==c.pairAddress||at-state.lastAt>MAX_GAP||at<state.lastAt) {
    state={pairAddress:c.pairAddress,firstAt:at,lastAt:at,samples:1,signature,lastChangeAt:null};
  } else if(at>state.lastAt) {
    state.samples++;if(signature!==state.signature)state.lastChangeAt=at;
    state.lastAt=at;state.signature=signature;
  }
  p.alternateConfirmation=state;
  if(state.samples<2||at-state.firstAt<MIN_SPAN||state.lastChangeAt===null||at-state.lastChangeAt>MAX_GAP)return null;
  return {status:'observed',basis:'alternate-pool',sampleAt:at,pairAddress:c.pairAddress,quoteMint:c.quoteMint||null,
    priceUsd:c.priceUsd,returnPct:(c.priceUsd/p.priceUsd-1)*100,
    evidence:{confirmedSince:state.firstAt,samples:state.samples,lastChangeAt:state.lastChangeAt,
      liquidityUsd:c.liquidityUsd,transactions5m:buys+sells},
    migrationVerified:false,executionVerified:false};
}
export function summarizeContinuity(entries,outcomes,horizons,now,tolerance) {
  const indexed=new Map(outcomes.map(o=>[`${o.entryId}:${o.horizon}`,o]));
  return Object.fromEntries(['baseline','early-activity'].map(cohort=>{
    const rows=entries.filter(e=>e.cohort===cohort);
    return [cohort,{entries:rows.length,horizons:Object.fromEntries(Object.entries(horizons).map(([h,ms])=>{
      const values=[];let originalPool=0,alternatePool=0,missing=0,gapped=0,pending=0,overdue=0,unavailable=0;
      for(const e of rows) {
        const o=indexed.get(`${e.id}:${h}`);
        if(!o){if(now<=e.at+ms+tolerance)pending++;else overdue++;continue;}
        const f=o.tokenFollowup;
        if(!f){unavailable++;continue;}
        if(f.status!=='observed'||!Number.isFinite(f.returnPct)){missing++;continue;}
        if(f.coverage==='gapped'){gapped++;continue;}
        if(f.basis==='alternate-pool')alternatePool++;else originalPool++;
        values.push(f.returnPct);
      }
      values.sort((a,b)=>a-b);const n=values.length;
      return [h,{observed:n,originalPool,alternatePool,missing,gapped,pending,overdue,unavailable,
        aboveEntry:values.filter(x=>x>0).length,medianReturnPct:n?(values[Math.floor((n-1)/2)]+values[Math.floor(n/2)])/2:null}];
    }))}];
  }));
}
