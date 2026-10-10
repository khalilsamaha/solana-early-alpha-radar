import {turnoverPoints} from './momentum.js';
const clamp = (n, min, max) => Math.min(max, Math.max(min, n));
const safe = (n, fallback = 0) => n !== null && n !== undefined && n !== '' && Number.isFinite(Number(n)) ? Number(n) : fallback;

export function deriveMetrics(candidate, previous = null, now = Date.now()) {
  const knownTimes = [candidate.launchAt, candidate.firstPoolAt, candidate.pairCreatedAt].filter(x => Number.isFinite(x) && x > 0);
  const createdAt = knownTimes.length ? Math.min(...knownTimes) : safe(candidate.firstSeenAt, now);
  const ageMin = Math.max(0, (now - createdAt) / 60000);
  const buys5m = safe(candidate.txns?.m5?.buys);
  const sells5m = safe(candidate.txns?.m5?.sells);
  const txns5m = buys5m + sells5m;
  const buySellRatio = sells5m > 0 ? buys5m / sells5m : (buys5m > 0 ? 99 : 0);
  const liquidity = safe(candidate.liquidityUsd);
  const volume5m = safe(candidate.volume?.m5);
  const volumeLiquidity = liquidity > 0 ? volume5m / liquidity : 0;
  let volumeAcceleration = 0;
  let txnAcceleration = 0;
  if (previous) {
    const dtMin = Math.max(0.1, (safe(candidate.observedAt, now) - safe(previous.observedAt, now)) / 60000);
    volumeAcceleration = (volume5m - safe(previous.volume?.m5)) / dtMin;
    const prevTx = safe(previous.txns?.m5?.buys) + safe(previous.txns?.m5?.sells);
    txnAcceleration = (txns5m - prevTx) / dtMin;
  }
  return { ageMin, buys5m, sells5m, txns5m, buySellRatio, liquidity, volume5m, volumeLiquidity, volumeAcceleration, txnAcceleration };
}

