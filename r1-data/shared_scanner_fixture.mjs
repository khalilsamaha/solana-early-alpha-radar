// Fixed synthetic acceptance consumer. No scanner loops, provider or credentials.
import {DatabaseSync} from 'node:sqlite';
import {LaunchRegistry} from '../scanner/src/core/launch-registry.js';
import {consumeSharedDiscovery} from '../scanner/src/adapters/pumpportal-shared.js';
import {startPumpPortalSource} from '../scanner/src/adapters/pumpportal-source.js';

globalThis.WebSocket=class{constructor(){throw Error('upstream forbidden');}};
globalThis.fetch=()=>{throw Error('fetch forbidden');};
const db=new DatabaseSync(':memory:');
db.exec('CREATE TABLE kv(key TEXT PRIMARY KEY,data TEXT); CREATE TABLE candidates(mint TEXT PRIMARY KEY,data TEXT)');
const registry=new LaunchRegistry(db),tokens=[];
let failures=0,finished=false,stop;
const timer=setTimeout(()=>finish(1),12000);
function finish(code=0){
  if(finished)return;finished=true;clearTimeout(timer);stop?.();
  const result={tokens:tokens.length,creations:registry.health().retained,discovery_gaps:failures,
    sources:tokens.map(x=>x.discoverySource),upstream_connections_opened:0};
  db.close();process.stdout.write(JSON.stringify(result)+'\n');process.exitCode=code;
}
const health={success(){},failure(){failures++;finish();}};
try{
  const args=[x=>{if(tokens.length>=32)throw Error();tokens.push(x);},()=>{},health,e=>registry.record(e)];
  if(process.argv[2]==='pipe')stop=consumeSharedDiscovery(process.stdin,...args);
  else if(process.argv[2]==='unix'&&process.argv.length===4)
    stop=startPumpPortalSource({pumpPortalSource:'shared',pumpPortalSocket:process.argv[3]},...args);
  else throw Error();
  process.stdout.write('ready\n');
}catch{finish(1);}
