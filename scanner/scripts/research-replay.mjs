// Offline, read-only feature replay. No credentials, database access or notifications.
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
import {MomentumHistory,turnoverPoints} from '../src/core/momentum.js';
export function replayHistory(input) {
 const rows=(input.events||[]).filter(e=>e.kind==='snapshots').map(e=>e.data).sort((a,b)=>a.at-b.at);
 const h=new MomentumHistory();let previous,identical=0,ready=0,gaps=0,poolChanges=0;const features=[];
 for(const c of rows){
  const m=h.observe(c,c.at);
  if(previous){if(c.at-previous.at>45000)gaps++;if(previous.pairAddress!==c.pairAddress)poolChanges++;
   const fields=x=>JSON.stringify([x.pairAddress,x.priceUsd,x.volume?.m5,x.txns?.m5,x.liquidityUsd]);
   if(fields(c)===fields(previous))identical++;
  }
  if(m.ready)ready++;
  features.push({at:c.at,iso:new Date(c.at).toISOString(),priceUsd:c.priceUsd,storedBaselineScore:c.score,
   ready:m.ready,resetReason:m.resetReason,return30Pct:m.r30?.returnPct??null,return60Pct:m.r60?.returnPct??null,
   rollingVolumeDeltaPerMinute:m.r60?.volumeDeltaPerMinute??null,rollingTransactionsDeltaPerMinute:m.r60?.transactionsDeltaPerMinute??null,
   recentDrawdownPct:m.drawdownPct,turnoverPoints:c.liquidityUsd>0?turnoverPoints(c.volume?.m5/c.liquidityUsd):null});
  previous=c;
 }
 return {mint:input.mint,snapshotCount:rows.length,identicalConsecutiveMarketSnapshots:identical,
  gapsOver45Seconds:gaps,poolChanges,readySnapshots:ready,firstReadyAt:features.find(x=>x.ready)?.iso??null,
  limitations:['Feature replay only: snapshots do not contain complete historical security and metadata state.',
   'Sparse archived observations are not the complete live scan. Gaps reset history; missing observations are never interpolated.',
   'These are observed prices, not executable fills or predicted peaks.'],features};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 if(!process.argv[2]){console.error('Usage: node scripts/research-replay.mjs PATH_TO_MARKET_HISTORY.json');process.exitCode=1;}
 else console.log(JSON.stringify(replayHistory(JSON.parse(fs.readFileSync(process.argv[2],'utf8'))),null,2));
}
