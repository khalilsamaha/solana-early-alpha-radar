// Synthetic discovery acceptance inside the candidate image. Never starts scanner loops.
import {verify} from './verify.mjs';
import {startPumpPortalSource} from './scanner/src/adapters/pumpportal-source.js';
let stop,finished=false,connections=0,fetches=0;
const tokens=[],creations=[];
const identity=verify();
globalThis.WebSocket=class{constructor(){connections++;throw Error('upstream forbidden');}};
globalThis.fetch=()=>{fetches++;throw Error('fetch forbidden');};
const timer=setTimeout(()=>finish('deadline',1),8000);
function finish(outcome,code=0){
 if(finished)return;finished=true;clearTimeout(timer);stop?.();
 console.log(JSON.stringify({identity,outcome,tokens:tokens.map(x=>x.discoverySource),
   creations:creations.length,upstream_attempts:connections,fetch_attempts:fetches}));process.exitCode=code;
}
try{
 if(process.argv.length!==3||process.argv[2]!=='/r1-ipc/discovery.sock')throw Error('endpoint');
 stop=startPumpPortalSource({pumpPortalSource:'shared',pumpPortalSocket:process.argv[2]},
   x=>tokens.push(x),()=>{},{success(){},failure(){finish('gap');}},x=>creations.push(x));
}catch{finish('endpoint-refused');}
