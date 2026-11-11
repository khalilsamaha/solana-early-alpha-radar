import {creationEvidence} from '../core/launch-registry.js';

export function dispatchPumpPortalEvent(row,onToken,onStatus,onCreation,receivedAt=Date.now()) {
  if(!row.mint||!['create','migration','migrate'].includes(row.txType))return;
  const evidence=creationEvidence(row,receivedAt);
  if(evidence){try{onCreation(evidence);}catch{onStatus('Launch registry write failed; discovery continues');}}
  onToken({mint:row.mint,tokenName:row.name,symbol:row.symbol,creator:row.traderPublicKey||row.creator,
    ...(row.txType==='create'?{launchAt:receivedAt}:{}),discoverySource:`pumpportal:${row.txType}`});
}
