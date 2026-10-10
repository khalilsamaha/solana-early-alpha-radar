import {observationQuality} from './observation-quality.js';
export const FAST_VERSION='fast30-shadow-1';
export const FOLLOWUP_POLICY='fast-followup-1';
export const EVIDENCE_VERSION='fast-evidence-1';
export const SHADOW_RULES=Object.freeze([
 {id:'known-liquidity-5000-v1',field:'liquidityUsd',operator:'gte',threshold:5000},
 {id:'return30-at-most-50-v1',field:'return30sPct',operator:'lte',threshold:50}
]);
export function evaluateEntryShadows(features){return Object.fromEntries(SHADOW_RULES.map(r=>{
 const v=features[r.field];return [r.id,!Number.isFinite(v)?'unknown':(r.operator==='gte'?v>=r.threshold:v<=r.threshold)?'selected':'excluded'];
}));}
function attemptEvidence(p,c,now,valid){
 const d=p.diagnostics||=( {version:EVIDENCE_VERSION,startedAt:now,partialHistory:now>p.at,windows:{},lastAttempt:null} );
 if(!c)return;
 const state=c.marketAttemptStatus==='error'?'provider-error':c.marketAttemptStatus==='no-usable-market'?'no-usable-market'
  :valid&&c.pairAddress!==p.pairAddress?'different-pool':valid&&Number.isFinite(c.priceUsd)&&c.priceUsd>0&&c.marketObservedAt<=now?'same-pool':'stale-or-invalid';
 d.lastAttempt={at:now,state,pairAddress:typeof c.pairAddress==='string'?c.pairAddress:null,
  sampleAt:Number.isFinite(c.marketObservedAt)?c.marketObservedAt:null};
 for(const [h,ms] of Object.entries(FAST_RULE.horizons)){
  if(p.horizons[h]||now<p.at+ms||now>p.at+ms+FAST_RULE.toleranceMs)continue;
  const w=d.windows[h]||={attempts:0,counts:{},lastAttempt:null};w.attempts++;w.counts[state]=(w.counts[state]||0)+1;w.lastAttempt={...d.lastAttempt};
 }
}
function diagnosticOutcome(p,h,now,reason,observed){
 const d=p.diagnostics,w=d.windows[h]||{attempts:0,counts:{},lastAttempt:null};
 const code=observed?null:reason?'candidate-left-queue':p.restartObserved?'restart-interrupted'
  :d.partialHistory?'partial-diagnostic-history':!w.attempts?'no-attempt-in-checkpoint-window'
  :Object.keys(w.counts).length===1&&w.lastAttempt.state!=='same-pool'?w.lastAttempt.state:'no-timely-original-pool-observation';
 return {reasonCode:code,diagnostics:{version:EVIDENCE_VERSION,startedAt:d.startedAt,partialHistory:d.partialHistory,
  restartObserved:Boolean(p.restartObserved),dueAt:p.at+FAST_RULE.horizons[h],deadlineAt:p.at+FAST_RULE.horizons[h]+FAST_RULE.toleranceMs,
  finalizedAt:now,lastOriginalPoolAt:p.lastAt,lastAttempt:d.lastAttempt,window:{...w},
  note:'Recorded attempts explain available evidence; no-attempt does not establish scheduler root cause. Different pool does not prove migration.'}};
}
export const FAST_RULE=Object.freeze({id:FAST_VERSION,windowMs:30000,maxWindowSpanMs:45000,minReturnPct:10,minTransactions5m:35,
 minKnownLiquidityUsd:5000,unknownLiquidityVenue:'pumpfun',minRollingVolumeDeltaPerMinute:1000,minRollingTransactionsDeltaPerMinute:8,
 minChangedTransitions:2,cooldownMs:21600000,horizons:{'30s':30000,'60s':60000,'120s':120000,'300s':300000},toleranceMs:30000,
 maxResponseAgeMs:45000,notifications:false,changesScheduling:true});
