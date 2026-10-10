// Keep summary rows small before collecting them. Full event payloads stay on disk.
import {getHeapStatistics} from 'node:v8';
export const STATS_MEMORY_VERSION='stats-memory-1.0.0';
const pick=(row,keys)=>Object.fromEntries(keys.filter(k=>Object.hasOwn(row,k)).map(k=>[k,row[k]]));
export function compactSummaryRow(kind,row) {
  switch(kind) {
    case 'alerts': {
      const out=pick(row,['id','legacy','engineVersion']);
      if(row.candidate)out.candidate=pick(row.candidate,['mint']);
      if(row.qualification)out.qualification=pick(row.qualification,['version','disposition','state']);
      return out;
    }
    case 'outcomes': return pick(row,['version','mint','alertAt','horizon','status','coverage','multiple','maxMultiple','score','entryMarketCap']);
    case 'research-entries': return pick(row,['id','at','version','cohort']);
    case 'research-outcomes': {
      const out=pick(row,['entryId','horizon','status','returnPct','coverage','reasonCode']);
      if(row.tokenFollowup)out.tokenFollowup=pick(row.tokenFollowup,['status','returnPct','coverage','basis']);
      return out;
    }
    default: throw new Error('Unsupported summary event kind');
  }
}
export function* summaryEvents(storage,kind) {
  // The storage iterator parses one event at a time. Never collect raw evidence.
  for(const row of storage.events(kind))yield compactSummaryRow(kind,row);
}
export function statisticsHealth() {
  const m=process.memoryUsage();
  return {version:STATS_MEMORY_VERSION,heapUsedBytes:m.heapUsed,heapLimitBytes:getHeapStatistics().heap_size_limit,rssBytes:m.rss};
}