export function scoreCandidate(candidate, previous = null, now = Date.now(), research = null) {
  const m = deriveMetrics(candidate, previous, now);
  let score = 0;
  const reasons = [];
  const risks = [];
  const add = (pts, reason) => { score += pts; if (pts !== 0) reasons.push({ pts, reason }); };
  const penalize = (pts, reason) => { score -= pts; risks.push({ pts: -Math.abs(pts), reason }); };

  // Freshness: we care about discovering acceleration, not mature trending tokens.
  if (m.ageMin <= 3) add(15, 'extremely fresh (≤3m)');
  else if (m.ageMin <= 10) add(12, 'very fresh (≤10m)');
  else if (m.ageMin <= 20) add(8, 'fresh (≤20m)');
  else if (m.ageMin <= 60) add(3, 'still early (≤60m)');
  else penalize(6, 'older than the primary launch window');

  // Liquidity: enough to trade, but still early enough to have room.
  if (m.liquidity >= 15000 && m.liquidity <= 120000) add(14, 'healthy early liquidity');
  else if (m.liquidity > 120000 && m.liquidity <= 350000) add(10, 'strong liquidity');
  else if (m.liquidity >= 5000) add(5, 'minimum viable liquidity');
  else penalize(22, Number.isFinite(candidate.liquidityUsd)&&candidate.liquidityUsd>=0?'very thin liquidity (<$5k)':'Liquidity unknown; conservative scoring applied');

  if (m.txns5m >= 80) add(10, 'heavy 5m transaction activity');
  else if (m.txns5m >= 35) add(7, 'strong 5m transaction activity');
  else if (m.txns5m >= 15) add(3, 'emerging 5m activity');
  else penalize(4, 'weak 5m transaction activity');

  if (m.sells5m === 0 && m.buys5m >= 10) penalize(10, 'no sells observed despite many buys');
  else if (m.buySellRatio >= 1.5 && m.buySellRatio <= 5) add(8, 'buy pressure materially exceeds sell pressure');
  else if (m.buySellRatio >= 1.15) add(4, 'positive buy/sell balance');
  else if (m.buySellRatio < 0.75 && m.txns5m >= 15) penalize(7, 'sell pressure dominates');

  if (research) {
    const pts=turnoverPoints(m.volumeLiquidity);
    if(pts>=0)add(pts,'Gradual turnover contribution (experimental)');
    else penalize(-pts,'Extreme turnover (experimental gradual penalty)');
  } else if (m.volumeLiquidity >= 0.35 && m.volumeLiquidity <= 4) add(9, 'high turnover relative to liquidity');
  else if (m.volumeLiquidity > 4) penalize(3, 'extreme turnover requires manipulation review');
  else if (m.volumeLiquidity >= 0.12) add(5, 'useful turnover relative to liquidity');
  else if (m.volume5m > 0) add(1, 'some recent volume');

  const p5 = safe(candidate.priceChange?.m5);
  if (p5 >= 8 && p5 <= 65) add(8, 'constructive 5m momentum');
  else if (p5 > 65 && p5 <= 180) add(4, 'very strong but extended 5m momentum');
  else if (p5 > 180) penalize(4, 'parabolic 5m move may be late');
  else if (p5 <= -20) penalize(7, 'sharp negative 5m momentum');

  if(research) {
    m.volumeAcceleration=research.r60?.volumeDeltaPerMinute??0;
    m.txnAcceleration=research.r60?.transactionsDeltaPerMinute??0;
  }
  if (m.volumeAcceleration > 5000) add(6, research?'Rolling-volume growth over approximately 60s':'5m volume is accelerating');
  else if (m.volumeAcceleration > 1000) add(3, research?'Rolling-volume growth over approximately 60s':'5m volume is beginning to accelerate');
  if (m.txnAcceleration > 8) add(5, research?'Rolling-transaction growth over approximately 60s':'transaction rate is accelerating');
  else if (m.txnAcceleration > 2) add(2, research?'Rolling-transaction growth over approximately 60s':'transaction rate is improving');

  const organic = safe(candidate.organicScore, -1);
  if (organic >= 70) add(14, 'high Jupiter organic score');
  else if (organic >= 50) add(9, 'good Jupiter organic score');
  else if (organic >= 30) add(4, 'moderate Jupiter organic score');
  else if (organic >= 0 && organic < 15) penalize(6, 'very low Jupiter organic score');

  const holders = safe(candidate.holderCount);
  if (holders >= 300) add(7, 'reported holder count ≥300 (growth unverified)');
  else if (holders >= 100) add(5, 'meaningful holder count');
  else if (holders >= 35) add(2, 'holder base forming');

  const marketCap = safe(candidate.marketCap || candidate.fdv);
  if (marketCap >= 20000 && marketCap <= 250000) add(8, 'early market-cap zone');
  else if (marketCap > 250000 && marketCap <= 750000) add(4, 'still below large-cap discovery zone');
  else if (marketCap > 2000000) penalize(3, 'already above $2m market cap');

  const socials = safe(candidate.socialCount);
  if (socials >= 2) add(4, 'multiple project/social links');
  else if (socials === 1) add(2, 'project/social link present');

  if (candidate.auditIsSus === true) penalize(35, 'Jupiter audit marks token suspicious');
  if (candidate.mintAuthority === null) add(4, 'mint authority revoked');
  else if (candidate.mintAuthority) penalize(14, 'mint authority still active');
  if (candidate.freezeAuthority === null) add(4, 'freeze authority revoked');
  else if (candidate.freezeAuthority) penalize(18, 'freeze authority still active');

  const top10 = safe(candidate.top10Pct, -1);
  if (top10 > 50) penalize(20, 'top-10 token-account concentration above 50%');
  else if (top10 > 35) penalize(10, 'top-10 token-account concentration above 35%');

  const creator = candidate.creatorStats;
  if (creator?.resolved >= 3) {
    if (creator.hitRate >= 0.35) add(6, 'creator has repeated historical winners');
    if (creator.rugRate >= 0.5) penalize(18, 'creator history has a high failure/rug rate');
  }

  if (safe(candidate.boostsActive) > 0) risks.push({ pts: 0, reason: 'DEX Screener boosts active; do not treat trending visibility as organic proof' });

  // Hard caps prevent a token with severe trust failures from scoring as excellent.
  if (candidate.auditIsSus === true) score = Math.min(score, 49);
  if (m.liquidity < 2500) score = Math.min(score, 45);
  if (candidate.freezeAuthority || candidate.mintAuthority || top10 > 50) score = Math.min(score, 55);
  if (candidate.mintAuthority === undefined || candidate.freezeAuthority === undefined || top10 < 0) {
    risks.push({pts:0, reason:'Security checks incomplete; authorities or token-account concentration unknown'});
    score = Math.min(score, 57);
  }
  if (!(candidate.launchAt || candidate.firstPoolAt || candidate.pairCreatedAt)) risks.push({pts:0, reason:'Launch age unknown; age is time since first discovery'});
  const metadataExtensions=new Set(['metadataPointer','tokenMetadata']);
  const extensions=candidate.extensions;
  if (extensions !== undefined && (!Array.isArray(extensions) || extensions.some(x=>!metadataExtensions.has(x)))) {
    risks.push({pts:0,reason:'Non-metadata or unknown token extensions require review'});
    score = Math.min(score, 55);
  } else if (extensions?.length) {
    risks.push({pts:0,reason:'Metadata extensions present; metadata identity and update authority are not verified'});
  }

  score = clamp(Math.round(score), 0, 100);
  const band = score >= 88 ? 'exceptional' : score >= 82 ? 'strong' : score >= 72 ? 'watch' : score >= 58 ? 'developing' : 'low';
  return { score, band, reasons: reasons.sort((a,b)=>b.pts-a.pts), risks, metrics: m };
}