export function fastDecision(c,history,metrics,now,severe=false,hadDeterioration=false){
 const flow=metrics.r30,quality=observationQuality(history,now),rows=history.rows;
 const anchor=flow?rows.at(-1).at-flow.spanMs:null;
 const transitions=flow?rows.filter(r=>r.at>anchor&&r.changed).length:0;
 const tx=(c.txns?.m5?.buys||0)+(c.txns?.m5?.sells||0);const reasons=[];
 if(!quality.responseRecent)reasons.push('response unavailable');
 if(!flow||flow.spanMs>FAST_RULE.maxWindowSpanMs)reasons.push('30-second history unavailable');
 if(transitions<2)reasons.push('fewer than two changed transitions');
 if(!(flow?.returnPct>=10))reasons.push('30-second increase below 10%');
 if(!(metrics.lastIntervalReturnPct>0))reasons.push('latest price interval not rising');
 if(!(flow?.volumeDeltaPerMinute>1000||flow?.transactionsDeltaPerMinute>8))reasons.push('rolling activity threshold not met');
 if(tx<35)reasons.push('transaction threshold not met');
 if(!(c.liquidityUsd>=5000||(!Number.isFinite(c.liquidityUsd)&&c.dexId==='pumpfun')))reasons.push('liquidity condition not met');
 if(c.inactive||severe||hadDeterioration||metrics.drawdownPct<=-15||flow?.liquidityChangePct<=-30)reasons.push('inactive or adverse observations');
 return {version:FAST_VERSION,eligible:reasons.length===0,reasons,quality,return30sPct:flow?.returnPct??null,
  lastIntervalReturnPct:metrics.lastIntervalReturnPct??null,changedTransitions:transitions,
  note:'Experimental observation; unknown security or liquidity remains unknown.'};
}
export class FastShadow {
 constructor(config,storage){this.config=config;this.storage=storage;this.states=new Map();this.entries=0;this.outcomes=0;this.links=0;this.registration=null;this.evidenceRegistration=null;this.trackingAdmissions=0;this.trackingCapacityExcluded=0;}
 load(mint){
  if(!this.states.has(mint)){
   const saved=this.storage.getState(`fast-shadow:${mint}`),s={lastEntryAt:0,position:null,...saved};
   if(s.position){s.position.gapped=true;s.position.restartObserved=true;delete s.position.diagnostics;}
   this.states.set(mint,s);
  }
  return this.states.get(mint);
 }
 save(mint,s,now){this.storage.setState({...s,updatedAt:now},`fast-shadow:${mint}`);}
 trackingLimit(){return Math.min(12,Math.max(0,Math.floor(Math.min(this.config.researchFocusLimit||60,Math.max(1,Math.floor((this.config.maxCandidates||1000)/5)))/3)));}
 trackedPending(mint){const p=this.states.get(mint)?.position;return Boolean(p?.followup?.admitted);}
 register(now){
  if(this.registration)return;
  const evidence=this.storage.getState('fast-evidence-registration');
  this.evidenceRegistration=evidence.id===EVIDENCE_VERSION?evidence:{id:EVIDENCE_VERSION,registeredAt:now,rules:SHADOW_RULES,
   purpose:'Prospective Fast30 shadow comparisons only; no admission, notification or trading changes'};
  if(evidence.id!==EVIDENCE_VERSION)this.storage.setState(this.evidenceRegistration,'fast-evidence-registration');
  const prior=this.storage.getState('fast-followup-registration');
  if(prior.id!==FOLLOWUP_POLICY)this.storage.setState({id:FOLLOWUP_POLICY,registeredAt:now,limit:this.trackingLimit(),changesScheduling:true,requestLimitsChanged:false},'fast-followup-registration');
  const old=this.storage.getState('fast-shadow-registration');
  this.registration=old.id===FAST_VERSION?old:{...FAST_RULE,registeredAt:now};
  if(old.id!==FAST_VERSION)this.storage.setState(this.registration,'fast-shadow-registration');
 }
 observe(c,history,metrics,now,severe,hadDeterioration){
  const d=fastDecision(c,history,metrics,now,severe,hadDeterioration),s=this.load(c.mint);
  if(!d.eligible||s.position||now-s.lastEntryAt<FAST_RULE.cooldownMs)return {...d,admission:s.position?'tracking':now-s.lastEntryAt<FAST_RULE.cooldownMs?'cooldown':'not eligible'};
  this.register(now);
  const id=`${FAST_VERSION}:${c.mint}:${now}`;
  const used=[...this.states.values()].filter(x=>x.position?.followup?.admitted).length;
  const followup={policy:FOLLOWUP_POLICY,admitted:used<this.trackingLimit(),limit:this.trackingLimit(),reason:used<this.trackingLimit()?'capacity admitted':'tracking capacity full'};
  if(followup.admitted)this.trackingAdmissions++;else this.trackingCapacityExcluded++;
  const p={id,followup,mint:c.mint,pairAddress:c.pairAddress,at:now,priceUsd:c.priceUsd,lastAt:c.marketObservedAt,horizons:{},links:{},gapped:false,diagnostics:{version:EVIDENCE_VERSION,startedAt:now,partialHistory:false,windows:{},lastAttempt:null}};
  const entryFeatures={liquidityUsd:Number.isFinite(c.liquidityUsd)?c.liquidityUsd:null,return30sPct:d.return30sPct,
   lastIntervalReturnPct:d.lastIntervalReturnPct,transactions5m:(c.txns?.m5?.buys||0)+(c.txns?.m5?.sells||0),
   volume5mUsd:Number.isFinite(c.volume?.m5)?c.volume.m5:null,dexId:c.dexId||null};
  const shadowEvaluation={version:EVIDENCE_VERSION,registeredAt:this.evidenceRegistration.registeredAt,
   featureAt:now,features:entryFeatures,groups:evaluateEntryShadows(entryFeatures)};
  s.position=p;s.lastEntryAt=now;
  this.storage.transaction(()=>{
   this.storage.append('fast-shadow-entries',{...p,version:FAST_VERSION,cohort:'fast30-shadow',symbol:c.symbol||null,ruleId:FAST_VERSION,
    shadowEvaluation,quality:d.quality,decision:d,liquidityUsd:Number.isFinite(c.liquidityUsd)?c.liquidityUsd:null,
    security:{checkedAt:c.securityCheckedAt??null,mintAuthority:c.mintAuthority??null,freezeAuthority:c.freezeAuthority??null,top10Pct:c.top10Pct??null,
     status:!c.securityCheckedAt||now-c.securityCheckedAt>this.config.securityTtlMs?'expired or unavailable':c.mintAuthority===undefined||c.freezeAuthority===undefined||!Number.isFinite(c.top10Pct)?'incomplete':'limited checks complete'},
    evidence:{basis:'provider-response-time',poolAddress:history.pair,resetReason:history.resetReason,samples:history.rows.slice(-24).map(r=>({...r}))},
    baselineRulesChanged:false,notifications:false,followupPolicy:FOLLOWUP_POLICY});this.save(c.mint,s,now);
  });this.entries++;return {...d,admission:'recorded',entryId:id};
 }
 checkpoint(mint,c,now,valid,reason=null){
  const s=this.states.get(mint),p=s?.position;if(!p)return;
  attemptEvidence(p,c,now,valid);
  const usable=valid&&c?.pairAddress===p.pairAddress&&Number.isFinite(c.priceUsd)&&c.priceUsd>0&&c.marketObservedAt>p.lastAt&&c.marketObservedAt<=now;
  if(now-p.lastAt>45000)p.gapped=true;
  if(usable)p.lastAt=c.marketObservedAt;
  if(!reason&&!Object.entries(FAST_RULE.horizons).some(([h,ms])=>!p.horizons[h]&&now>=p.at+ms))return;
  let dirty=false;
  this.storage.transaction(()=>{
   for(const [h,ms] of Object.entries(FAST_RULE.horizons)){
    if(p.horizons[h])continue;const due=p.at+ms;
    const timely=usable&&c.marketObservedAt>=due&&c.marketObservedAt<=due+30000&&now<=due+30000;
    if(!reason&&!timely&&now<=due+30000)continue;
    const observed=!reason&&timely;
    this.storage.append('fast-shadow-outcomes',{id:`${p.id}:${h}`,entryId:p.id,mint,version:FAST_VERSION,at:now,entryAt:p.at,horizon:h,
     followup:p.followup||{policy:'legacy-unprioritized',admitted:false},
     ...diagnosticOutcome(p,h,now,reason,observed),
     status:observed?'observed':'missing',coverage:p.gapped?'gapped':'sampled',pairAddress:p.pairAddress,
     ...(observed?{sampleAt:c.marketObservedAt,priceUsd:c.priceUsd,returnPct:(c.priceUsd/p.priceUsd-1)*100}
      :{reason:reason||'no timely original-pool observation'}),basis:'provider-response-time; no costs or fills'});
    p.horizons[h]=observed?'observed':'missing';dirty=true;this.outcomes++;
   }
   if(dirty){if(Object.keys(p.horizons).length===4)s.position=null;this.save(mint,s,now);}
  });
 }
 link(c,entryId,cohort,now){const s=this.states.get(c.mint),p=s?.position;
  if(!p||p.pairAddress!==c.pairAddress||now<p.at||now-p.at>300000||p.links[cohort])return;
  p.links[cohort]=entryId;this.storage.transaction(()=>{
   this.storage.append('fast-shadow-links',{id:`${p.id}:${cohort}`,entryId:p.id,comparisonEntryId:entryId,cohort,mint:c.mint,pairAddress:p.pairAddress,at:now,leadMs:now-p.at,comparisonPriceUsd:Number.isFinite(c.priceUsd)&&c.priceUsd>0?c.priceUsd:null,
    comparisonObservedAt:c.marketObservedAt??null,followup:p.followup||{policy:'legacy-unprioritized',admitted:false},version:FAST_VERSION});
   this.save(c.mint,s,now);
  });this.links++;
 }
 sweep(now){for(const mint of this.states.keys())this.checkpoint(mint,null,now,false);}
 drop(mint,now){this.checkpoint(mint,null,now,false,'candidate left queue');this.states.delete(mint);}
 stats(){return {evidenceVersion:EVIDENCE_VERSION,evidenceRegisteredAt:this.evidenceRegistration?.registeredAt??null,version:FAST_VERSION,entriesSinceRestart:this.entries,outcomesSinceRestart:this.outcomes,linksSinceRestart:this.links,
  pending:[...this.states.values()].filter(s=>s.position).length,registeredAt:this.registration?.registeredAt??null,changesScheduling:true,notifications:false,followupPolicy:FOLLOWUP_POLICY,trackingLimit:this.trackingLimit(),trackingActive:[...this.states.values()].filter(s=>s.position?.followup?.admitted).length,trackingAdmissionsSinceRestart:this.trackingAdmissions,trackingCapacityExcludedSinceRestart:this.trackingCapacityExcluded};}
}
