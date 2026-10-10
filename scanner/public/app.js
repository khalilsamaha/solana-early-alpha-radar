import {tokenLinks,validSolanaAddress} from './token-links.js';
import {createRefreshLoop} from './refresh-loop.js';
const $=s=>document.querySelector(s);
let token='',latestStats=null;const openDecisions=new Set();
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=n=>n!==null&&n!==undefined&&Number.isFinite(Number(n));
const money=n=>!num(n)?'—':Number(n)>=1e6?`$${(n/1e6).toFixed(2)}m`:Number(n)>=1e3?`$${(n/1e3).toFixed(1)}k`:`$${Number(n).toFixed(2)}`;
const pct=n=>num(n)?`${Number(n).toFixed(1)}%`:'—';
const short=s=>s?`${s.slice(0,5)}…${s.slice(-4)}`:'—';
const scoreClass=n=>n>=82?'strong':n>=72?'watch':'low';
const age=r=>{const times=[r.launchAt,r.firstPoolAt,r.pairCreatedAt].filter(x=>x>0);const t=times.length?Math.min(...times):r.firstSeenAt;return `${((Date.now()-t)/60000).toFixed(1)}m${times.length?'':'*'}`;};
async function api(url,signal){const r=await fetch(url,{cache:'no-store',signal,headers:token?{Authorization:`Bearer ${token}`}:{}});if(!r.ok){const error=new Error(`HTTP ${r.status}`);error.status=r.status;throw error;}return r.json();}
function tokenActions(candidate) {
 const links=tokenLinks(candidate);if(!links.length)return '';
 return `<div class="token-actions"><button type="button" data-copy-mint="${esc(candidate.mint)}" aria-label="Copy Solana mint ${esc(candidate.mint)}">Copy mint</button>${links.map(link=>`<a href="${esc(link.url)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">${esc(link.label)}</a>`).join('')}</div>`;
}
function renderMetrics(s){const h=s.paperSummary?.horizons?.['60m'];const rows=[['Active candidates',s.activeCandidates],['Unique paper entries',s.uniquePaperEntries],['60m completed',h?.observed??s.evaluated60m],['60m median change',pct(h?.medianReturnPct)],['60m above entry',pct(h?.aboveEntryPct)],['60m losses ≥50%',pct(h?.loss50Pct)]];$('#metrics').innerHTML=rows.map(([k,v])=>`<div class="metric"><b>${esc(v??'—')}</b><span>${k}</span></div>`).join('');}
function renderSummary(s){
 const cohort=$('#resultCohort').value,current=cohort==='current',summary=cohort==='v029'?s.paperSummaryV029:cohort==='v028'?s.paperSummaryV028:cohort==='v027'?s.paperSummaryV027:cohort==='v026'?s.paperSummaryV026:cohort==='v025'?s.paperSummaryV025:current?s.paperSummaryCurrent:s.paperSummary;
 const h=summary?.horizons||{};
 $('#resultRows').innerHTML=Object.entries(h).map(([label,r])=>`<tr><td>${esc(label)}</td><td>${r.observed}</td><td>${pct(r.medianReturnPct)}</td><td>${r.aboveEntry} (${pct(r.aboveEntryPct)})</td><td>${r.loss50} (${pct(r.loss50Pct)})</td><td>${r.sampledPeak2x} / ${r.checkpoint2x}</td><td>${r.missing} / ${r.gapped}</td><td>${r.pending} / ${r.overdue} / ${r.invalid}</td></tr>`).join('')||'<tr><td colspan="8">No summary available yet.</td></tr>';
 $('#resultScope').textContent=`${summary?.entries||0} unique entries · ${cohort==='v029'?'First alerts created by v0.2.9':cohort==='v028'?'First alerts created by v0.2.8':cohort==='v027'?'First alerts created by v0.2.7':cohort==='v026'?'First alerts created by v0.2.6':cohort==='v025'?'First alerts created by v0.2.5':current?'First alerts created by v0.2.4':'All retained entries; versions and market conditions may differ'}${summary?.firstEntryAt?' · first entry '+new Date(summary.firstEntryAt).toLocaleString():''}. Percentages use observed checkpoints; pending, overdue and missing counts remain separate.`;
}
function qualificationLabel(q) {
 return q?`<div class="tiny"><b>${esc(q.state)}</b> · shadow ${esc(q.disposition)}<br>${esc((q.reasons||[])[0]||'')}</div>`:'<div class="tiny">Qualification not recorded</div>';
}
function renderQualification(s) {
 const q=s.qualification;
 $('#qualificationScope').textContent=`Shadow rule ${q?.version||'qualification-1'} · ${q?.entries||0} new v0.2.9 baseline entries. Retain/defer are comparison labels; all baseline alerts continue. Missing or gapped returns are excluded from these medians and means. These are price observations, not fills.`;
 $('#qualificationRows').innerHTML=Object.entries(q?.groups||{}).flatMap(([name,g])=>Object.entries(g.horizons||{}).map(([h,r])=>`<tr><td>${esc(name)}</td><td>${esc(g.entries)}</td><td>${esc(h)}</td><td>${esc(r.observed)}</td><td>${pct(r.medianReturnPct)}</td><td>${pct(r.meanReturnPct)}</td><td>${esc(r.aboveEntry)} / ${esc(r.loss50)}</td><td>${esc(r.missing)} / ${esc(r.gapped)}</td><td>${esc(r.pending)} / ${esc(r.overdue)}</td></tr>`)).join('')||'<tr><td colspan="9">New entries will populate the comparison.</td></tr>';
}
function renderResearch(s){
 const h=s.health?.research;
 $('#researchMode').textContent=!h?.enabled?'Research disabled':h.notificationsEnabled?'Experimental Telegram enabled · baseline alerts continue':'SHADOW MODE · experimental Telegram off · baseline alerts continue';
 if(h?.enabled)$('#researchMode').textContent+=` · cohort ${s.research?.version||'unknown'} · focus ${h.focus?.ready??0}/${h.focus?.selected??0} ready (${h.focus?.eligible??0} eligible; limit ${h.focus?.limit??0})`;
 const summary=s.research?.summary||{};
 $('#researchRows').innerHTML=Object.entries(summary).flatMap(([cohort,group])=>Object.entries(group.horizons||{}).map(([h,r])=>`<tr><td>${esc(cohort)}</td><td>${esc(h)}</td><td>${esc(group.entries)}</td><td>${esc(r.observed)}</td><td>${pct(r.medianReturnPct)}</td><td>${esc(r.aboveEntry)}</td><td>${esc(r.gapped)} / ${esc(r.missing)}</td><td>${esc(r.pending)} / ${esc(r.overdue)}</td></tr>`)).join('')||'<tr><td colspan="8">New research checkpoints will appear after an entry.</td></tr>';
 $('#continuityRows').innerHTML=Object.entries(s.research?.tokenFollowup||{}).flatMap(([cohort,group])=>Object.entries(group.horizons||{}).map(([h,r])=>`<tr><td>${esc(cohort)}</td><td>${esc(h)}</td><td>${esc(r.originalPool)} / ${esc(r.alternatePool)}</td><td>${pct(r.medianReturnPct)}</td><td>${esc(r.gapped)} / ${esc(r.missing)}</td><td>${esc(r.pending)} / ${esc(r.overdue)}</td></tr>`)).join('')||'<tr><td colspan="6">Follow-ups start with new research entries.</td></tr>';
 $('#researchEvents').innerHTML=(s.research?.events||[]).map(e=>`<div class="alert-card"><div><b>${esc(e.event)} · ${esc(e.candidate?.symbol||short(e.mint))}</b><div class="alert-meta">${esc(new Date(e.at).toLocaleString())} · ${esc(e.security)}</div><div class="tiny">Baseline ${esc(e.baselineScore??'—')} · research ${esc(e.experimentalScore??'—')} · ~60s ${pct(e.features?.r60?.returnPct)} · drawdown ${pct(e.features?.drawdownPct)}</div><p>${(e.reasons||[]).map(esc).join('<br>')}</p>${tokenActions(e.candidate||{mint:e.mint})}</div></div>`).join('')||'<p>No research events yet. Histories start fresh after each restart.</p>';
}
function decisionDetails(r){
 const d=r.decision;if(!d)return '<span class="tiny">Decision trace starts with v0.2.4 observations.</span>';
 const titles={blocked:'Not eligible now',eligible:'Eligible at evaluation','already-alerted':'This alert level already sent or recorded'};
 const timeline=r.decisionTimeline;
 const labels={startedAt:'Trace started',firstSeenAt:'First discovery recorded',firstAttemptAt:'First attempt during trace',firstMarketAt:'First usable market during trace',firstLiquidityKnownAt:'Liquidity first reported',firstLiquidityEligibleAt:'Liquidity first ≥$5k',firstMetadataEligibleAt:'Metadata queue first eligible',firstSecurityAttemptAt:'First security request',firstSecurityCompleteAt:'First complete security',firstThresholdAt:'First threshold crossing',firstAlertEligibleAt:'First alert eligibility',firstAlertAt:'First alert created'};
 return `<details data-decision-mint="${esc(r.mint)}"${openDecisions.has(r.mint)?' open':''}><summary>${esc(titles[d.status]||d.status)}</summary><ul>${(d.reasons||[]).map(reason=>`<li>${esc(reason)}</li>`).join('')}</ul><p>${esc(d.metadataReason)}</p><p>Score last evaluated: ${r.updatedAt?esc(new Date(r.updatedAt).toLocaleString()):'unknown'}</p>${timeline?`<p>${timeline.priorHistoryUnavailable?'Earlier milestones are unknown; trace began after discovery.':'Trace began with this discovery.'}</p>${Object.entries(labels).filter(([key])=>timeline[key]).map(([key,label])=>`<div>${label}: ${esc(new Date(timeline[key]).toLocaleString())}</div>`).join('')}`:'<p>No timeline recorded yet.</p>'}</details>`;
}
function observationLabel(r){
 const q=r.research?.observationQuality,f=r.research?.fastShadow;
 if(!q)return '';
 return `<div class="tiny">Observation: ${esc(q.state)} · response ${num(q.responseAgeMs)?Math.round(q.responseAgeMs/1000)+'s':'unknown'} old<br>Price unchanged for at least ${num(q.priceUnchangedForAtLeastMs)?Math.round(q.priceUnchangedForAtLeastMs/1000)+'s':'unknown'} · exchange freshness unknown${f?`<br>30s research: ${esc(f.admission||'not eligible')} · ${pct(f.return30sPct)}`:''}</div>`;
}
function renderCandidates(rows){
 const query=$('#search').value.trim().toLowerCase();rows=rows.filter(r=>[r.mint,r.symbol,r.tokenName].some(x=>String(x||'').toLowerCase().includes(query)));
 $('#candidates').innerHTML=rows.length?rows.map(r=>`<tr><td class="token"><strong>${esc(r.symbol||r.tokenName||short(r.mint))}</strong><small title="${esc(r.mint)}">${esc(short(r.mint))} · Solana · ${esc((r.discoverySources||[]).join(', '))}</small>${tokenActions(r)}</td><td><span class="score ${scoreClass(r.score||0)}">${esc(r.score||0)}</span><div class="tiny">${esc(r.stale?'STALE':'Activity score')}</div>${qualificationLabel(r.qualification)}${observationLabel(r)}${r.research?`<div class="tiny">Research: ${esc(r.research.stage)}${r.research.poolChange?' · pool changed':''} · ${esc(r.research.score??'warming up')}<br>~60s ${pct(r.research.metrics?.r60?.returnPct)} · drawdown ${pct(r.research.metrics?.drawdownPct)}</div>`:''}</td><td>${esc(age(r))}</td><td>${money(r.marketCap)}${!num(r.marketCap)&&num(r.fdv)?`<small>FDV ${money(r.fdv)}</small>`:''}</td><td>${num(r.liquidityUsd)?money(r.liquidityUsd):'Unknown'}${!num(r.liquidityUsd)?'<div class="tiny">Not reported by source</div>':''}</td><td>${esc(r.txns?.m5?.buys??'—')} B / ${esc(r.txns?.m5?.sells??'—')} S</td><td>${esc(r.organicScore??'—')}</td><td>${esc(r.holderCount??'—')}</td><td>${pct(r.top10Pct)}<div class="tiny">${r.securityFresh?'checked':'unverified / expired'}</div></td><td class="risk">${esc((r.scoreRisks||[])[0]?.reason||'Limited checks only')}<div class="tiny">Deterioration: ${esc(r.exitRisk?.level||'unknown')}</div></td><td class="decision">${decisionDetails(r)}</td></tr>`).join(''):'<tr><td colspan="11">No matching candidates. Discovery and provider status appear below.</td></tr>';
}
function renderAlerts(rows){$('#alerts').innerHTML=rows.length?rows.slice(0,20).map(a=>`<div class="alert-card"><div><b>${esc(a.candidate.symbol||short(a.candidate.mint))}</b>${qualificationLabel(a.qualification)}<div class="alert-meta">${esc(new Date(a.at).toLocaleString())} · MC ${money(a.candidate.marketCap)}</div><div class="tiny">${esc(a.candidate.mint)}</div>${tokenActions(a.candidate)}<div class="tiny">${esc((a.scoring.reasons||[]).slice(0,2).map(x=>x.reason).join(' · '))}</div></div><span class="score ${scoreClass(a.scoring.score)}">${esc(a.scoring.score)}</span></div>`).join(''):'<p>No paper alerts yet.</p>';}
function renderHealth(h){$('#providerHealth').innerHTML=Object.entries(h.providers).map(([name,p])=>`<div class="metric"><b>${esc(name)}</b><span>${esc(p.state)} · failures ${p.failures}</span><div class="tiny">${esc(p.lastError||'')}</div></div>`).join('');$('#serviceState').textContent=`Backend ${h.mode} · ${h.ready?'market data arriving':'not ready'} · queue age ${Math.round(h.oldestAttemptAgeMs/1000)}s · notifications pending ${h.notifications.pending||0}, failed ${h.notifications.failed||0}, expired ${h.notifications.expired||0}`;}
function renderOutcomes(rows){$('#outcomes').innerHTML=rows.slice(-20).reverse().map(o=>`<tr><td class="token">${esc(o.symbol||short(o.mint))}${tokenActions({mint:o.mint})}</td><td>${esc(o.horizon)}</td><td>${esc(o.status||(o.legacy?'legacy MC':'unknown'))}</td><td>${num(o.multiple)?o.multiple.toFixed(2)+'×':'—'}</td><td>${esc(o.coverage||'—')}</td><td>${num(o.lagMs)?Math.round(o.lagMs/1000)+'s':'—'}</td></tr>`).join('')||'<tr><td colspan="6">No completed checkpoints yet.</td></tr>';}
let candidates=[];
const loop=createRefreshLoop({
 load:async signal=>{const active=$('#activeOnly').checked?'1':'0';return Promise.all([api('/api/stats',signal),api(`/api/candidates?active=${active}&limit=1000`,signal),api('/api/alerts?limit=50',signal),api('/api/outcomes?limit=50',signal)]);},
 render:([stats,rows,alerts,outcomes])=>{
   const freshness=$('#statisticsFreshness'),metadata=stats.statistics;
   if(freshness)freshness.textContent=metadata?`${metadata.stale?'STALE SUMMARY · ':''}Results calculated from observations through ${new Date(metadata.snapshotAt).toLocaleTimeString()} · ${Math.round(metadata.ageMs/1000)}s old${metadata.refreshing?' · updating…':''}${metadata.lastError?' · update failed; showing previous results':''}`:'Summary timestamp unavailable';
   candidates=rows;latestStats=stats;renderMetrics(stats);renderSummary(stats);renderResearch(stats);renderQualification(stats);renderCandidates(rows);renderAlerts(alerts);renderHealth(stats.health);renderOutcomes(outcomes);
   $('#statusLog').innerHTML=stats.status.map(r=>`<div class="log-row"><time>${esc(new Date(r.at).toLocaleTimeString())}</time>${esc(r.message)}</div>`).join('');
   $('#buckets').textContent=Object.entries(stats.buckets).map(([k,b])=>`${k}: ${b.doubles}/${b.n} sampled ≥2×`).join(' · ')||'Peak cohorts appear after 60m observations.';
 },
 onState:s=>{
   const state=s.error?'error':s.stale?'stale':'fresh';$('#refreshState').dataset.state=state;
   $('#clock').textContent=s.lastSuccessAt===null?'No successful dashboard refresh':`Last successful update ${new Date(s.lastSuccessAt).toLocaleTimeString()} · ${Math.floor(s.ageMs/1000)}s ago`;
   $('#refreshNotice').textContent=s.error?`${s.error} Displayed data may be stale.`:s.stale?(s.lastSuccessAt===null?'Waiting for dashboard data.':'STALE DISPLAY — no successful update for over 30 seconds.'):(s.busy?'Refreshing dashboard…':'Dashboard data is updating.');
   $('#refreshNotice').dataset.state=state;$('#authMessage').textContent=s.error||'';
 }
});
$('#connect').addEventListener('click',()=>{token=$('#accessToken').value;$('#accessToken').value='';void loop.request();});
$('#refresh').addEventListener('click',()=>void loop.request());$('#activeOnly').addEventListener('change',()=>void loop.request());
$('#search').addEventListener('input',()=>renderCandidates(candidates));
$('#resultCohort').addEventListener('change',()=>{if(latestStats)renderSummary(latestStats);});
document.addEventListener('toggle',event=>{const mint=event.target.dataset?.decisionMint;if(mint){if(event.target.open)openDecisions.add(mint);else openDecisions.delete(mint);}},true);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)void loop.request();});
void loop.start();

document.addEventListener('click',async event=>{
 const button=event.target.closest('[data-copy-mint]');if(!button)return;
 const mint=button.dataset.copyMint;if(!validSolanaAddress(mint))return;
 try {
   if(!navigator.clipboard?.writeText)throw new Error('Clipboard unavailable');
   await navigator.clipboard.writeText(mint);$('#actionStatus').textContent=`Copied Solana mint: ${mint}`;
 } catch {
   const input=$('#mintValue');input.value=mint;
   $('#mintDialog').showModal();input.focus();input.select();
   $('#actionStatus').textContent='Clipboard unavailable. Select and copy the full mint in the dialog.';
 }
});
$('#closeMintDialog').addEventListener('click',()=>$('#mintDialog').close());
