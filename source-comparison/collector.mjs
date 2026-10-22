import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {DatabaseSync} from 'node:sqlite';
import {address, amount, USDC, pause, usdcChange} from '../quote-observer/quote-check.mjs';
import {PROVIDERS, requestPrice} from './providers.mjs';

export const LIMITS = Object.freeze({durationMs: 1800000, maxWatches: 3, maxRequests: 24,
  providerSpacingMs: 10000, maxQuoteAgeMs: 5000, pollMs: 1000, maxProbeBytes: 65536});
const COHORTS = ['baseline', 'early-activity', 'fast30-shadow'];
const KEYS = ['buy', 'sell:30000', 'sell:60000', 'sell:120000'];
const stamp = n => Number.isSafeInteger(n) && n > 0;
const key = o => o?.leg === 'buy' ? 'buy' : o?.leg === 'sell' && [30000,60000,120000].includes(o.targetOffsetMs) ? `sell:${o.targetOffsetMs}` : null;
export function identity(file) { const s = fs.statSync(file); return `${s.dev}:${s.ino}`; }
export class Ledger {
  constructor(file) {
    this.file = file; this.identity = identity(file);
    this.db = new DatabaseSync(file, {readOnly: true});
    this.db.exec('PRAGMA query_only=ON; PRAGMA busy_timeout=200; PRAGMA cache_size=-2048; PRAGMA mmap_size=0');
    this.sourceIdentity = JSON.parse(this.db.prepare("SELECT v FROM meta WHERE k='sourceIdentity'").get()?.v || 'null');
    if (typeof this.sourceIdentity !== 'string' || !/^\d+:\d+$/.test(this.sourceIdentity)) { this.close(); throw Error('Invalid source identity'); }
  }
  check() {
    if (identity(this.file) !== this.identity) throw Error('Ledger replaced');
    const source = JSON.parse(this.db.prepare("SELECT v FROM meta WHERE k='sourceIdentity'").get()?.v || 'null');
    if (source !== this.sourceIdentity) throw Error('Source replaced');
  }
  tail() { this.check(); return this.db.prepare('SELECT COALESCE(MAX(seq),0) AS seq FROM probes').get().seq; }
  rows(after) {
    this.check();
    return this.db.prepare('SELECT seq, CASE WHEN length(CAST(data AS BLOB)) <= ? THEN data ELSE NULL END AS data FROM probes WHERE seq > ? ORDER BY seq LIMIT 21').all(LIMITS.maxProbeBytes, after);
  }
  get(seq) {
    this.check();
    return this.db.prepare('SELECT seq, CASE WHEN length(CAST(data AS BLOB)) <= ? THEN data ELSE NULL END AS data FROM probes WHERE seq = ?').get(LIMITS.maxProbeBytes, seq);
  }
  close() { this.db.close(); }
}
export function probe(row) {
  let p; try { p = JSON.parse(row?.data); } catch { return null; }
  const s = p?.signal;
  // The observer inserts a brief placeholder before its first asynchronous save.
  // Accept only its empty running form; this cannot authorize any price request.
  if (p?.mode === undefined && p?.state === 'running' && Array.isArray(p.observations) && p.observations.length === 0)
    p = {...p, mode: 'automatic-signal-watch', mint: s?.mint, baseMint: USDC, inputAtomic: '10000000'};
  if (!Number.isSafeInteger(row?.seq) || row.seq < 1 || s?.seq !== row.seq ||
      !address(s.mint) || !address(s.originalPool) || p.mint !== s.mint ||
      !COHORTS.includes(s.cohort) || !stamp(s.signalAt) || !stamp(p.startedAt) ||
      p.mode !== 'automatic-signal-watch' || p.inputAtomic !== '10000000' || p.baseMint !== USDC ||
      !Array.isArray(p.observations) || p.observations.length > 5) return null;
  return p;
}
export function quoteEvidence(o, p) {
  const buy = p.observations.find(x => x.leg === 'buy');
  const buyValid = buy?.status === 'quoted' && buy.inputMint === USDC && buy.outputMint === p.mint &&
    buy.inAmount === p.inputAtomic && amount(buy.outAmount) && buy.transactionRequested === false && buy.executionVerified === false &&
    stamp(buy.startedAt) && stamp(buy.receivedAt) && buy.receivedAt >= buy.startedAt;
  const valid = buyValid && o.status === 'quoted' && amount(o.outAmount) &&
    o.inputMint === (o.leg === 'buy' ? USDC : p.mint) && o.outputMint === (o.leg === 'buy' ? p.mint : USDC) &&
    o.inAmount === (o.leg === 'buy' ? p.inputAtomic : buy.outAmount) && o.transactionRequested === false && o.executionVerified === false;
  const clocks = stamp(o.startedAt) && stamp(o.receivedAt) && o.receivedAt >= o.startedAt;
  return {key: key(o), status: valid && clocks ? 'validated-quote' : 'quote-failed-or-invalid',
    startedAt: stamp(o.startedAt) ? o.startedAt : null, receivedAt: stamp(o.receivedAt) ? o.receivedAt : null,
    httpStatus: Number.isInteger(o.httpStatus) && o.httpStatus >= 100 && o.httpStatus <= 599 ? o.httpStatus : null,
    inAmount: valid ? o.inAmount : null, outAmount: valid ? o.outAmount : null,
    quotedUsdcChangePct: valid && o.leg === 'sell' ? usdcChange(o.outAmount, p.inputAtomic) : null,
    tokenPools: Array.isArray(o.routePlan) ? [...new Set(o.routePlan.filter(r => r.inputMint === p.mint || r.outputMint === p.mint).map(r => r.pool).filter(address))].slice(0,12) : [],
    routePlanTruncated: o.routePlanTruncated !== false};
}
export function summarize(watches) {
  const result = {watches: watches.length, points: 0, pairedPrices: 0, priceDisagreementsAbove10Pct: 0, states: {}};
  const finite = x => Number.isFinite(x) ? x : null;
  for (const w of watches) for (const point of w.points) {
    result.points++; result.states[point.state] = (result.states[point.state] || 0) + 1;
    const entry = w.points.find(x => x.key === 'buy');
    for (const price of point.prices || []) {
      const base = entry?.prices?.find(x => x.provider === price.provider);
      price.changeFromBuyPricePct = price.status === 'price' && base?.status === 'price' ? finite((price.priceUsd / base.priceUsd - 1) * 100) : null;
      price.quoteMinusPriceChangePp = typeof point.quote?.quotedUsdcChangePct === 'number' && price.changeFromBuyPricePct !== null
        ? finite(point.quote.quotedUsdcChangePct - price.changeFromBuyPricePct) : null;
    }
    const [d,g] = point.prices || [];
    if (d?.status === 'price' && g?.status === 'price') {
      result.pairedPrices++;
      point.geckoVsDexPct = finite((g.priceUsd / d.priceUsd - 1) * 100);
      if (Math.abs(point.geckoVsDexPct) > 10) result.priceDisagreementsAbove10Pct++;
    }
  }
  return result;
}
export async function collect(ledger, {now = Date.now, monotonic = () => performance.now(), sleep = pause,
  request = requestPrice, signal, progress = () => {}} = {}) {
  const startedAt = now(), startedClock = monotonic(), tail = ledger.tail();
  const report = {format: 'source-comparison-1', startedAt, sourceIdentity: ledger.sourceIdentity,
    initialTail: tail, limits: LIMITS, requests: 0, watches: [], exclusions: {}, state: 'collecting',
    sampling: 'First new observer watch while idle; existing watches skipped; not random or cohort-balanced.',
    limitations: ['Price responses follow quote receipts; actual clocks are retained, not simultaneous observations.',
      'GeckoTerminal public endpoints document a one-minute cache. HTTP receipt time is not price time.',
      'DEX base mint must match; Gecko base or quote orientation is explicitly bound to the same pool and mint.',
      'Missing, failed, delayed and interrupted evidence is not a zero return.',
      'Prices and fixed-quantity quotes are not fills, net profit, or proof of sellability. No new quote requests or trades.']};
  const exclude = reason => { report.exclusions[reason] = (report.exclusions[reason] || 0) + 1; };
  let cursor = tail, active = null, lastRequestClock = -Infinity, stop = null;
  try {
    while (!signal?.aborted && monotonic() - startedClock < LIMITS.durationMs && !stop) {
      if (ledger.tail() < cursor) throw Error('Ledger rewound');
      const rows = ledger.rows(cursor);
      if (rows.length > 20) { stop = 'source-backlog'; break; }
      for (const row of rows) {
        cursor = row.seq;
        if (active) { exclude('observer-watch-arrived-while-busy'); continue; }
        const p = probe(row);
        if (!p) { exclude('invalid-or-oversized-probe'); continue; }
        if (p.startedAt < startedAt || now() < p.startedAt || now() - p.startedAt > 15000) { exclude('not-new-and-timely'); continue; }
        active = {seq: row.seq, cohort: p.signal.cohort, mint: p.mint, pool: p.signal.originalPool,
          signalAt: p.signal.signalAt, quoteWatchStartedAt: p.startedAt, selectedAt: now(),
          observerVersion: typeof p.format === 'string' && /^quote-observer-[0-9.]+$/.test(p.format) ? p.format : null,
          samplingPolicy: ['three-cohort-budgets-v3'].includes(p.samplingPolicy) ? p.samplingPolicy : 'unknown',
          state: 'observing', points: []};
        report.watches.push(active); progress(`Selected watch ${report.watches.length}/${LIMITS.maxWatches}.`);
      }
      if (active) {
        const p = probe(ledger.get(active.seq));
        if (!p || p.mint !== active.mint || p.signal.originalPool !== active.pool || p.startedAt !== active.quoteWatchStartedAt) { stop = 'selected-probe-changed-or-unavailable'; break; }
        const seen = new Set(active.points.map(x => x.key));
        for (const o of p.observations) {
          const k = key(o); if (!k || seen.has(k)) continue;
          seen.add(k);
          const q = quoteEvidence(o, p), point = {key: k, readAt: now(), quote: q, prices: []};
          active.points.push(point);
          if (q.status !== 'validated-quote') { point.state = 'quote-failed-or-invalid'; continue; }
          const age = now() - q.receivedAt;
          if (age < 0 || age > LIMITS.maxQuoteAgeMs) { point.state = 'quote-receipt-not-timely'; continue; }
          if (monotonic() - lastRequestClock < LIMITS.providerSpacingMs) { point.state = 'provider-spacing-skip'; continue; }
          if (monotonic() - startedClock >= LIMITS.durationMs || signal?.aborted) { point.state = 'run-ended'; break; }
          if (report.requests + 2 > LIMITS.maxRequests) { point.state = 'request-cap'; stop = 'request-cap'; break; }
          lastRequestClock = monotonic(); report.requests += 2; point.state = 'sampled';
          point.prices = await Promise.all(PROVIDERS.map(async provider => ({provider,
            ...await request(provider, active.pool, active.mint, {now, signal})})));
          for (const price of point.prices) price.quoteReceiptToRequestMs = price.startedAt - q.receivedAt;
          if (point.prices.some(x => ['rate-limited','access-denied'].includes(x.status))) { stop = 'provider-halt'; break; }
        }
        if (!stop && (p.state !== 'running' || now() - active.quoteWatchStartedAt > 160000)) {
          active.state = p.state !== 'running' ? 'watch-ended' : 'watch-deadline';
          for (const k of KEYS) if (!active.points.some(x => x.key === k)) active.points.push({key: k, state: 'observation-unavailable', prices: []});
          active = null;
          if (report.watches.length >= LIMITS.maxWatches) stop = 'watch-cap';
        }
      }
      if (!stop) await sleep(LIMITS.pollMs, signal);
    }
    report.state = stop || (monotonic() - startedClock >= LIMITS.durationMs ? 'duration-ended' : 'interrupted');
  } catch { report.state = 'source-error'; }
  if (active) {
    active.state = report.state;
    for (const k of KEYS) if (!active.points.some(x => x.key === k)) active.points.push({key: k, state: 'run-ended-before-observation', prices: []});
  }
  report.finishedAt = now(); report.elapsedMs = Math.round(monotonic() - startedClock);
  report.summary = summarize(report.watches);
  return report;
}
async function main() {
  if (process.argv.length !== 2) throw Error('No arguments accepted');
  const config = JSON.parse(fs.readFileSync('/etc/solana-radar-quotes.json', 'utf8'));
  if (typeof config.reports !== 'string' || !path.isAbsolute(config.reports)) throw Error('Invalid ledger configuration');
  const ledger = new Ledger(path.join(config.reports, 'observer.sqlite'));
  const controller = new AbortController(); const stop = () => controller.abort();
  process.on('SIGINT', stop); process.on('SIGTERM', stop);
  const timer = setTimeout(stop, LIMITS.durationMs);
  try {
    console.error('Public price comparison: up to 30 minutes, 3 new watches, 24 GET requests. No credentials or trades.');
    const r = await collect(ledger, {signal: controller.signal, progress: x => console.error(x)});
    process.stdout.write(JSON.stringify(r) + '\n');
    console.error(`Finished: ${r.state}; watches=${r.watches.length}; paired prices=${r.summary.pairedPrices}; requests=${r.requests}.`);
  } finally { clearTimeout(timer); ledger.close(); process.off('SIGINT', stop); process.off('SIGTERM', stop); }
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(() => {
  console.error('Comparison could not start. Check installed observer configuration and ledger permissions.'); process.exitCode = 1;
});
