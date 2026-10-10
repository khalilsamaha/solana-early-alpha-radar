import {tokenLinks} from '../../public/token-links.js';
export function alertButtons(alert) {
  const links=tokenLinks(alert.candidate);
  if(!links.length)return undefined;
  const buttons=links.map(link=>({text:link.label,url:link.url}));
  const rows=[];for(let i=0;i<buttons.length;i+=2)rows.push(buttons.slice(i,i+2));
  rows.push([{text:'Copy Solana mint',copy_text:{text:alert.candidate.mint}}]);
  return {inline_keyboard:rows};
}
export function formatAlert(alert) {
  if(alert.text)return alert.text.slice(0,3900);
  const c=alert.candidate,s=alert.scoring;
  return [
    `RADAR ${alert.qualification?alert.qualification.state.toUpperCase():alert.type==='exit'?'DETERIORATION':'BASELINE OBSERVATION'} — ${c.symbol||c.tokenName||'UNKNOWN'}`,
    ...(alert.qualification?[`Shadow rule: ${alert.qualification.disposition.toUpperCase()} · baseline alert retained for comparison`,...alert.qualification.reasons,`History ready: ${alert.qualification.historyReady?'yes':'no'}`]:[]),
    `Signal ID: ${alert.id}`,`Observed: ${new Date(alert.at).toISOString()}`,
    `Activity score: ${s.score}/100 | age: ${s.metrics.ageMin.toFixed(1)}m`,
    `Network: Solana | Mint: ${c.mint}`,`Price: $${c.priceUsd??'unknown'} | MC: $${Math.round(c.marketCap||0).toLocaleString()}`,
    `Liquidity: $${Math.round(c.liquidityUsd||0).toLocaleString()}`,
    `5m flow: ${s.metrics.buys5m} buys / ${s.metrics.sells5m} sells`,
    `Organic: ${c.organicScore??'unknown'} | Top 10 token accounts: ${Number.isFinite(c.top10Pct)?c.top10Pct.toFixed(1)+'%':'unknown'}`,
    ...(alert.marketContext?[`Research stage: ${alert.marketContext.stage}`,`Drawdown from recorded peak: ${Number.isFinite(alert.marketContext.metrics?.drawdownPct)?alert.marketContext.metrics.drawdownPct.toFixed(1)+'%':'unavailable'}`,`Experimental score: ${alert.marketContext.score??'warming up'} (separate from baseline score)`]:[]),
    'Reasons:',...(s.reasons||[]).slice(0,4).map(x=>`• ${x.reason}`),
    'Risk flags:',...(alert.qualification?.flags||[]),...(s.risks||[]).slice(0,4).map(x=>`• ${x.reason}`),
    'Paper observation. Score is not a probability or a safety assessment.'
  ].join('\n').slice(0,3900);
}
export async function sendTelegram(config,alert) {
  if(!config.notificationsEnabled||!config.telegramBotToken||!config.telegramChatId)return {skipped:true};
  const response=await fetch(`https://api.telegram.org/bot${config.telegramBotToken}/sendMessage`,{
    method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({chat_id:config.telegramChatId,text:formatAlert(alert),reply_markup:alertButtons(alert),link_preview_options:{is_disabled:true}}),signal:AbortSignal.timeout(8000)});
  const body=await response.json();
  if(!response.ok||body.ok!==true) {
    const error=new Error(`Telegram error ${body.error_code||response.status}`);
    error.retryAfterMs=Number(body.parameters?.retry_after||0)*1000;
    error.permanent=[400,401,403,404].includes(body.error_code||response.status);
    throw error;
  }
  return {messageId:body.result?.message_id};
}
