// Exact-pool, public GET-only corroboration. Neither source is a price oracle.
import {address} from '../quote-observer/quote-check.mjs';
export const PROVIDERS = ['dexscreener', 'geckoterminal'];
const number = x => (typeof x === 'number' || (typeof x === 'string' && /^\d+(\.\d+)?([eE][+-]?\d+)?$/.test(x))) && Number.isFinite(Number(x)) && Number(x) > 0 ? Number(x) : null;
export function endpoint(provider, pool) {
  if (!PROVIDERS.includes(provider) || !address(pool)) throw Error('Invalid request');
  return provider === 'dexscreener'
    ? `https://api.dexscreener.com/latest/dex/pairs/solana/${pool}`
    : `https://api.geckoterminal.com/api/v2/networks/solana/pools/${pool}`;
}
export function parsePrice(provider, body, pool, mint) {
  let price, orientation;
  if (provider === 'dexscreener') {
    const rows = Array.isArray(body?.pairs) ? body.pairs.filter(p => p?.chainId === 'solana' && p.pairAddress === pool) : [];
    if (rows.length !== 1 || rows[0].baseToken?.address !== mint) return {status: 'pool-or-base-mint-unavailable'};
    price = rows[0].priceUsd; orientation = 'base';
  } else if (provider === 'geckoterminal') {
    const p = body?.data;
    if (p?.type !== 'pool' || p.id !== `solana_${pool}` || p.attributes?.address !== pool) return {status: 'pool-unavailable'};
    const base = p.relationships?.base_token?.data?.id === `solana_${mint}`;
    const quote = p.relationships?.quote_token?.data?.id === `solana_${mint}`;
    if (base === quote) return {status: 'mint-unavailable-or-ambiguous'};
    orientation = base ? 'base' : 'quote';
    price = p.attributes[`${orientation}_token_price_usd`];
  } else throw Error('Unknown provider');
  const priceUsd = number(price);
  return priceUsd === null ? {status: 'price-unavailable'} : {status: 'price', priceUsd, orientation, providerPriceAt: null};
}
export async function requestPrice(provider, pool, mint, {fetchFn = fetch, now = Date.now, signal} = {}) {
  const url = endpoint(provider, pool);
  if (!address(mint)) throw Error('Invalid mint');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);
  const timing = {startedAt: now(), providerPriceAt: null};
  let reader;
  try {
    const response = await fetchFn(url, {method: 'GET', redirect: 'error',
      signal: signal ? AbortSignal.any([signal, controller.signal]) : controller.signal,
      headers: {accept: provider === 'geckoterminal' ? 'application/json;version=20230203' : 'application/json'}});
    timing.headersAt = now(); timing.httpStatus = response.status;
    const age = response.headers.get('age'), cache = response.headers.get('cf-cache-status');
    timing.httpAgeSeconds = /^\d{1,10}$/.test(age || '') ? Number(age) : null;
    timing.cacheStatus = ['HIT','MISS','DYNAMIC','BYPASS','EXPIRED','STALE','REVALIDATED','UPDATING'].includes(cache) ? cache : null;
    const date = response.headers.get('date');
    timing.httpDateAt = date && date.length <= 64 && Number.isFinite(Date.parse(date)) ? Date.parse(date) : null;
    if (!response.ok) {
      await response.body?.cancel();
      return {...timing, receivedAt: now(), status: response.status === 429 ? 'rate-limited' : [401,403].includes(response.status) ? 'access-denied' : 'http-error'};
    }
    reader = response.body.getReader();
    const chunks = []; let size = 0;
    while (true) {
      const {done, value} = await reader.read(); if (done) break;
      size += value.length;
      if (size > 262144) { controller.abort(); await reader.cancel(); return {...timing, receivedAt: now(), status: 'response-too-large'}; }
      chunks.push(value);
    }
    const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    return {...timing, receivedAt: now(), ...parsePrice(provider, body, pool, mint)};
  } catch {
    return {...timing, receivedAt: now(), status: signal?.aborted ? 'interrupted' : controller.signal.aborted ? 'timeout' : 'network-or-json-error'};
  } finally { clearTimeout(timer); reader?.releaseLock(); }
}
