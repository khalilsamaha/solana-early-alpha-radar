import {createHash} from 'node:crypto';
export const FEED_VERSION='feed-provenance-1';
const number=v=>Number.isFinite(v)?v:null;
// Response headers describe HTTP caching, never the age of a market price.
export function transportEvidence(response,queuedAt,requestStartedAt,headersAt,bodyAt) {
 const rawAge=response.headers?.get('age'),age=typeof rawAge==='string'&&/^\d{1,10}$/.test(rawAge)?Number(rawAge):null;
 const rawDate=response.headers?.get('date'),date=typeof rawDate==='string'&&rawDate.length<=64?Date.parse(rawDate):NaN;
 const rawCache=response.headers?.get('cf-cache-status')?.toUpperCase();
 const cfCacheStatus=['HIT','MISS','DYNAMIC','BYPASS','EXPIRED','STALE','UPDATING','REVALIDATED'].includes(rawCache)?rawCache:null;
 const clocksOrdered=[queuedAt,requestStartedAt,headersAt,bodyAt].every(Number.isFinite)&&queuedAt<=requestStartedAt&&requestStartedAt<=headersAt&&headersAt<=bodyAt;
 return {queuedAt,requestStartedAt,headersAt,bodyAt,clocksOrdered,httpStatus:response.status,
  queueMs:clocksOrdered?requestStartedAt-queuedAt:null,headersMs:clocksOrdered?headersAt-requestStartedAt:null,
  bodyMs:clocksOrdered?bodyAt-headersAt:null,httpAgeSeconds:age,httpDateAt:number(date),cfCacheStatus,providerPriceAt:null};
}
export function attachFeed(market,transport,endpoint) {
 if(!market)return market;
 return {...market,feedEvidence:transport?{version:FEED_VERSION,provider:'dexscreener',endpoint,
  pairAddress:market.pairAddress,priceUsd:market.priceUsd,...transport}:null};
}
export function applyFeed(previous,market,appliedAt) {
 const feed=market.feedEvidence;
 if(feed?.version!==FEED_VERSION)return null;
 const values=[market.priceUsd,market.liquidityUsd,market.volume?.m5,market.txns?.m5?.buys,market.txns?.m5?.sells].map(number);
 const valuesSha256=createHash('sha256').update(JSON.stringify(values)).digest('hex');
 const old=previous?.feedEvidence;
 const continuous=old?.version===FEED_VERSION&&old.pairAddress===market.pairAddress&&old.clocksOrdered&&feed.clocksOrdered
  &&feed.bodyAt>old.bodyAt&&feed.bodyAt-old.bodyAt<=45000;
 const samePrice=continuous&&old.priceUsd===market.priceUsd,sameValues=continuous&&old.valuesSha256===valuesSha256;
 const ordered=feed.clocksOrdered&&Number.isFinite(appliedAt)&&appliedAt>=feed.bodyAt;
 return {...feed,appliedAt,clocksOrdered:ordered,applyDelayMs:ordered?appliedAt-feed.bodyAt:null,valuesSha256,
  previousBodyAt:continuous?old.bodyAt:null,comparison:continuous?'same-pool-within-45s':'new-or-gapped',
  repeatedPriceCount:samePrice?Math.min(1000000,(old.repeatedPriceCount||0)+1):0,
  priceUnchangedSince:samePrice?old.priceUnchangedSince:feed.bodyAt,
  repeatedValuesCount:sameValues?Math.min(1000000,(old.repeatedValuesCount||0)+1):0,
  valuesUnchangedSince:sameValues?old.valuesUnchangedSince:feed.bodyAt};
}
