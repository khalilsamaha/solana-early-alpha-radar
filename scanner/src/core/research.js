import {observationQuality} from './observation-quality.js';
import {FastShadow} from './fast-shadow.js';
import {qualify} from './qualification.js';
import {observeContinuity,CONTINUITY_VERSION} from './continuity.js';
import {MomentumHistory,MOMENTUM_VERSION,MAX_GAP_MS} from './momentum.js';
import {scoreCandidate} from './scoring.js';

export const RESEARCH_HORIZONS={'30s':30000,'1m':60000,'2m':120000,'5m':300000};
const TOLERANCE=30000;
const missingReasons={
  'different-pool':'A different pool was returned; no timely original-pool observation',
  'no-usable-market':'The latest market attempt returned no usable market',
  'provider-error':'The latest market attempt failed',
  'stale-or-invalid':'The latest market observation was stale or invalid',
  'no-timely-observation':'No timely original-pool observation within 30 seconds of checkpoint',
  'no-observation':'No market attempt was recorded after the research entry'
};
const severe=c=>c.auditIsSus===true||Boolean(c.mintAuthority)||Boolean(c.freezeAuthority)||c.top10Pct>50
  ||(c.extensions!==undefined&&(!Array.isArray(c.extensions)||c.extensions.some(x=>!['metadataPointer','tokenMetadata'].includes(x))));
const securityStatus=(c,now,config)=>now-(c.securityCheckedAt||0)>config.securityTtlMs?'expired or unavailable'
  :c.mintAuthority===undefined||c.freezeAuthority===undefined||!Number.isFinite(c.top10Pct)?'incomplete'
  :severe(c)?'adverse flags':'limited checks complete';
const publicToken=c=>Object.fromEntries(['mint','symbol','pairAddress','priceUsd','liquidityUsd','dexId'].map(k=>[k,c[k]]));

