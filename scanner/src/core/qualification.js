// Observational rule, versioned independently of the baseline activity score.
import {summarizeOutcomes} from './outcome-summary.js';
export const QUALIFICATION_VERSION='qualification-1';
const finite=Number.isFinite;
const value=x=>finite(x)?x:null;
export function qualify(candidate,research,now=Date.now()) {
 const m=research?.metrics||{},r30=value(m.r30?.returnPct),r60=value(m.r60?.returnPct);
 const dd=value(m.drawdownPct),liq=value(m.r30?.liquidityChangePct),interval=value(m.lastIntervalReturnPct);
 const poolMatches=typeof candidate.pairAddress==='string'&&candidate.pairAddress.length>0&&m.pairAddress===candidate.pairAddress;
 const fresh=poolMatches&&finite(candidate.priceUsd)&&candidate.priceUsd>0&&finite(m.at)&&m.at>0&&now>=m.at&&now-m.at<=45000
   &&!candidate.stale&&finite(candidate.marketObservedAt)&&now>=candidate.marketObservedAt&&now-candidate.marketObservedAt<=45000;
 const historyReady=fresh&&m.ready===true&&r30!==null&&r60!==null;
 const flags=[],reasons=[];
 let state='insufficient history';
 if(!fresh)reasons.push('Fresh same-pool research observations unavailable');
 else if((interval!==null&&interval<=-20)||(r30!==null&&r30<=-10)||(dd!==null&&dd<=-15)||(liq!==null&&liq<=-30)) {
   state='deteriorating';reasons.push('Recent price or liquidity deterioration; activity score does not establish recovery');
 } else if(!historyReady)reasons.push('A continuous same-pool short-window history is not ready');
 else if(research.stage==='recovery unconfirmed'||research.stage==='deteriorating') {
   state='recovery unconfirmed';reasons.push('Prior deterioration has not met the research recovery conditions');
 } else if(!finite(m.unchangedForMs)||m.unchangedForMs>45000) {
   state='unchanged market';reasons.push('Recent requests repeat unchanged market fields');
 } else if(research.stage==='recovery observed') {
   state='recovery observed';reasons.push('Research recovery observed; continuation and execution remain unknown');
 } else if(r30<0||r60<0) {
   state='falling';reasons.push('Recorded short-window price direction is negative');
 } else if(r60>=10&&r30>0&&m.r60.changedSamples>=2) {
   state='rising activity';reasons.push('Positive short-window movement with changing provider observations');
 } else {state='observing';reasons.push('No confirmed rising or recovery condition');}
 const tx=candidate.txns?.m5,buys=value(tx?.buys),sells=value(tx?.sells),volume=value(candidate.volume?.m5);
 const transactions=buys!==null&&sells!==null&&buys>=0&&sells>=0?buys+sells:null;
 const average=volume!==null&&volume>=0&&transactions>0?volume/transactions:null;
 // A descriptive flag only: this is not proof of manipulation and does not gate the shadow rule.
 if(average!==null&&average<5)flags.push('Small average reported trade (<$5); activity quality unverified');
 if(candidate.organicScore===0)flags.push('Provider organic score is zero');
 if(!historyReady)flags.push('Insufficient continuous research history');
 if(fresh&&finite(m.unchangedForMs)&&m.unchangedForMs>45000)flags.push('Market fields unchanged for over 45 seconds; fresh requests do not establish fresh trading');
 const disposition=['rising activity','recovery observed'].includes(state)?'retain':'defer';
 return {version:QUALIFICATION_VERSION,mode:'shadow',at:now,state,disposition,historyReady,reasons,flags,
   metrics:{poolAddress:candidate.pairAddress||null,observedAt:value(m.at),return30sPct:r30,return60sPct:r60,
     drawdownPct:dd,liquidityChange30sPct:liq,lastIntervalReturnPct:interval,unchangedForMs:value(m.unchangedForMs),
     averageReportedTradeUsd:average,transactions5m:transactions,volume5mUsd:volume},
   note:'Shadow comparison only. Baseline entry and notification rules continue. Not an execution or safety assessment.'};
}
export function qualificationSummary(entries,outcomes,now,tolerance) {
 const scoped=entries.filter(a=>a.engineVersion==='0.2.9'&&a.qualification?.version===QUALIFICATION_VERSION);
 const groups={};
 for(const name of ['retain','defer']) {
   const group=scoped.filter(a=>a.qualification.disposition===name);
   // Fair comparison excludes gapped returns from medians but keeps their counts explicit.
   const clean=outcomes.filter(o=>o.coverage!=='gapped');
   const s=summarizeOutcomes(group,clean,now,tolerance);
   const original=summarizeOutcomes(group,outcomes,now,tolerance);
   const keys=new Set(group.map(a=>`${a.candidate.mint}:${a.id.split(':')[1]}`));
   for(const h of Object.keys(s.horizons)) {
     const vals=clean.filter(o=>o.version==='price-v2'&&o.horizon===h&&o.status==='observed'&&Number.isFinite(o.multiple)&&o.multiple>0&&keys.has(`${o.mint}:${o.alertAt}`)).map(o=>(o.multiple-1)*100);
     s.horizons[h].meanReturnPct=vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null;
     s.horizons[h].gapped=original.horizons[h].gapped;
     s.horizons[h].pending=original.horizons[h].pending;s.horizons[h].overdue=original.horizons[h].overdue;
   }
   groups[name]=s;
 }
 return {version:QUALIFICATION_VERSION,mode:'shadow',entries:scoped.length,
   states:Object.fromEntries([...new Set(scoped.map(a=>a.qualification.state))].map(state=>[state,scoped.filter(a=>a.qualification.state===state).length])),groups};
}
