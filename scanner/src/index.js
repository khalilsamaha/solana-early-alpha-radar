import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {config} from './config.js';
import {Storage} from './core/storage.js';
import {Radar} from './core/radar.js';
import {startPumpPortalSource} from './adapters/pumpportal-source.js';
import {startServer} from './server/server.js';
const args=new Set(process.argv.slice(2));
const storage=new Storage(config.dataDir),radar=new Radar(config,storage);
let stopPump=()=>{},server,stopping=false;
async function shutdown(code=0) {
  if(stopping)return;stopping=true;
  const forced=setTimeout(()=>process.exit(1),30000);forced.unref();
  stopPump();if(server)server.close();
  await radar.stop();storage.close();clearTimeout(forced);process.exitCode=code;
}
radar.onFatal=()=>void shutdown(1);
if(args.has('--dashboard-only'))radar.health.mode='dashboard';
else {radar.startBackgroundLoops();stopPump=startPumpPortalSource(config,c=>radar.addCandidate(c),msg=>radar.log(msg),radar.health,e=>{
  storage.recordLaunch(e);
});}
if(!args.has('--scanner-only'))server=startServer(radar,config.dashboardPort,path.join(path.dirname(fileURLToPath(import.meta.url)),'../public'));
if(!config.heliusApiKey)radar.log('Security provider disabled; candidates remain visible but incomplete checks cap scores below default alerts.');
if(!config.notificationsEnabled)radar.log('Notification sending is OFF; paper alerts stay in the dashboard.');
process.on('SIGINT',()=>void shutdown());process.on('SIGTERM',()=>void shutdown());
