// Run from the project directory with Node 24:
// node --env-file=.env scripts/radar-diagnostics.mjs
// Read-only: calls the local dashboard API. Does not print credentials or raw logs.
const number = (name, fallback) => Number(process.env[name] || fallback);
const settings = {
  maxCandidates: number('MAX_CANDIDATES', 1000),
  batchSize: number('BATCH_SIZE', 30),
  minimumMarketRevisitMs: number('ENRICH_INTERVAL_MS', 15000),
  marketBatchPauseMs: number('MARKET_BATCH_PAUSE_MS', 1000),
  metadataPauseMs: number('METADATA_PAUSE_MS', 2000),
  marketFreshMs: number('FRESH_MS', 120000),
  securityTtlMs: number('SECURITY_TTL_MS', 300000),
  alertScore: number('ALERT_SCORE', 72),
  dexRpm: number('DEX_RPM', 120),
  jupiterRpm: number('JUPITER_RPM', 30),
  heliusRpm: number('HELIUS_RPM', 60),
};
const base = `http://127.0.0.1:${number('DASHBOARD_PORT', 8787)}`;
const token = process.env.DASHBOARD_TOKEN;
const ageSeconds = (time, now) => Number.isFinite(time) && time > 0 ? Math.max(0, Math.round((now-time)/1000)) : null;

async function read(route) {
  const response = await fetch(base + route, {
    headers: {authorization: `Bearer ${token}`}, signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error(`Local API returned HTTP ${response.status}`);
  return response.json();
}

try {
  if (!token) throw new Error('DASHBOARD_TOKEN missing; run from the project directory with --env-file=.env');
  const [health, stats, rows] = await Promise.all([
    read('/api/health'), read('/api/stats'), read('/api/candidates?limit=1000'),
  ]);
  const now = Date.now();
  const active = rows.filter(row => !row.inactive);
  const freshMarket = row => !row.stale && row.marketObservedAt > 0 && now-row.marketObservedAt <= settings.marketFreshMs;
  const freshSecurity = row => row.securityCheckedAt > 0 && now-row.securityCheckedAt <= settings.securityTtlMs;
  const completeSecurity = row => freshSecurity(row) && row.mintAuthority !== undefined && row.freezeAuthority !== undefined && Number.isFinite(row.top10Pct);
  const ages = active.filter(row => row.lastAttemptAt > 0).map(row => ageSeconds(row.lastAttemptAt,now)).sort((a,b)=>a-b);
  const percentile = p => ages.length ? ages[Math.ceil(p*ages.length)-1] : null;
  const risks = {};
  for (const row of active.filter(freshMarket)) {
    for (const risk of row.scoreRisks || []) risks[risk.reason] = (risks[risk.reason] || 0) + 1;
  }
  const report = {
    capturedAt: new Date(now).toISOString(), settings,
    service: {
      scannerVersion: health.scannerVersion || 'pre-0.2.1',
      ready: health.ready, uptimeSeconds: health.uptimeSeconds,
      lastMarketAgeSeconds: ageSeconds(health.lastMarketAt,now),
      lastLoopAgeSeconds: ageSeconds(health.lastLoopAt,now),
      oldestAttemptAgeSeconds: Math.round((health.oldestAttemptAgeMs || 0)/1000),
      droppedOrEvictedCandidatesSinceRestart: health.droppedCandidates || 0,
    },
    providers: Object.fromEntries(Object.entries(health.providers || {}).map(([name,p]) => [name,{
      state:p.state, consecutiveFailures:p.failures, recordedSuccessesSinceRestart:p.requests,
      lastSuccessAgeSeconds:ageSeconds(p.lastSuccessAt,now),
    }])),
    storageWrites:health.storageWrites||null,
    research:{...health.research,tokenFollowup:stats.research?.tokenFollowup||null,cohortVersion:stats.research?.version||null,summary:stats.research?.summary||null,allRetainedSummary:stats.research?.summaryAllRetained||null},
    qualification:stats.qualification||null,
    decisionTrace:health.decisionTrace||null,
    snapshotArchive: health.snapshotArchive || null,
    fullQueueCoverage: health.coverage || null,
    coverage: {
      totalCandidates:stats.totalCandidates, returnedCandidates:rows.length,
      sampleTruncated:stats.totalCandidates>rows.length, activeInSample:active.length,
      neverAttempted:active.filter(row=>!row.lastAttemptAt).length,
      neverHadMarketData:active.filter(row=>!row.marketObservedAt).length,
      freshMarket:active.filter(freshMarket).length,
      freshCompleteSecurity:active.filter(completeSecurity).length,
      freshMarketAndCompleteSecurity:active.filter(row=>freshMarket(row)&&completeSecurity(row)).length,
      freshMarketAtAlertScore:active.filter(row=>freshMarket(row)&&row.score>=settings.alertScore).length,
      attemptedCandidateAgeSeconds:{median:percentile(0.5),p95:percentile(0.95),max:ages.at(-1) ?? null},
    },
    paperResults: {allRetained:stats.paperSummary||null,newV024Entries:stats.paperSummaryCurrent||null,newV025Entries:stats.paperSummaryV025||null,newV026Entries:stats.paperSummaryV026||null,newV027Entries:stats.paperSummaryV027||null,newV028Entries:stats.paperSummaryV028||null,newV029Entries:stats.paperSummaryV029||null},
    decisionCoverage: {withTimeline:rows.filter(r=>r.decisionTimeline).length,unknownLiquidity:active.filter(r=>r.decision?.liquidity==='unknown').length},
    signals: {
      alertEvents:stats.alerts, uniquePaperEntries:stats.uniquePaperEntries,
      observed60m:stats.evaluated60m, missing60m:stats.missing60m, gapped60m:stats.gapped60m,
      notificationQueue:health.notifications,
    },
    commonRisksAmongFreshMarketCandidates:Object.entries(risks).sort((a,b)=>b[1]-a[1]).slice(0,8),
    highestStoredScores:active.filter(row=>Number.isFinite(row.score)).sort((a,b)=>b.score-a.score).slice(0,5).map(row=>({
      mint:row.mint, score:row.score, qualification:row.qualification||null, freshMarket:freshMarket(row), freshCompleteSecurity:completeSecurity(row),
      top10TokenAccountsPct:row.top10Pct ?? null, extensions:row.extensions || [],
      mintAuthorityActive:row.mintAuthority===undefined?null:row.mintAuthority!==null,
      freezeAuthorityActive:row.freezeAuthority===undefined?null:row.freezeAuthority!==null,
      marketAgeSeconds:ageSeconds(row.marketObservedAt,now),
      risks:(row.scoreRisks || []).map(risk=>risk.reason),
    })),
  };
  console.log(JSON.stringify(report,null,2));
} catch (error) {
  const safe = error.message?.startsWith('Local API returned') || error.message?.startsWith('DASHBOARD_TOKEN missing');
  console.error(safe ? error.message : 'Diagnostic failed. Check that the local radar is running and the dashboard port is correct.');
  process.exitCode = 1;
}
