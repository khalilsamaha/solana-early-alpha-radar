const median=values=>{if(!values.length)return null;values.sort((a,b)=>a-b);const i=Math.floor(values.length/2);return values.length%2?values[i]:(values[i-1]+values[i])/2;};
const key=(mint,at)=>`${mint}:${at}`;
export function summarizeOutcomes(entries,outcomes,now=Date.now(),toleranceMs=120000) {
  const indexed=new Map(entries.map(a=>[key(a.candidate.mint,Number(a.id.split(':')[1])),a]));
  const rows=new Map();
  for(const o of outcomes)if(o.version==='price-v2'&&indexed.has(key(o.mint,o.alertAt)))rows.set(`${key(o.mint,o.alertAt)}:${o.horizon}`,o);
  const horizons={};
  for(const [h,ms] of Object.entries({'5m':300000,'15m':900000,'60m':3600000})) {
    let missing=0,pending=0,overdue=0,invalid=0;const valid=[];
    for(const [id,a] of indexed) {
      const o=rows.get(`${id}:${h}`),at=Number(a.id.split(':')[1]);
      if(!o){if(now>at+ms+toleranceMs)overdue++;else pending++;}
      else if(o.status==='missing')missing++;
      else if(o.status==='observed'&&Number.isFinite(o.multiple)&&o.multiple>0)valid.push(o);
      else invalid++;
    }
    const observed=valid.length,aboveEntry=valid.filter(o=>o.multiple>1).length,loss50=valid.filter(o=>o.multiple<=.5).length;
    horizons[h]={observed,missing,pending,overdue,invalid,gapped:valid.filter(o=>o.coverage==='gapped').length,
      aboveEntry,aboveEntryPct:observed?aboveEntry/observed*100:null,loss50,
      loss50Pct:observed?loss50/observed*100:null,medianReturnPct:median(valid.map(o=>(o.multiple-1)*100)),
      sampledPeak2x:valid.filter(o=>o.maxMultiple>=2).length,checkpoint2x:valid.filter(o=>o.multiple>=2).length};
  }
  const dates=entries.map(a=>Number(a.id.split(':')[1]));
  return {entries:indexed.size,firstEntryAt:dates.length?Math.min(...dates):null,lastEntryAt:dates.length?Math.max(...dates):null,horizons};
}