export class Research {
  constructor(config,storage){this.config=config;this.storage=storage;this.states=new Map();this.fast=new FastShadow(config,storage);this.eventCount=0;this.checkpointCount=0;}
  state(mint) {
    if(!this.states.has(mint)) {
      const saved=this.storage.getState(`research:${mint}`);
      const state={positions:[],lastActivityAt:0,riskLevel:0,hadDeterioration:false,lastRiskEventAt:0,...saved,history:new MomentumHistory(),summary:null};
      // We cannot reconstruct observations lost across a process restart.
      for(const p of state.positions)if(Object.keys(p.horizons).length<4){p.gapped=true;p.tokenGapped=true;p.alternateConfirmation=null;p.followupSamples={};}
      this.states.set(mint,state);this.fast.load(mint);
    }
    return this.states.get(mint);
  }
  persist(mint,s,now){this.storage.setState({positions:s.positions,lastActivityAt:s.lastActivityAt,riskLevel:s.riskLevel,
    hadDeterioration:s.hadDeterioration,lastRiskEventAt:s.lastRiskEventAt,updatedAt:now},`research:${mint}`);}
  checkpoint(mint,s,c,now,valid,forceReason=null) {
    this.fast.checkpoint(mint,c,now,valid,forceReason);
    let dirty=false;
    for(const p of s.positions) {
      if(Object.keys(p.horizons).length===4)continue;
      const usable=valid&&c?.mint===mint&&c?.pairAddress===p.pairAddress&&c.priceUsd>0;
      const followup=observeContinuity(p,c,now,valid);
      if(now-(p.lastTokenAt||p.at)>MAX_GAP_MS)p.tokenGapped=true;
      if(followup)p.lastTokenAt=followup.sampleAt;
      p.followupSamples||={};
      // Also flag a gap when no subsequent same-pool observation ever arrives.
      // HTTP receipt time is not an exchange trade timestamp or proof of execution.
      if(now-p.lastAt>MAX_GAP_MS)p.gapped=true;
      if(c)p.lastAttemptEvidence={at:now,status:valid?(usable?'same-pool':'different-pool')
        :c.marketAttemptStatus==='error'?'provider-error':c.marketAttemptStatus==='no-usable-market'?'no-usable-market':'stale-or-invalid',
        ...(valid?{pairAddress:c.pairAddress,sampleAt:c.marketObservedAt}:{})};
      if(usable)p.lastAt=now;
      for(const [horizon,ms] of Object.entries(RESEARCH_HORIZONS)) {
        if(p.horizons[horizon])continue;
        const due=p.at+ms;
        if(followup&&followup.sampleAt>=due&&followup.sampleAt<=due+TOLERANCE&&now<=due+TOLERANCE)
          p.followupSamples[horizon]||={...followup,coverage:p.tokenGapped?'gapped':'sampled'};
        if(!forceReason&&now<due)continue;
        const timely=usable&&c.marketObservedAt>=due&&c.marketObservedAt<=due+TOLERANCE;
        if(!forceReason&&!timely&&now<=due+TOLERANCE)continue;
        const observed=!forceReason&&timely&&now<=due+TOLERANCE;
        const reasonCode=forceReason?'candidate-left-queue':!p.lastAttemptEvidence?'no-observation'
          :p.lastAttemptEvidence.status==='same-pool'?'no-timely-observation':p.lastAttemptEvidence.status;
        const row={id:`${p.id}:${horizon}`,entryId:p.id,mint,cohort:p.cohort,at:now,entryAt:p.at,dueAt:due,horizon,
          status:observed?'observed':'missing',coverage:p.gapped?'gapped':'sampled',lagMs:Math.max(0,now-due),
          observationBasis:'provider-response-time',evidenceHistory:this.evidence(mint,24),
          tokenFollowup:{version:CONTINUITY_VERSION,...(p.followupSamples[horizon]||{status:'missing',reason:'No timely qualified token follow-up',coverage:p.tokenGapped?'gapped':'sampled'})},
          evidence:{entryPool:p.pairAddress,lastSamePoolAt:p.lastAt,lastAttempt:p.lastAttemptEvidence||null},
          ...(observed?{sampleAt:c.marketObservedAt,priceUsd:c.priceUsd,returnPct:(c.priceUsd/p.priceUsd-1)*100}
            :{reasonCode,reason:forceReason||missingReasons[reasonCode]})};
        this.storage.append('research-outcomes',row);p.horizons[horizon]=row.status;dirty=true;this.checkpointCount++;
      }
    }
    if(dirty)this.persist(mint,s,now);
  }
  startEntry(c,s,cohort,now,summary) {
    const id=`${MOMENTUM_VERSION}:${cohort}:${c.mint}:${now}`;
    const p={id,mint:c.mint,cohort,at:now,priceUsd:c.priceUsd,pairAddress:c.pairAddress,lastAt:now,lastTokenAt:now,horizons:{},gapped:false,tokenGapped:false,followupSamples:{},alternateConfirmation:null};
    // At most one activity episode per six hours, plus one baseline entry.
    s.positions=s.positions.filter(p=>Object.keys(p.horizons).length<4);
    s.positions.push(p);
    this.storage.append('research-entries',{...p,version:MOMENTUM_VERSION,candidate:publicToken(c),
      baselineScore:c.score,experimentalScore:summary?.score??null,security:summary?.security??'unknown',features:summary?.metrics??null,
      qualification:qualify(c,summary,now),evidence:this.evidence(c.mint)});
    this.fast.link(c,id,cohort,now);
    this.persist(c.mint,s,now);return id;
  }
  baseline(c,now) {
    if(!this.config.researchEnabled)return;
    const s=this.state(c.mint);
    if(s.positions.some(p=>p.cohort==='baseline'&&p.at===now))return;
    this.startEntry(c,s,'baseline',now,s.summary);
  }
  emit(c,s,event,now,reasons,entryId=null) {
    const row={id:`${MOMENTUM_VERSION}:${event}:${c.mint}:${now}`,at:now,type:'research',event,version:MOMENTUM_VERSION,
      mint:c.mint,entryId,candidate:publicToken(c),baselineScore:c.score,experimentalScore:s.summary.score,
      evidence:this.evidence(c.mint),qualification:qualify(c,s.summary,now),stage:s.summary.stage,security:s.summary.security,features:s.summary.metrics,reasons,
      expiresAt:now+45000,text:`RADAR RESEARCH — ${event.toUpperCase()} — ${c.symbol||c.mint}\nMint: ${c.mint}\nObserved: ${new Date(now).toISOString()}\n${reasons.join('\n')}\nSecurity: ${s.summary.security}\nExperimental observation, not a buy or sell instruction.`};
    this.storage.append('research-events',row);this.eventCount++;
    if(this.config.researchNotifications&&this.config.notificationsEnabled)this.storage.queue(row);
  }
  observe(c,forScore,baseline,now,valid) {
    if(!this.config.researchEnabled)return null;
    const s=this.state(c.mint);
    valid=Boolean(valid&&c.pairAddress&&Number.isFinite(c.marketObservedAt)&&now-c.marketObservedAt>=0&&now-c.marketObservedAt<=MAX_GAP_MS);
    if(valid&&s.history.rows.at(-1)?.at>=c.marketObservedAt)return this.describe(c.mint,now);
    this.checkpoint(c.mint,s,c,now,valid);
    if(!valid){s.summary={...s.summary,stage:'data unavailable',at:now,score:null};return s.summary;}
    const priorPair=s.history.pair;
    const metrics=s.history.observe(c,c.marketObservedAt||now);
    if(priorPair&&priorPair!==c.pairAddress){
      s.hadDeterioration=false;s.riskLevel=0;s.recoverySince=null;
      s.lastPoolChange={at:now,from:priorPair,to:c.pairAddress,migrationVerified:false};
      this.storage.append('research-events',{id:`${MOMENTUM_VERSION}:pool:${c.mint}:${now}`,at:now,
        version:MOMENTUM_VERSION,mint:c.mint,event:'pool changed',candidate:publicToken(c),
        security:securityStatus(c,now,this.config),poolChange:s.lastPoolChange,evidence:this.evidence(c.mint),
        reasons:['The provider returned another pool for this exact mint. Migration is not verified.',
          'Momentum history restarts; alternate-pool follow-ups are reported separately.']});
      this.eventCount++;
    }
    const experimental=scoreCandidate(forScore,null,now,metrics);
    const peak=c.paperEntry&&c.paperEntry.pairAddress===c.pairAddress?c.paperEntry.peakPrice:null;
    const dd=peak>0?Math.min(metrics.drawdownPct??0,(c.priceUsd/peak-1)*100):metrics.drawdownPct;
    const r30=metrics.r30?.returnPct,r60=metrics.r60?.returnPct;
    const liquidityDrop=metrics.r30?.liquidityChangePct;
    const risk=!metrics.ready?0:(r30<=-20||dd<=-30||liquidityDrop<=-30?2:r30<=-10||dd<=-15?1:0);
    const changedRecently=metrics.unchangedForMs<=MAX_GAP_MS;
    const moving=metrics.ready&&changedRecently&&metrics.r60.changedSamples>=2;
    let stage=!metrics.ready?'warming up':!changedRecently?'no recent market change':risk?'deteriorating'
      :s.hadDeterioration?'recovery unconfirmed':r60>=10?'rising':r60<=-5?'falling':'observing';
    s.summary={at:now,poolChange:s.lastPoolChange||null,version:MOMENTUM_VERSION,stage,score:metrics.ready?experimental.score:null,baselineScore:baseline.score,
      security:securityStatus(c,now,this.config),metrics:{...metrics,drawdownPct:dd},
      contributions:experimental.reasons,risks:experimental.risks,mode:this.config.researchNotifications?'experimental notifications enabled':'shadow'};
    const eligibleRisk=Boolean(c.paperEntry)||s.lastActivityAt>0;
    if(eligibleRisk&&risk>0) {
      s.recoverySince=null;
      if(!s.hadDeterioration||(risk>s.riskLevel&&now-s.lastRiskEventAt>=15000)) {
        s.hadDeterioration=true;s.lastRiskEventAt=now;
        this.emit(c,s,risk===2?'risk escalation':'rapid drop',now,[
          `Drawdown from recorded peak: ${dd?.toFixed(1)}%`,
          `Approximately 30s price change: ${Number.isFinite(r30)?r30.toFixed(1)+'%':'unavailable'}`]);
        s.riskLevel=risk;this.persist(c.mint,s,now);
      }
    } else if(s.hadDeterioration&&moving&&r60>=10&&r30>0&&dd>-15&&c.exitRisk?.level!=='high'&&!severe(c)) {
      s.recoverySince??=now;
      if(now-s.recoverySince>=30000) {
        s.summary.stage='recovery observed';s.hadDeterioration=false;s.riskLevel=0;s.recoverySince=null;
        this.emit(c,s,'recovery observed',now,['Positive short-window movement persisted for 30 seconds; future continuation is unknown.']);
        this.persist(c.mint,s,now);
      }
    } else s.recoverySince=null;
    s.summary.observationQuality=observationQuality(s.history,now);
    s.summary.fastShadow=this.fast.observe(c,s.history,metrics,now,severe(c),s.hadDeterioration);
    const flow=metrics.r60;
    const activity=moving&&!risk&&!s.hadDeterioration&&!c.inactive&&!severe(c)
      &&(c.liquidityUsd>=5000||(!Number.isFinite(c.liquidityUsd)&&c.dexId==='pumpfun'))
      &&((c.txns?.m5?.buys||0)+(c.txns?.m5?.sells||0)>=35)
      &&r60>=10&&(flow.volumeDeltaPerMinute>1000||flow.transactionsDeltaPerMinute>8);
    if(activity&&now-(s.lastActivityAt||0)>=21600000) {
      s.lastActivityAt=now;
      const id=this.startEntry(c,s,'early-activity',now,s.summary);
      this.emit(c,s,'early activity',now,[`Price +${r60.toFixed(1)}% over ${(flow.spanMs/1000).toFixed(0)} seconds`,
        'Rolling activity increased; transaction counts do not establish organic demand.',
        Number.isFinite(c.liquidityUsd)?`Reported liquidity: $${Math.round(c.liquidityUsd)}`:'Liquidity unknown; observation only.'],id);
    }
    return s.summary;
  }
  evidence(mint,maxSamples=24) {
    const h=this.states.get(mint)?.history;
    return {version:'event-evidence-1',basis:'provider-response-time',poolAddress:h?.pair||null,
      resetReason:h?.resetReason||'unavailable',maxSamples,samples:(h?.rows||[]).slice(-maxSamples).map(r=>({...r}))};
  }
  describe(mint,now=Date.now()) {
    const s=this.states.get(mint);if(!s?.summary)return null;
    const value={...s.summary,observationQuality:observationQuality(s.history,now)};
    return now-(s.summary.metrics?.at||0)>MAX_GAP_MS?{...value,stage:'data unavailable',score:null}:value;
  }
  sweep(now=Date.now()) {
    for(const [mint,s] of this.states)this.checkpoint(mint,s,null,now,false);
  }
  drop(mint,now=Date.now()) {
    const s=this.states.get(mint);
    if(s)this.checkpoint(mint,s,null,now,false,'Candidate left the monitored queue');
    this.fast.drop(mint,now);this.states.delete(mint);
  }
  pending(mint) {return Boolean(this.config.researchEnabled&&this.states.get(mint)?.positions.some(p=>Object.keys(p.horizons).length<4));}
  trackingPending(mint) {return this.pending(mint)||Boolean(this.config.researchEnabled&&this.fast.trackedPending(mint));}
  focusTier(c,now) {
    if(!this.config.researchEnabled)return null;
    if(this.pending(c.mint))return 0;
    if(this.fast.trackedPending(c.mint))return 0.5;
    if(c.inactive)return null;
    if(c.stale||!c.pairAddress||!(c.priceUsd>0)||!c.marketObservedAt||now-c.marketObservedAt>this.config.freshMs||severe(c))return null;
    const tx=(c.txns?.m5?.buys||0)+(c.txns?.m5?.sells||0);
    if(c.liquidityUsd>=5000&&tx>=15)return 1;
    if(!Number.isFinite(c.liquidityUsd)&&c.dexId==='pumpfun'&&tx>=35&&c.volume?.m5>=1000&&c.priceChange?.m5>=8)return 2;
    return null;
  }
  stats(now=Date.now()){
    const stages={};let readyCandidates=0;
    for(const mint of this.states.keys()){const v=this.describe(mint,now),stage=v?.stage||'not initialized';stages[stage]=(stages[stage]||0)+1;if(v?.metrics?.ready&&stage!=='data unavailable')readyCandidates++;}
    return {fastShadow:this.fast.stats(),observationQualityVersion:'observation-quality-1',readyCandidates,stages,enabled:this.config.researchEnabled,notificationsEnabled:this.config.researchNotifications,
    version:MOMENTUM_VERSION,bufferedCandidates:this.states.size,bufferedPoints:[...this.states.values()].reduce((n,s)=>n+s.history.rows.length,0),
    eventsSinceRestart:this.eventCount,checkpointsSinceRestart:this.checkpointCount};}
}

