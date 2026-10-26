import {StatsService} from '../core/stats-service.js';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import {timingSafeEqual} from 'node:crypto';
const json=(res,body,status=200)=>{res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store'});res.end(JSON.stringify(body));};
const safeEqual=(a,b)=>{const x=Buffer.from(a),y=Buffer.from(b);return x.length===y.length&&timingSafeEqual(x,y);};
const limit=(u,fallback)=>Math.max(1,Math.min(1000,parseInt(u.searchParams.get('limit'),10)||fallback));
export function startServer(radar,port,publicDir=path.resolve('public'),options={}) {
  const token=options.token??radar.config.dashboardToken;
  const statistics=new StatsService(path.join(radar.storage.dir,'radar.sqlite'),radar.config.horizonToleranceMs,options.statisticsOptions);
  radar.statisticsService=statistics;
  const liveStats=async()=>({...await statistics.get(),totalCandidates:radar.candidates.size,activeCandidates:[...radar.candidates.values()].filter(x=>!x.inactive).length,health:radar.getHealth(),status:radar.status.slice(-20).reverse()});
  const server=http.createServer(async(req,res)=>{
    res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('Referrer-Policy','no-referrer');
    res.setHeader('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");
    try {
      const u=new URL(req.url,'http://localhost');
      if(req.method!=='GET'){res.setHeader('Allow','GET');return json(res,{error:'Method not allowed'},405);}
      if(u.pathname==='/healthz')return json(res,{alive:true});
      if(u.pathname==='/readyz'){const ready=radar.getHealth().ready;return json(res,{ready},ready?200:503);}
      if(u.pathname.startsWith('/api/')||u.pathname==='/metrics') {
        if(token&&!safeEqual(req.headers.authorization||'',`Bearer ${token}`))return json(res,{error:'Authentication required'},401);
        if(u.pathname==='/api/health')return json(res,radar.getHealth());
        if(u.pathname==='/api/candidates')return json(res,radar.getCandidates({activeOnly:u.searchParams.get('active')==='1',limit:limit(u,200)}));
        if(u.pathname==='/api/alerts')return json(res,radar.getAlerts(limit(u,200)));
        if(u.pathname==='/api/outcomes')return json(res,radar.getOutcomes(limit(u,1000)));
        if(u.pathname==='/api/stats')return json(res,await liveStats());
        if(u.pathname==='/api/exit-alerts')return json(res,radar.storage.readJsonl('exit-alerts',limit(u,100)).reverse());
        if(u.pathname.startsWith('/api/token/')){const row=radar.candidates.get(decodeURIComponent(u.pathname.slice(11)));return json(res,row||{error:'Not found'},row?200:404);}
        if(u.pathname==='/metrics') {
          const h=radar.getHealth(),s=await liveStats();
          res.writeHead(200,{'content-type':'text/plain; version=0.0.4','cache-control':'no-store'});
          return res.end(`radar_ready ${Number(h.ready)}\nradar_uptime_seconds ${h.uptimeSeconds}\nradar_candidates ${s.totalCandidates}\nradar_paper_entries ${s.uniquePaperEntries}\nradar_outcomes_missing ${s.missing60m}\nradar_notifications_pending ${h.notifications.pending||0}\nradar_notifications_failed ${h.notifications.failed||0}\nradar_oldest_attempt_age_seconds ${h.oldestAttemptAgeMs/1000}\n`);
        }
        return json(res,{error:'Not found'},404);
      }
      const files={'/':'index.html','/app.js':'app.js','/token-links.js':'token-links.js','/refresh-loop.js':'refresh-loop.js','/styles.css':'styles.css'};
      if(!files[u.pathname])return json(res,{error:'Not found'},404);
      const file=path.join(publicDir,files[u.pathname]);
      res.writeHead(200,{'content-type':u.pathname.endsWith('.js')?'text/javascript; charset=utf-8':u.pathname.endsWith('.css')?'text/css; charset=utf-8':'text/html; charset=utf-8','cache-control':'no-cache'});
      res.end(fs.readFileSync(file));
    }catch(error){if(!res.headersSent)json(res,{error:error.statusCode===503?'Statistics temporarily unavailable':'Internal server error'},error.statusCode===503?503:500);else res.end();}
  });
  server.once('close',()=>void statistics.close());
  server.requestTimeout=15000;server.headersTimeout=10000;
  server.listen(port,options.host||radar.config.dashboardHost,()=>console.log(`[dashboard] listening on port ${server.address().port}`));
  return server;
}
