export const HORIZONS={'5m':300000,'15m':900000,'60m':3600000};
export function createEntry(candidate,now) {
  return {at:now,score:candidate.score,priceUsd:candidate.priceUsd,marketCap:candidate.marketCap,
    pairAddress:candidate.pairAddress,version:'price-v2',horizons:{},lastAt:now,maxGapMs:0,
    peakPrice:candidate.priceUsd,troughPrice:candidate.priceUsd,maxDrawdownPct:0,
    windows:Object.fromEntries(Object.keys(HORIZONS).map(k=>[k,{maxPrice:candidate.priceUsd,minPrice:candidate.priceUsd}]))};
}
export function updatePaper(candidate,now,toleranceMs,fresh) {
  const p=candidate.paperEntry;
  if(!p||p.legacy||p.version!=='price-v2')return [];
  const rows=[];
  const valid=fresh&&Number.isFinite(candidate.priceUsd)&&candidate.priceUsd>0&&candidate.pairAddress===p.pairAddress;
  if(valid) {
    p.maxGapMs=Math.max(p.maxGapMs,now-p.lastAt);p.lastAt=now;
    p.peakPrice=Math.max(p.peakPrice,candidate.priceUsd);p.troughPrice=Math.min(p.troughPrice,candidate.priceUsd);
    p.currentMultiple=candidate.priceUsd/p.priceUsd;p.maxMultiple=p.peakPrice/p.priceUsd;
    p.maxDrawdownPct=Math.min(p.maxDrawdownPct,(candidate.priceUsd/p.peakPrice-1)*100);
  }
  for(const [label,ms] of Object.entries(HORIZONS)) {
    if(p.horizons[label])continue;
    const due=p.at+ms,w=p.windows[label];
    if(valid&&now<=due){w.maxPrice=Math.max(w.maxPrice,candidate.priceUsd);w.minPrice=Math.min(w.minPrice,candidate.priceUsd);}
    if(now<due)continue;
    if(valid&&now<=due+toleranceMs) {
      p.horizons[label]={status:'observed',at:now,dueAt:due,lagMs:now-due,priceUsd:candidate.priceUsd,
        multiple:candidate.priceUsd/p.priceUsd,maxMultiple:w.maxPrice/p.priceUsd,
        drawdownFromEntryPct:(w.minPrice/p.priceUsd-1)*100,maxGapMs:p.maxGapMs,
        coverage:p.maxGapMs<=toleranceMs?'sampled':'gapped'};
    } else if(now>due+toleranceMs) p.horizons[label]={status:'missing',at:now,dueAt:due,reason:'No same-pair fresh observation in checkpoint window'};
    else continue;
    rows.push({mint:candidate.mint,symbol:candidate.symbol,alertAt:p.at,horizon:label,score:p.score,entryMarketCap:p.marketCap,version:p.version,...p.horizons[label]});
  }
  return rows;
}
export function tracking(candidate) {const p=candidate.paperEntry;return p?.version==='price-v2'&&!p.horizons?.['60m'];}