export function summarizeResearch(entries,outcomes,now=Date.now()) {
  const indexed=new Map(outcomes.map(o=>[`${o.entryId}:${o.horizon}`,o]));
  return Object.fromEntries(['baseline','early-activity'].map(cohort=>{
    const rows=entries.filter(e=>e.cohort===cohort);
    const horizons=Object.fromEntries(Object.entries(RESEARCH_HORIZONS).map(([h,ms])=>{
      let pending=0,overdue=0,missing=0,gapped=0;const values=[],missingByReason={};
      for(const e of rows){const o=indexed.get(`${e.id}:${h}`);
        if(!o){if(now<=e.at+ms+TOLERANCE)pending++;else overdue++;}
        else if(o.status!=='observed'||!Number.isFinite(o.returnPct)){missing++;const reason=o.reasonCode||'legacy-or-unspecified';missingByReason[reason]=(missingByReason[reason]||0)+1;}
        else if(o.coverage==='gapped')gapped++;else values.push(o.returnPct);
      }
      values.sort((a,b)=>a-b);const n=values.length;
      return [h,{observed:n,gapped,missing,pending,overdue,missingByReason,aboveEntry:values.filter(x=>x>0).length,
        medianReturnPct:n?(values[Math.floor((n-1)/2)]+values[Math.floor(n/2)])/2:null}];
    }));
    return [cohort,{entries:rows.length,horizons}];
  }));
}
