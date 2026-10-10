// Read-only local evidence. No API calls, candidate insertion, notifications, or trades.
import {DatabaseSync} from 'node:sqlite';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {validSolanaAddress,tokenLinks} from '../public/token-links.js';
export function auditToken(db,mint,now=Date.now()) {
  if(!validSolanaAddress(mint))throw new Error('Supply a Solana mint address, not a token name or URL.');
  const stored=db.prepare('SELECT data FROM candidates WHERE mint=?').get(mint);
  const c=stored?JSON.parse(stored.data):null;
  const state=db.prepare('SELECT data FROM kv WHERE key=?').get(`paper:${mint}`);
  const paper=state?JSON.parse(state.data):{};
  const events=db.prepare(`SELECT kind,COUNT(*) AS count,MIN(at) AS firstAt,MAX(at) AS lastAt FROM events
    WHERE kind IN ('snapshots','alerts','outcomes','exit-alerts','decisions')
      AND (json_extract(data,'$.mint')=? OR json_extract(data,'$.candidate.mint')=?)
    GROUP BY kind`).all(mint,mint);
  const trace=db.prepare(`SELECT data FROM events WHERE kind='decisions'
    AND json_extract(data,'$.mint')=? ORDER BY at DESC,seq DESC LIMIT 200`).all(mint).map(r=>JSON.parse(r.data)).reverse();
  const deliveries=db.prepare(`SELECT id,at,status,attempts,delivered_at FROM outbox
    WHERE json_extract(payload,'$.candidate.mint')=? ORDER BY at DESC LIMIT 100`).all(mint).reverse();
  const iso=at=>Number.isFinite(at)?new Date(at).toISOString():null;
  const age=at=>Number.isFinite(at)?Math.max(0,Math.round((now-at)/1000)):null;
  return {
    mint,network:'solana',capturedAt:iso(now),currentlyRetained:Boolean(c),
    current:c?{
      symbol:c.symbol??null,name:c.tokenName??null,inactive:Boolean(c.inactive),
      hiddenByActiveOnlyFilter:Boolean(c.inactive),sources:c.discoverySources||[],
      firstSeenAt:iso(c.firstSeenAt),lastDiscoveryAt:iso(c.lastDiscoveryAt),
      launchAt:iso(c.launchAt),firstPoolAt:iso(c.firstPoolAt),pairCreatedAt:iso(c.pairCreatedAt),
      lastAttemptAgeSeconds:age(c.lastAttemptAt),lastMarketAgeSeconds:age(c.marketObservedAt),
      marketAttemptStatus:c.marketAttemptStatus||null,nextMarketAttemptAt:iso(c.nextMarketAttemptAt),
      score:c.score??null,storedStaleFlag:Boolean(c.stale),
      securityAgeSeconds:age(c.securityCheckedAt),risks:(c.scoreRisks||[]).map(r=>r.reason),
    }:null,
    archivedPaperEntryAt:iso(paper.paperEntry?.at),
    decisionTimeline:c?.decisionTimeline||paper.decisionTimeline||trace.at(-1)?.timeline||null,
    decisionHistory:{rows:trace,total:events.find(e=>e.kind==='decisions')?.count||0,limit:200,
      note:'Prospective v0.2.4 trace; ordinary state changes coalesced to one per minute. Older history may be absent or pruned.'},
    notificationDeliveries:deliveries.map(r=>({...r,at:iso(r.at),delivered_at:iso(r.delivered_at),
      acknowledgementDelayMs:r.delivered_at==null?null:r.delivered_at-r.at})),
    retainedEvents:events.map(e=>({...e,firstAt:iso(e.firstAt),lastAt:iso(e.lastAt)})),
    links:tokenLinks(c||{mint}),
    evidenceNote:c?'Candidate is present; compare its inactive flag, exact mint, and current dashboard filters.'
      :events.length||paper.paperEntry?'Absent from the current queue, but retained historical evidence exists.'
      :'No retained local evidence. This does not prove it was never discovered: queue eviction and history pruning can remove evidence.',
  };
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const mint=process.argv[2];let db;
  try {
    if(!validSolanaAddress(mint))throw new Error('Usage: node scripts/token-audit.mjs SOLANA_MINT_ADDRESS');
    db=new DatabaseSync(path.join(process.env.DATA_DIR||'/app/data','radar.sqlite'),{readOnly:true});
    db.exec('PRAGMA query_only=ON; PRAGMA busy_timeout=5000;');
    console.log(JSON.stringify(auditToken(db,mint),null,2));
  } catch(error) {
    console.error(error.message.startsWith('Usage:')?error.message:'Token audit failed. Run inside the radar container against its existing database.');process.exitCode=1;
  } finally {db?.close();}
}
