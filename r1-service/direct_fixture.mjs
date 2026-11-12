// Actual direct adapter, in-memory WebSocket peer. No external connection.
import {startPumpPortalSource} from '../scanner/src/adapters/pumpportal-source.js';
let attempts=0,closed=false,subscriptions=[],stop,finished=false;
class Peer {
  constructor(){if(++attempts!==1)throw Error('retry forbidden');this.readyState=1;this.handlers={};queueMicrotask(()=>this.handlers.open?.());}
  addEventListener(name,handler){this.handlers[name]=handler;}
  send(raw){const row=JSON.parse(raw);subscriptions.push(row.method);if(subscriptions.length===2){
    if(subscriptions.join(',')!=='subscribeNewToken,subscribeMigration')throw Error('subscription mismatch');
    process.stdout.write('ready\n');}}
  close(){closed=true;this.readyState=3;this.handlers.close?.();}
}
globalThis.WebSocket=Peer;globalThis.fetch=()=>{throw Error('network forbidden');};
const timer=setTimeout(()=>finish(1),45000);
function finish(code=0){if(finished)return;finished=true;clearTimeout(timer);stop?.();
 process.stdout.write(JSON.stringify({attempts,closed,subscriptions,provider_connections_opened:0})+'\n');process.exitCode=code;}
process.on('SIGTERM',()=>finish());process.on('SIGINT',()=>finish());
try{stop=startPumpPortalSource({pumpPortalSource:'direct',pumpPortalApiKey:'SYNTHETIC'},()=>{});}
catch{finish(1);}
