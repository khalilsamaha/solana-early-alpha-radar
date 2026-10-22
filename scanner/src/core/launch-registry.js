import {createHash} from 'node:crypto';

export const LAUNCH_VERSION='launch-registry-1';
export const LAUNCH_LIMITS={retentionDays:30,maxRows:100000,maxRowBytes:4096,pruneBatch:500};
const base58=(v,min,max)=>typeof v==='string'&&v.length>=min&&v.length<=max&&/^[1-9A-HJ-NP-Za-km-z]+$/.test(v)?v:null;
const decimal=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=Number.MAX_SAFE_INTEGER?String(v):
  typeof v==='string'&&v.length<=80&&/^\d+(?:\.\d+)?$/.test(v)?v:null;
const integer=v=>Number.isSafeInteger(v)&&v>=0?v:null;

// Only provider-reported creation fields. No metadata fetch, identity verification,
// inferred decimals, reserve-derived prices, or reconstructed on-chain timestamps.
export function creationEvidence(row,receivedAt=Date.now()) {
  if(!row||row.txType!=='create'||!base58(row.mint,32,44)||!Number.isSafeInteger(receivedAt)||receivedAt<=0)return null;
  const fields={signature:base58(row.signature,64,88),creatorReported:base58(row.creator,32,44),
    traderReported:base58(row.traderPublicKey,32,44),bondingCurveKey:base58(row.bondingCurveKey,32,44),
    slotReported:integer(row.slot),decimalsReported:integer(row.decimals),
    initialBuyReported:decimal(row.initialBuy),solAmountReported:decimal(row.solAmount),
    virtualSolReservesReported:decimal(row.vSolInBondingCurve),virtualTokenReservesReported:decimal(row.vTokensInBondingCurve),
    marketCapSolReported:decimal(row.marketCapSol),
    metadataUriSha256:typeof row.uri==='string'&&row.uri.length>0&&row.uri.length<=2048?
      createHash('sha256').update(row.uri).digest('hex'):null};
  if(fields.decimalsReported>255)fields.decimalsReported=null;
  return {version:LAUNCH_VERSION,mint:row.mint,source:'pumpportal:create',receivedAt,availableAt:receivedAt,
    chainTime:null,fields,quantityBasis:'provider-reported units; not normalized or execution prices',
    identityBasis:'creator and trader are distinct unverified provider fields',
    numberBasis:'JSON numbers already parsed by provider adapter; exact original number lexemes unavailable'};
}

export class LaunchRegistry {
  constructor(db,limits=LAUNCH_LIMITS){
    this.db=db;this.limits=limits;this.lastMaintenance=0;
    this.counters={inserted:0,duplicate:0,rejected:0,capacityDropped:0,pruned:0,errors:0};
    db.exec(`CREATE TABLE IF NOT EXISTS launch_registry(mint TEXT PRIMARY KEY,received_at INTEGER NOT NULL,data TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS launch_registry_received ON launch_registry(received_at);`);
    this.retained=Number(db.prepare('SELECT count(*) AS n FROM launch_registry').get().n);
  }
  record(e,now=Date.now()){
    if(!e||e.version!==LAUNCH_VERSION||!base58(e.mint,32,44)||e.source!=='pumpportal:create'||
      !Number.isSafeInteger(e.receivedAt)||e.receivedAt<=0||e.receivedAt>now||e.availableAt!==e.receivedAt||
      e.receivedAt<now-this.limits.retentionDays*86400000){this.counters.rejected++;return 'rejected';}
    const data=JSON.stringify(e);
    if(Buffer.byteLength(data)>this.limits.maxRowBytes){this.counters.rejected++;return 'rejected';}
    if(now-this.lastMaintenance>=60000){
      const removed=this.db.prepare('DELETE FROM launch_registry WHERE mint IN (SELECT mint FROM launch_registry WHERE received_at<? ORDER BY received_at LIMIT ?)')
        .run(now-this.limits.retentionDays*86400000,this.limits.pruneBatch);
      this.retained-=Number(removed.changes);this.counters.pruned+=Number(removed.changes);this.lastMaintenance=now;
    }
    if(this.db.prepare('SELECT 1 FROM launch_registry WHERE mint=?').get(e.mint)){this.counters.duplicate++;return 'duplicate';}
    if(this.retained>=this.limits.maxRows){this.counters.capacityDropped++;return 'capacity-dropped';}
    this.db.prepare('INSERT INTO launch_registry VALUES(?,?,?)').run(e.mint,e.receivedAt,data);
    this.db.prepare("INSERT OR IGNORE INTO kv(key,data) VALUES('launch-registry-registration',?)")
      .run(JSON.stringify({version:LAUNCH_VERSION,registeredAt:now,limits:this.limits,coverage:'received valid creation events only; not all Solana launches'}));
    this.retained++;this.counters.inserted++;return 'inserted';
  }
  health(){return {version:LAUNCH_VERSION,retained:this.retained,limits:this.limits,sinceRestart:{...this.counters},
    coverage:'first retained creation per mint; local receipt clock; unknown stream downtime is not reconstructed'};}
}
