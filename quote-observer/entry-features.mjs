// Read only the immutable signal event; never query a later candidate snapshot.
export const FEATURE_CAPTURE='entry-features-1';
export const ACTIVITY_SHADOW={id:'average-reported-trade-5-v1',field:'averageReportedTradeUsd',
  thresholdUsd:5,groups:['below-5','at-least-5','unknown'],primaryOffsetMs:120000,
  mode:'prospective-observation-only',changesAdmissions:false,
  definition:'Compare entry-time average reported trade size below 5 USD, at least 5 USD and unknown; keep all quote failures. No trading approval.'};
const object=x=>x&&typeof x==='object'&&!Array.isArray(x)?x:{};
const numeric=x=>typeof x==='number'&&Number.isFinite(x)?x:null;
const short=x=>typeof x==='string'?x.slice(0,96):null;
export function entryFeatures(row){
  if(row.cohort==='fast30-shadow')return fastFeatures(row);
  const c=object(row.candidate),q=object(row.qualification),m=object(q.metrics);
  const inputs=object(object(row.evidence).inputs),features={},sources={};
  function num(key,raw,source,nonnegative=false){
    const n=numeric(raw);features[key]=n!==null&&(!nonnegative||n>=0)?n:null;
    sources[key]={source,state:raw===undefined||raw===null?'absent':features[key]===null?'invalid':'recorded'};
  }
  for(const key of ['liquidityUsd','organicScore','top10Pct','marketCap','holderCount'])num(key,c[key],`candidate.${key}`,true);
  for(const key of ['return30sPct','return60sPct','drawdownPct','liquidityChange30sPct','lastIntervalReturnPct'])num(key,m[key],`qualification.metrics.${key}`);
  for(const key of ['unchangedForMs','averageReportedTradeUsd','transactions5m','volume5mUsd'])num(key,m[key],`qualification.metrics.${key}`,true);
  for(const key of ['securityCheckedAt','marketObservedAt','jupiterCheckedAt']){
    num(key,inputs[key],`evidence.inputs.${key}`,true);
    if(features[key]!==null&&(!Number.isSafeInteger(features[key])||features[key]<=0||features[key]>row.at)){
      features[key]=null;sources[key].state='invalid';
    }
  }
  features.security=short(row.security||object(row.marketContext).security);
  features.baselineScore=numeric(row.baselineScore??object(row.scoring).score);
  features.experimentalScore=numeric(row.experimentalScore);
  features.disposition=short(q.disposition);
  features.historyReady=typeof q.historyReady==='boolean'?q.historyReady:null;
  features.dexId=short(c.dexId);
  const ages={};
  for(const key of ['securityCheckedAt','marketObservedAt','jupiterCheckedAt'])ages[key]=features[key]===null?null:row.at-features[key];
  return {features,featureCapture:{version:FEATURE_CAPTURE,signalAt:row.at,sources,ageAtSignalMs:ages,
    note:'Immutable event fields only. Recorded values and request timestamps do not establish current liquidity, organic activity, safety or executable depth.'}};
}

function fastFeatures(row){
 const security=object(row.security),quality=object(row.quality),decision=object(row.decision);
 const mapped={...row,candidate:{liquidityUsd:row.liquidityUsd,top10Pct:security.top10Pct},
  qualification:{metrics:{return30sPct:decision.return30sPct,lastIntervalReturnPct:decision.lastIntervalReturnPct}},
  security:security.status,evidence:{inputs:{securityCheckedAt:security.checkedAt,marketObservedAt:quality.lastObservedAt}}};
 delete mapped.cohort;
 const result=entryFeatures(mapped);
 result.featureCapture.version='fast-entry-features-1';
 result.featureCapture.sources.liquidityUsd.source='liquidityUsd';
 result.featureCapture.sources.top10Pct.source='security.top10Pct';
 result.featureCapture.sources.return30sPct.source='decision.return30sPct';
 result.featureCapture.sources.lastIntervalReturnPct.source='decision.lastIntervalReturnPct';
 result.featureCapture.sources.securityCheckedAt.source='security.checkedAt';
 result.featureCapture.sources.marketObservedAt.source='quality.lastObservedAt';
 result.followup=row.followup||{policy:'legacy-unprioritized',admitted:false};
 return result;
}
