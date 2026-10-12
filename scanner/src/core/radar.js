import {applyFeed,FEED_VERSION} from './feed-evidence.js';
import {summaryEvents,statisticsHealth} from './stats-memory.js';
import {qualify,qualificationSummary} from './qualification.js';
import {summarizeContinuity} from './continuity.js';
import {RESEARCH_HORIZONS} from './research.js';
import {Research,summarizeResearch} from './research.js';
import {MOMENTUM_VERSION} from './momentum.js';
import {setTimeout as delay} from 'node:timers/promises';
import * as dex from '../adapters/dexscreener.js';
import * as jupiter from '../adapters/jupiter.js';
import {getMintSecurity} from '../adapters/helius.js';
import {ensureTimeline,recordDecision,describeDecision} from './decision.js';
import {summarizeOutcomes} from './outcome-summary.js';
import {scoreCandidate} from './scoring.js';
import {createEntry,updatePaper,tracking} from './paper.js';
import {exitRisk} from './exit.js';
import {Health} from './health.js';
import {HttpClient} from './http.js';
import {Notifications} from './notifications.js';
const clean=obj=>Object.fromEntries(Object.entries(obj||{}).filter(([,v])=>v!==undefined));
export const validMint=mint=>typeof mint==='string'&&/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(mint);
export class Radar {
  constructor(config,storage,adapters={}) {
    Object.assign(this,{config,storage});this.candidates=new Map(Object.entries(storage.loadCandidates()));
    this.research=new Research(config,storage);this.researchFocus=new Set();this.focusEligibleCount=0;
    if(config.researchEnabled)for(const mint of this.candidates.keys())this.research.state(mint);
    this.health=new Health(config);this.http=new HttpClient(config,this.health);
    this.notifications=new Notifications(config,storage);this.running=false;this.status=[];
    this.adapters={getTokenPairs:dex.getTokenPairs,getTokenPair:dex.getTokenPair,getLatestProfiles:dex.getLatestProfiles,getMintSecurity,
      getRecent:jupiter.getRecent,getTopOrganic:jupiter.getTopOrganic,searchToken:jupiter.searchToken,...adapters};
    this.abort=new AbortController();this.loops=[];this.lastPruneAt=0;this.lastOpsState=null;this.inFlight=new Set();this.marketGroupCursor=0;this.metadataTurns={};this.metadataBusy=new Set();this.snapshotCounts={stored:0,skipped:0};
  }
  log(message) {
    let safe=String(message).replace(/https?:\/\/\S+/g,'[URL]');
    for(const key of ['pumpPortalApiKey','jupiterApiKey','heliusApiKey','telegramBotToken','dashboardToken'])if(this.config[key])safe=safe.split(this.config[key]).join('[REDACTED]');
    const row={at:new Date().toISOString(),message:safe.slice(0,500)};
    this.status.push(row);this.status=this.status.slice(-100);console.log(JSON.stringify({component:'radar',...row}));
  }
  addCandidate(input) {
    if(!validMint(input?.mint))return null;
    const now=Date.now(),memory=this.candidates.get(input.mint),archived=this.storage.getState(`paper:${input.mint}`),prev=memory||(archived.paperEntry?archived:null);
    // A bounded queue exposes dropped discovery; ongoing paper entries are never evicted.
    if(!memory&&this.candidates.size>=this.config.maxCandidates) {
      const expendable=[...this.candidates.values()].filter(x=>!tracking(x)&&!this.research.fast.trackedPending(x.mint)&&!this.researchFocus.has(x.mint)&&!this.inFlight.has(x.mint)).sort((a,b)=>Number(!a.inactive)-Number(!b.inactive)||(a.lastDiscoveryAt||a.firstSeenAt)-(b.lastDiscoveryAt||b.firstSeenAt))[0];
      if(!expendable){this.droppedCandidates=(this.droppedCandidates||0)+1;return null;}
      if(!expendable.lastAttemptAt)this.evictedBeforeAttempt=(this.evictedBeforeAttempt||0)+1;
      this.research.drop(expendable.mint);this.storage.deleteCandidate(expendable.mint);this.candidates.delete(expendable.mint);this.droppedCandidates=(this.droppedCandidates||0)+1;
    }
    const next={...prev,...clean(input),mint:input.mint,firstSeenAt:prev?.firstSeenAt||now,lastDiscoveryAt:now,
      discoverySources:[...new Set([...(prev?.discoverySources||[]),input.discoverySource||'unknown'])]};
    // Preserve operational state when discovery updates metadata.
    if(prev?.launchAt)next.launchAt=prev.launchAt;
    ensureTimeline(next,now);this.candidates.set(next.mint,next);this.storage.saveCandidate(next);return next;
  }
  persist() {this.storage.saveCandidates(Object.fromEntries(this.candidates));}
  save(row) {this.candidates.set(row.mint,row);this.storage.saveCandidate(row);if(row.paperEntry)this.storage.setState({paperEntry:row.paperEntry,alertLevel:row.alertLevel,alertedAt:row.alertedAt,decisionTimeline:row.decisionTimeline},`paper:${row.mint}`);}
  updateResearchFocus(rows,now) {
    const eligible=rows.filter(c=>!tracking(c)&&c.lastAttemptAt).map(c=>({c,tier:this.research.focusTier(c,now)})).filter(x=>x.tier!==null);
    // Stable membership allows a history to warm up. Higher-priority pending
    // checkpoints or known-liquid markets can replace discovery-only markets.
    eligible.sort((a,b)=>a.tier-b.tier||Number(this.researchFocus.has(b.c.mint))-Number(this.researchFocus.has(a.c.mint))
      ||(a.c.lastAttemptAt||0)-(b.c.lastAttemptAt||0)||(a.c.firstSeenAt||0)-(b.c.firstSeenAt||0));
    const ordinary=eligible.filter(x=>x.tier!==0.5);
    const limit=Math.min(this.config.researchFocusLimit||60,Math.max(1,Math.floor(this.config.maxCandidates/5)));
    const next=new Set(eligible.slice(0,limit).map(x=>x.c.mint));
    this.fastFocusDisplaced=ordinary.slice(0,limit).filter(x=>!next.has(x.c.mint)).length;
    this.fastFocusSelected=eligible.slice(0,limit).filter(x=>x.tier===0.5).length;
    this.fastFocusAwaiting=eligible.filter(x=>x.tier===0.5&&!next.has(x.c.mint)).length;
    this.focusEligibleCount=eligible.length;
    this.researchFocus=new Set(eligible.slice(0,Math.min(this.config.researchFocusLimit||60,Math.max(1,Math.floor(this.config.maxCandidates/5)))).map(x=>x.c.mint));
  }
  selectBatch(now=Date.now()) {
    const rows=[...this.candidates.values()].filter(x=>!x.inactive||tracking(x)||this.research.trackingPending(x.mint));
    this.updateResearchFocus(rows,now);
    const order=(a,b)=>(a.lastAttemptAt||0)-(b.lastAttemptAt||0)||(a.firstSeenAt||0)-(b.firstSeenAt||0);
    const active=rows.filter(x=>now-(x.lastAttemptAt||0)>=this.config.enrichIntervalMs && (this.research.trackingPending(x.mint)||now>=(x.nextMarketAttemptAt||0)));
    const tracked=active.filter(tracking).sort(order),fresh=active.filter(x=>!tracking(x)&&!x.lastAttemptAt).sort(order);
    const focus=active.filter(x=>!tracking(x)&&x.lastAttemptAt&&this.researchFocus.has(x.mint)).sort(order);
    const rest=active.filter(x=>!tracking(x)&&x.lastAttemptAt&&!this.researchFocus.has(x.mint)).sort(order);
    const selected=[];
    while(selected.length<this.config.batchSize&&(tracked.length||fresh.length||focus.length||rest.length)) {
      const group=[tracked,fresh,focus,rest][this.marketGroupCursor++%4];
      if(group.length)selected.push(group.shift());
    }
    return selected;
  }
  async enrichOne(mint,observation) {
    this.inFlight.add(mint);
    try{return await this.enrichCandidate(mint,observation);}finally{this.inFlight.delete(mint);}
  }
  async enrichCandidate(mint,observation) {
    const base=this.candidates.get(mint);if(!base)return;
    if(observation===undefined) {
      try {observation={market:await this.adapters.getTokenPair(mint,this.http,base.paperEntry?.pairAddress||base.pairAddress),observedAt:Date.now()};}
      catch(e){this.log(`DEX: ${e.message}`);observation={market:null,failed:true};}
    }
    return this.applyObservation(mint,observation);
  }
  applyObservation(mint,observation) {
    const base=this.candidates.get(mint);if(!base)return;
    const started=Date.now();base.lastAttemptAt=started;
    const times=[base.launchAt,base.firstPoolAt,base.pairCreatedAt].filter(x=>x>0);
    let tooOld=started-(times.length?Math.min(...times):base.firstSeenAt)>this.config.maxCandidateAgeMin*60000;
    if(tooOld&&!tracking(base)&&!this.research.trackingPending(mint)){base.inactive=true;recordDecision(this.storage,base,this.config,started);this.save(base);return;}
    const {market}=observation,now=observation.observedAt||Date.now();
    // Merge after awaits: a discovery or metadata worker may have updated this row.
    let current={...this.candidates.get(mint)};
    if(!current.mint)return;
    const fresh=market?.mint===mint&&Number.isFinite(market.priceUsd)&&market.priceUsd>0
      &&(!current.paperEntry?.pairAddress||market.pairAddress===current.paperEntry.pairAddress);
    if(fresh) {
      current={...current,...market,feedEvidence:applyFeed(current,market,started),marketObservedAt:now,observedAt:now,stale:false,marketEmptyCount:0,nextMarketAttemptAt:0};
      this.health.lastMarketAt=Math.max(this.health.lastMarketAt,now);
    } else {
      current.stale=true;
      if(!observation.failed&&!tracking(current)) {
        current.marketEmptyCount=(current.marketEmptyCount||0)+1;
        // Pending research deadlines must not inherit a five-minute empty-market backoff.
        // The ordinary scheduler and HTTP limiter still bound actual attempts.
        current.nextMarketAttemptAt=Date.now()+(this.research.trackingPending(mint)?this.config.enrichIntervalMs
          :Math.min(300000,30000*2**Math.min(4,current.marketEmptyCount-1)));
      }
    }
    current.marketAttemptStatus=observation.failed?'error':fresh?'observed':'no-usable-market';
    const scoredAt=Date.now();
    const knownTimes=[current.launchAt,current.firstPoolAt,current.pairCreatedAt].filter(x=>x>0);
    tooOld=scoredAt-(knownTimes.length?Math.min(...knownTimes):current.firstSeenAt)>this.config.maxCandidateAgeMin*60000;
    // Network delays or previously cached metadata cannot masquerade as fresh inputs.
    const marketFresh=fresh&&scoredAt-current.marketObservedAt<=this.config.freshMs;
    const securityFresh=Number.isFinite(current.securityCheckedAt)&&scoredAt-current.securityCheckedAt<=this.config.securityTtlMs;
    const forScore={...current};
    if(!securityFresh){delete forScore.mintAuthority;delete forScore.freezeAuthority;delete forScore.top10Pct;}
    if(scoredAt-(current.jupiterCheckedAt||0)>this.config.jupiterTtlMs){delete forScore.organicScore;delete forScore.holderCount;}
    const previous=base.lastSnapshot&&base.lastSnapshot.pairAddress===current.pairAddress&&now-base.lastSnapshot.observedAt<=this.config.freshMs?base.lastSnapshot:null;
    const scoring=scoreCandidate(forScore,previous,scoredAt);
    current.score=marketFresh?scoring.score:0;current.band=marketFresh?scoring.band:'stale';
    current.scoreReasons=scoring.reasons;current.scoreRisks=scoring.risks;current.securityFresh=securityFresh;
    current.stale=!marketFresh;current.updatedAt=scoredAt;current.inactive=tooOld&&!tracking(current);
    const trackedAtStart=tracking(current);
    let archivedSnapshot=false;
    const rows=updatePaper(current,scoredAt,this.config.horizonToleranceMs,marketFresh);
    current.exitRisk=exitRisk(current,previous,marketFresh);
    this.storage.transaction(()=>{
    this.research.observe(current,forScore,scoring,scoredAt,marketFresh);
    recordDecision(this.storage,current,this.config,scoredAt);
    if(marketFresh) {
      const snapshot={...Object.fromEntries(['mint','symbol','dexId','pairAddress','priceUsd','marketCap','liquidityUsd','txns','volume','priceChange','organicScore','score','band'].map(k=>[k,current[k]])),at:now,observedAt:now};
      // Scoring always compares successive live observations, independently of the archive.
      current.lastSnapshot=snapshot;
      const fullCadence=trackedAtStart||tracking(current)||current.score>=this.config.alertScore;
      const tier=fullCadence?'paper-or-signal':current.liquidityUsd>=5000?'routine':'thin-or-unknown';
      const interval=tier==='thin-or-unknown'?this.config.thinSnapshotIntervalMs:this.config.snapshotIntervalMs;
      const elapsed=now-(current.lastArchivedSnapshotAt||0);
      const archive=fullCadence||!current.lastArchivedSnapshotAt||elapsed>=interval||elapsed<0
        ||current.lastArchivedSnapshotPair!==current.pairAddress
        ||(current.lastArchivedSnapshotTier==='thin-or-unknown'&&tier==='routine');
      if(archive) {
        this.storage.append('snapshots',{...snapshot,archiveTier:tier});archivedSnapshot=true;
        current.lastArchivedSnapshotAt=now;current.lastArchivedSnapshotPair=current.pairAddress;current.lastArchivedSnapshotTier=tier;
      }
      if(!tooOld&&(!this.config.requireSecurity||securityFresh))this.maybeAlert(current,scoring,scoredAt);
      this.maybeExitAlert(current,scoring,scoredAt);
    }
    // The persisted candidate carries horizon flags in the same transaction as outcomes.
    current.discoverySources=[...new Set([...(current.discoverySources||[]),...(this.candidates.get(mint)?.discoverySources||[])])];
    for(const row of rows)this.storage.append('outcomes',row);this.save(current);
    });
    if(marketFresh)this.snapshotCounts[archivedSnapshot?'stored':'skipped']++;
    this.health.lastLoopAt=Date.now();
  }
  async enrichBatch(rows=this.selectBatch()) {
    if(!rows.length)return;
    for(const row of rows)this.inFlight.add(row.mint);
    try {
      let observations;
      try {observations=await this.adapters.getTokenPairs(rows,this.http);}
      catch(e){this.log(`DEX batch: ${e.message}`);observations=new Map(rows.map(c=>[c.mint,{market:null,failed:true}]));}
      // All network waits finished. Commit the completed batch atomically, with no awaits.
      this.storage.transaction(()=>{
        for(const row of rows)this.applyObservation(row.mint,observations.get(row.mint)||{market:null,failed:true});
      });
    } finally {for(const row of rows)this.inFlight.delete(row.mint);}
  }
  metadataEligible(c,now=Date.now()) {
    return (!c.inactive||tracking(c))&&!c.stale&&c.marketObservedAt>0&&now-c.marketObservedAt<=this.config.freshMs
      &&(tracking(c)||(c.liquidityUsd>=5000&&(c.txns?.m5?.buys||0)+(c.txns?.m5?.sells||0)>=15));
  }
  selectMetadata(provider,now=Date.now()) {
    const security=provider==='helius',checked=security?'securityCheckedAt':'jupiterCheckedAt';
    const attempted=security?'securityAttemptAt':'jupiterAttemptAt',ttl=security?this.config.securityTtlMs:this.config.jupiterTtlMs;
    const rows=[...this.candidates.values()].filter(c=>this.metadataEligible(c,now)&&now-(c[checked]||0)>=ttl&&now-(c[attempted]||0)>=ttl)
      .sort((a,b)=>(a[attempted]||0)-(b[attempted]||0)||(a.firstSeenAt||0)-(b.firstSeenAt||0));
    const paper=rows.filter(tracking),other=rows.filter(c=>!tracking(c));
    // Reserve every third turn for ordinary candidates even during heavy paper tracking.
    const preferPaper=(this.metadataTurns[provider]||0)%3!==2;
    return (preferPaper?paper[0]||other[0]:other[0]||paper[0])||null;
  }
  async refreshMetadata(provider,mint) {
    const key=`${provider}:${mint}`;
    if(this.metadataBusy.has(key))return;
    const current=this.candidates.get(mint);
    if(!current||!this.metadataEligible(current)||!this.config[`${provider}ApiKey`])return;
    const security=provider==='helius',attempted=security?'securityAttemptAt':'jupiterAttemptAt';
    const generation=current.firstSeenAt,started=Date.now();
    const attempting={...current,[attempted]:started};
    if(security){const timeline=ensureTimeline(attempting,started);timeline.firstSecurityAttemptAt||=started;}
    this.save(attempting);this.metadataBusy.add(key);
    this.metadataTurns[provider]=(this.metadataTurns[provider]||0)+1;
    try {
      const result=security?await this.adapters.getMintSecurity(mint,this.config.heliusApiKey,this.http)
        :await this.adapters.searchToken(mint,this.config.jupiterApiKey,this.http);
      const latest=this.candidates.get(mint);
      if(!result||!latest||latest.firstSeenAt!==generation||latest[attempted]!==started)return;
      // Only metadata fields may cross this boundary; never restore an old price or paper state.
      const fields=security?['mintAuthority','freezeAuthority','top10Pct','concentrationMethod','tokenProgram','extensions','securityCheckedAt']
        :['organicScore','holderCount','auditIsSus','isVerified','jupiterStats'];
      const patch=Object.fromEntries(fields.map(field=>[field,result[field]]));
      if(!security)patch.jupiterCheckedAt=Date.now();
      const enriched={...latest,...patch};
      this.storage.transaction(()=>{recordDecision(this.storage,enriched,this.config,Date.now(),'metadata');this.save(enriched);});
    }catch(e){this.log(`${provider}: ${e.message}`);}
    finally {this.metadataBusy.delete(key);}
  }
  async metadataLoop(provider) {
    while(this.running) {
      const row=this.selectMetadata(provider);
      if(row)await this.refreshMetadata(provider,row.mint);
      await this.pause(this.config.metadataPauseMs);
    }
  }
  maybeAlert(candidate,scoring,now=Date.now()) {
    if(candidate.stale||scoring.score<this.config.alertScore||!(candidate.priceUsd>0))return;
    const level=scoring.score>=this.config.strongAlertScore?2:1;
    if((candidate.alertLevel||0)>=level)return;
    const firstEntry=!candidate.paperEntry;
    candidate.alertLevel=level;candidate.alertedAt||=now;
    candidate.paperEntry||=createEntry(candidate,now);
    const timeline=ensureTimeline(candidate,now);timeline.firstAlertAt||=now;
    recordDecision(this.storage,candidate,this.config,now,'alert');
    const alert={id:`${candidate.mint}:${candidate.paperEntry.at}:${level}`,at:now,level,type:'signal',engineVersion:'0.2.9',decisionTimeline:{...candidate.decisionTimeline},
      candidate:Object.fromEntries(['mint','symbol','tokenName','priceUsd','marketCap','liquidityUsd','organicScore','holderCount','top10Pct','pairAddress'].map(k=>[k,candidate[k]])),scoring};
    alert.marketContext=this.research.describe(candidate.mint,now);
    alert.qualification=qualify(candidate,alert.marketContext,now);
    alert.evidence={...this.research.evidence(candidate.mint),inputs:{
      priceUsd:candidate.priceUsd,pairAddress:candidate.pairAddress,liquidityUsd:candidate.liquidityUsd,
      volume5mUsd:candidate.volume?.m5,transactions5m:candidate.txns?.m5,
      providerPriceChange5mPct:candidate.priceChange?.m5,marketCap:candidate.marketCap,
      marketObservedAt:candidate.marketObservedAt,securityCheckedAt:candidate.securityCheckedAt,
      jupiterCheckedAt:candidate.jupiterCheckedAt,holderCount:candidate.holderCount},scoringMetrics:{...scoring.metrics}};
    if(firstEntry)this.research.baseline(candidate,now);
    this.storage.recordAlert(candidate,alert,this.config.notificationsEnabled);
    this.log(`Signal ${candidate.mint} score=${scoring.score}`);
  }
  maybeExitAlert(candidate,scoring,now) {
    if(!candidate.paperEntry||candidate.exitRisk.level!=='high'||now-(candidate.lastExitAlertAt||0)<900000)return;
    candidate.lastExitAlertAt=now;
    const alert={id:`exit:${candidate.mint}:${now}`,at:now,type:'exit',candidate:{mint:candidate.mint,symbol:candidate.symbol},
      text:`RADAR DETERIORATION — ${candidate.symbol||candidate.mint}\nMint: ${candidate.mint}\nObserved: ${new Date(now).toISOString()}\n${candidate.exitRisk.reasons.join('\n')}\nExperimental paper-monitoring warning; not a peak prediction.`};
    this.storage.transaction(()=>{this.save(candidate);this.storage.append('exit-alerts',alert);if(this.config.notificationsEnabled)this.storage.queue(alert);});
  }
  async pause(ms){try{await delay(ms,undefined,{signal:this.abort.signal});}catch(e){if(e.name!=='AbortError')throw e;}}
  async enrichLoop() {
    while(this.running) {
      this.health.lastLoopAt=Date.now();
      await this.enrichBatch();
      const now=Date.now();this.research.sweep(now);
      if(now-this.lastPruneAt>3600000){this.storage.prune(now-this.config.snapshotDays*86400000);this.lastPruneAt=now;}
      this.storage.setState(this.getHealth(),'health');
      await this.pause(this.config.marketBatchPauseMs);
    }
  }
  async discoveryLoop(source,interval) {
    while(this.running) {
      try {
        if(source==='dex') {
          const rows=await this.adapters.getLatestProfiles(this.http);
          for(const row of rows)this.addCandidate({mint:row.tokenAddress,discoverySource:'dexscreener:profile'});
        } else {
          // A single failing feed does not discard successful discovery from its sibling.
          for(const get of [this.adapters.getRecent,this.adapters.getTopOrganic]) {
            try {for(const row of await get(this.config.jupiterApiKey,this.http))this.addCandidate({...jupiter.normalizeDiscoveryRow(row),discoverySource:'jupiter'});}
            catch(e){this.log(`Jupiter discovery: ${e.message}`);}
          }
        }
      }catch(e){this.log(`${source} discovery: ${e.message}`);}
      await this.pause(interval);
    }
  }
  async notificationLoop() {
    while(this.running) {
      if(this.config.operationalNotifications&&this.config.notificationsEnabled&&Date.now()-this.health.startedAt>180000) {
        const healthy=this.getHealth().ready;
        if(this.lastOpsState!==healthy) {
          this.lastOpsState=healthy;
          this.storage.queue({id:`ops:${Date.now()}`,at:Date.now(),text:`RADAR SERVICE ${healthy?'RECOVERED':'DEGRADED'}\n${healthy?'Fresh market observations are arriving.':'No fresh market observations. Check readiness, providers and queue lag.'}`});
        }
      }
      if(this.config.operationalNotifications&&this.config.notificationsEnabled) {
        const now=Date.now(),state=this.storage.getState('digest');
        if(!state.nextAt)this.storage.setState({nextAt:now+86400000},'digest');
        else if(now>=state.nextAt) {
          const s=this.getStats();
          this.storage.transaction(()=>{
            this.storage.queue({id:`digest:${state.nextAt}`,at:now,text:`RADAR DAILY STATUS\nLifetime paper entries: ${s.uniquePaperEntries}\n60m observed: ${s.evaluated60m}; missing: ${s.missing60m}; gapped: ${s.gapped60m}\nObserved 2x: ${s.doubledWithin60m}\nResearch metrics; sampled prices are not executable returns.`});
            this.storage.setState({nextAt:now+86400000},'digest');
          });
        }
      }
      await this.notifications.flush();await this.pause(2000);
    }
  }
  startBackgroundLoops() {
    this.running=true;this.health.mode='live';
    this.loops=[this.enrichLoop(),this.discoveryLoop('dex',this.config.dexProfilePollMs),this.notificationLoop()];
    if(this.config.jupiterApiKey)this.loops.push(this.discoveryLoop('jupiter',this.config.jupiterPollMs),this.metadataLoop('jupiter'));
    if(this.config.heliusApiKey)this.loops.push(this.metadataLoop('helius'));
    for(const loop of this.loops)loop.catch(e=>{this.log(`Fatal worker error: ${e.message}`);process.exitCode=1;void this.stop();this.onFatal?.();});
  }
  async stop(){this.running=false;this.health.mode='stopped';this.abort.abort();await Promise.allSettled(this.loops);await this.statisticsService?.close();}
  getHealth(){if(this.health.mode==='dashboard'){const h=this.storage.getState('health');if(h.providers)return {...h,mode:'dashboard (worker snapshot)',ready:h.ready&&Date.now()-h.lastMarketAt<this.config.freshMs&&Date.now()-h.lastLoopAt<180000};}
    const now=Date.now(),active=[...this.candidates.values()].filter(x=>!x.inactive||tracking(x)||this.research.trackingPending(x.mint));
    const pending=active.filter(x=>!x.lastAttemptAt);
    return {...this.health.snapshot(this.config,this.storage.notificationStats()),scannerVersion:'0.2.9',feedEvidenceVersion:FEED_VERSION,statisticsReader:statisticsHealth(),statisticsWorker:this.statisticsService?.health()||null,research:{...this.research.stats(now),focus:{limit:Math.min(this.config.researchFocusLimit||60,Math.max(1,Math.floor(this.config.maxCandidates/5))),eligible:this.focusEligibleCount,selected:this.researchFocus.size,fastSelected:this.fastFocusSelected||0,fastAwaitingCapacity:this.fastFocusAwaiting||0,ordinaryDisplaced:this.fastFocusDisplaced||0,
      ready:[...this.researchFocus].filter(m=>{const v=this.research.describe(m,now);return v?.metrics?.ready&&v.stage!=='data unavailable';}).length}},droppedCandidates:this.droppedCandidates||0,
    decisionTrace:{writtenSinceRestart:this.storage.decisionEventsWritten||0,retentionDays:this.config.snapshotDays},
    storageWrites:this.storage.writeStats?.()||null,
    launchRegistry:this.storage.launchRegistry?.health()||null,
    snapshotArchive:{storedSinceRestart:this.snapshotCounts.stored,skippedSinceRestart:this.snapshotCounts.skipped,
      routineIntervalMs:this.config.snapshotIntervalMs,thinMarketIntervalMs:this.config.thinSnapshotIntervalMs},
    coverage:{active:active.length,neverAttempted:pending.length,oldestFirstAttemptWaitMs:Math.max(0,...pending.map(x=>now-x.firstSeenAt)),
      evictedBeforeAttempt:this.evictedBeforeAttempt||0,marketObserved:active.filter(x=>!x.stale&&now-x.marketObservedAt<=this.config.freshMs).length,
      noUsableMarket:active.filter(x=>x.marketAttemptStatus==='no-usable-market').length,marketErrors:active.filter(x=>x.marketAttemptStatus==='error').length,
      metadataEligible:active.filter(x=>this.metadataEligible(x,now)).length},
    oldestAttemptAgeMs:Math.max(0,...[...this.candidates.values()].filter(x=>!x.inactive||tracking(x)).map(x=>Date.now()-(x.lastAttemptAt||x.firstSeenAt)))};}
  getCandidates({activeOnly=false,limit=200}={}) {
    if(this.health.mode==='dashboard')this.candidates=new Map(Object.entries(this.storage.loadCandidates()));
    return [...this.candidates.values()].filter(x=>!activeOnly||!x.inactive).map(x=>({...x,research:this.research.describe(x.mint),qualification:qualify(x,this.research.describe(x.mint)),stale:x.stale||!x.marketObservedAt||Date.now()-x.marketObservedAt>this.config.freshMs,decision:describeDecision(x,this.config),decisionTimeline:x.decisionTimeline||null})).sort((a,b)=>(b.score||0)-(a.score||0)).slice(0,limit);
  }
  getAlerts(limit=200){return this.storage.readJsonl('alerts',limit).reverse();}
  getOutcomes(limit=1000){return this.storage.readJsonl('outcomes',limit);}
  getStats(now=Date.now()) {
    if(!this.statsCache||now-this.statsCache.at>30000) {
      const buckets={},entries=new Map(),outcomeRows=[];let signalEvents=0;
      for(const a of summaryEvents(this.storage,'alerts')) {signalEvents++;if(!a.legacy){const key=`${a.candidate.mint}:${a.id.split(':')[1]}`;if(!entries.has(key))entries.set(key,a);}}
      let observed=0,doubled=0,missing=0,gapped=0;const complete=new Set();
      for(const o of summaryEvents(this.storage,'outcomes')) {
        outcomeRows.push(o);
        if(o.version!=='price-v2'||o.horizon!=='60m')continue;
        complete.add(`${o.mint}:${o.alertAt}`);
        if(o.status!=='observed'){missing++;continue;}
        if(o.coverage==='gapped')gapped++;
        observed++;const hit=o.maxMultiple>=2;if(hit)doubled++;
        const score=o.score>=88?'88+':o.score>=82?'82–87':'72–81';
        const mc=o.entryMarketCap<100000?'<100k':o.entryMarketCap<250000?'100k–250k':'>=250k or unknown';
        for(const key of [`score ${score}`,`MC ${mc}`]){const b=buckets[key]||={n:0,doubles:0};b.n++;b.doubles+=Number(hit);}
      }
      this.statsCache={at:now,data:{alerts:signalEvents,uniquePaperEntries:entries.size,evaluated60m:observed,missing60m:missing,gapped60m:gapped,
        pending60m:Math.max(0,entries.size-complete.size),doubledWithin60m:doubled,doubleHitRate60m:observed?doubled/observed:null,
        conservativeObservedDoubleRate:observed+missing?doubled/(observed+missing):null,buckets,
        paperSummary:summarizeOutcomes([...entries.values()],outcomeRows,now,this.config.horizonToleranceMs),
        paperSummaryV026:summarizeOutcomes([...entries.values()].filter(a=>a.engineVersion==='0.2.6'),outcomeRows,now,this.config.horizonToleranceMs),
        qualification:qualificationSummary([...entries.values()],outcomeRows,now,this.config.horizonToleranceMs),
        paperSummaryV029:summarizeOutcomes([...entries.values()].filter(a=>a.engineVersion==='0.2.9'),outcomeRows,now,this.config.horizonToleranceMs),
        paperSummaryV028:summarizeOutcomes([...entries.values()].filter(a=>a.engineVersion==='0.2.8'),outcomeRows,now,this.config.horizonToleranceMs),
        paperSummaryV027:summarizeOutcomes([...entries.values()].filter(a=>a.engineVersion==='0.2.7'),outcomeRows,now,this.config.horizonToleranceMs),
        paperSummaryV025:summarizeOutcomes([...entries.values()].filter(a=>a.engineVersion==='0.2.5'),outcomeRows,now,this.config.horizonToleranceMs),
        paperSummaryCurrent:summarizeOutcomes([...entries.values()].filter(a=>a.engineVersion==='0.2.4'),outcomeRows,now,this.config.horizonToleranceMs)}};
    }
    if(!this.researchCache||now-this.researchCache.at>30000){
      const entries=[...summaryEvents(this.storage,'research-entries')],outcomes=[...summaryEvents(this.storage,'research-outcomes')];
      this.researchCache={at:now,data:{version:MOMENTUM_VERSION,summary:summarizeResearch(entries.filter(e=>e.version===MOMENTUM_VERSION),outcomes,now),summaryAllRetained:summarizeResearch(entries,outcomes,now),
        tokenFollowup:summarizeContinuity(entries.filter(e=>e.version===MOMENTUM_VERSION),outcomes,RESEARCH_HORIZONS,now,30000),events:this.storage.readJsonl('research-events',30).reverse()}};
    }
    return {...this.statsCache.data,research:this.researchCache.data,totalCandidates:this.candidates.size,activeCandidates:[...this.candidates.values()].filter(x=>!x.inactive).length,
      health:this.getHealth(),status:this.status.slice(-20).reverse()};
  }
}
