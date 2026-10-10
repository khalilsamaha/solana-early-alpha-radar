// Observation-only diagnostics: never used to change eligibility or scheduling.
export const TRACE_VERSION='0.2.4';
export function liquidityState(c) {
  const value=c.liquidityUsd;
  return !Number.isFinite(value)||value<0?'unknown':value<5000?'low':'reported';
}
export function ensureTimeline(c,now=Date.now()) {
  c.decisionTimeline||={version:TRACE_VERSION,startedAt:now,firstSeenAt:c.firstSeenAt||null,
    priorHistoryUnavailable:(c.firstSeenAt||0)<now};
  return c.decisionTimeline;
}
export function completeSecurity(c) {
  return c.mintAuthority!==undefined&&c.freezeAuthority!==undefined&&Number.isFinite(c.top10Pct);
}
export function describeDecision(c,config,now=Date.now()) {
  const marketFresh=!c.stale&&c.marketObservedAt>0&&now-c.marketObservedAt<=config.freshMs;
  const securityFresh=Number.isFinite(c.securityCheckedAt)&&now-c.securityCheckedAt<=config.securityTtlMs;
  const securityComplete=securityFresh&&completeSecurity(c);
  const liquidity=liquidityState(c),reasons=[];
  const times=[c.launchAt,c.firstPoolAt,c.pairCreatedAt].filter(x=>x>0);
  const tooOld=now-(times.length?Math.min(...times):c.firstSeenAt)>config.maxCandidateAgeMin*60000;
  const level=c.score>=config.strongAlertScore?2:1;
  const alreadyAlerted=(c.alertLevel||0)>=level;
  if(tooOld)reasons.push('Outside configured launch window');
  if(!marketFresh)reasons.push('Fresh usable market data unavailable');
  if(liquidity==='unknown')reasons.push('Liquidity unknown; conservative score cap retained');
  else if(liquidity==='low')reasons.push('Reported liquidity below $5,000');
  if(!securityComplete)reasons.push(securityFresh?'Security fields incomplete':'Security check missing or expired');
  if(securityFresh&&c.mintAuthority)reasons.push('Active mint authority; score cap applies');
  if(securityFresh&&c.freezeAuthority)reasons.push('Active freeze authority; score cap applies');
  if(securityFresh&&c.top10Pct>50)reasons.push('Top-10 token accounts above 50%; score cap applies');
  if(c.auditIsSus===true)reasons.push('Provider marks token suspicious; score cap applies');
  if((c.score||0)<config.alertScore)reasons.push(`Score ${c.score||0} below ${config.alertScore}`);
  // Eligibility mirrors the actual alert guards; explanatory risk flags can coexist.
  const eligible=!tooOld&&marketFresh&&c.priceUsd>0&&c.score>=config.alertScore&&(!config.requireSecurity||securityFresh);
  const paper=c.paperEntry?.version==='price-v2'&&!c.paperEntry.horizons?.['60m'];
  let metadataReason='Eligible for metadata queue';
  if(c.inactive&&!paper)metadataReason='Inactive candidate';
  else if(!marketFresh)metadataReason='Waiting for fresh market data';
  else if(!paper&&liquidity==='unknown')metadataReason='Waiting for reported liquidity ≥$5,000';
  else if(!paper&&c.liquidityUsd<5000)metadataReason='Waiting for liquidity ≥$5,000';
  else if(!paper&&(c.txns?.m5?.buys||0)+(c.txns?.m5?.sells||0)<15)metadataReason='Waiting for ≥15 transactions in 5m';
  const status=eligible?(alreadyAlerted?'already-alerted':'eligible'):'blocked';
  return {at:now,score:c.score||0,status,liquidity,marketFresh,securityFresh,securityComplete,
    reasons,metadataReason,requiredScore:config.alertScore,nextLevel:level};
}
export function recordDecision(storage,c,config,now=Date.now(),source='market') {
  const t=ensureTimeline(c,now),d=describeDecision(c,config,now),milestones=[];
  const mark=(name,yes)=>{if(yes&&!t[name]){t[name]=now;milestones.push(name);}};
  mark('firstAttemptAt',source==='market');
  mark('firstMarketAt',d.marketFresh);
  mark('firstLiquidityKnownAt',d.marketFresh&&d.liquidity!=='unknown');
  mark('firstLiquidityEligibleAt',d.marketFresh&&c.liquidityUsd>=5000);
  mark('firstMetadataEligibleAt',d.metadataReason==='Eligible for metadata queue');
  mark('firstSecurityCompleteAt',d.securityComplete);
  mark('firstThresholdAt',source==='market'&&d.marketFresh&&c.score>=config.alertScore);
  mark('firstAlertEligibleAt',source==='market'&&d.status==='eligible');
  c.decision=d;
  // Numeric score fluctuations alone do not generate extra events. State changes
  // are coalesced to one per minute; first milestones and alerts remain immediate.
  const signature=JSON.stringify([d.status,d.liquidity,d.marketFresh,d.securityComplete,
    d.metadataReason,c.score>=config.alertScore,c.pairAddress,c.inactive]);
  if(!c.lastDecisionAt||milestones.length||source==='alert'||(signature!==c.lastDecisionSignature&&now-c.lastDecisionAt>=60000)) {
    storage.append('decisions',{mint:c.mint,at:now,version:TRACE_VERSION,source,pairAddress:c.pairAddress,
      ...d,milestones,timeline:{...t},scoreRisks:c.scoreRisks||[],
      securityCheckedAt:c.securityCheckedAt||null,marketObservedAt:c.marketObservedAt||null});
    c.lastDecisionAt=now;c.lastDecisionSignature=signature;
    storage.decisionEventsWritten=(storage.decisionEventsWritten||0)+1;
  }
  return d;
}
