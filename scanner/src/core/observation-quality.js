// Describes received observations, never exchange freshness or executable depth.
export const OBSERVATION_QUALITY_VERSION='observation-quality-1';
export function observationQuality(history,now) {
 const rows=history.rows||[],last=rows.at(-1);
 if(!last)return {version:OBSERVATION_QUALITY_VERSION,state:'no observations',responseAgeMs:null,underlyingFreshness:'unknown'};
 const age=now-last.at,valid=age>=0&&age<=45000;
 let lastPriceChangeAt=null,lastValuesChangeAt=null,priceRepeats=0,valueRepeats=0;
 for(let i=1;i<rows.length;i++){
  if(rows[i].price!==rows[i-1].price){lastPriceChangeAt=rows[i].at;priceRepeats=0;}else priceRepeats++;
  if(rows[i].changed){lastValuesChangeAt=rows[i].at;valueRepeats=0;}else valueRepeats++;
 }
 return {version:OBSERVATION_QUALITY_VERSION,state:!valid?'response stale or invalid':rows.length<2?'first observation':last.changed?'reported values changed':'reported values repeated',
  responseAgeMs:age>=0?age:null,responseRecent:valid,underlyingFreshness:'unknown',
  lastObservedAt:last.at,lastValuesChangeAt,lastPriceChangeAt,
  valuesUnchangedForAtLeastMs:now-(lastValuesChangeAt??rows[0].at),priceUnchangedForAtLeastMs:now-(lastPriceChangeAt??rows[0].at),
  consecutiveRepeatedValues:valueRepeats,consecutiveRepeatedPrices:priceRepeats,
  historySpanMs:last.at-rows[0].at,historyResetReason:history.resetReason,sampleCount:rows.length,
  note:'Receipt age and repeated values are observational. Neither proves exchange freshness.'};
}
