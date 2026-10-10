export function exitRisk(candidate,previous,fresh=true) {
  if(!fresh)return {level:'unknown',reasons:['Fresh same-pair market data unavailable']};
  const reasons=[];
  if(previous?.pairAddress&&previous.pairAddress!==candidate.pairAddress)return {level:'unknown',reasons:['Market pair changed']};
  if(previous?.liquidityUsd>0&&candidate.liquidityUsd/previous.liquidityUsd<0.7)reasons.push('Liquidity fell more than 30% since previous observation');
  const flow=candidate.txns?.m5||{},total=(flow.buys||0)+(flow.sells||0);
  if(total>=15&&flow.sells/total>=0.65)reasons.push('Sell transactions exceed 65% of 5m flow');
  if(candidate.priceChange?.m5<=-20)reasons.push('Price down at least 20% over 5m');
  if(candidate.paperEntry?.peakPrice>0&&candidate.priceUsd/candidate.paperEntry.peakPrice<0.75)reasons.push('Price more than 25% below observed post-alert peak');
  return {level:reasons.length>=2?'high':reasons.length?'moderate':'low',reasons};
}
