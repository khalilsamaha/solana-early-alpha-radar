// Local development only. The Kali path uses the accepted image-contained probe.
import {startPumpPortalSource} from '../scanner/src/adapters/pumpportal-source.js';
const endpoint=process.argv[2];
if(process.argv.length!==3||!endpoint.startsWith('/')||!endpoint.endsWith('/discovery.sock'))throw Error('endpoint');
let attempts=0,fetches=0,stop,done=false,gaps=0,creations=0,tokens=[];
globalThis.WebSocket=class{constructor(){attempts++;throw Error('upstream forbidden');}};
globalThis.fetch=()=>{fetches++;throw Error('fetch forbidden');};
const timer=setTimeout(()=>finish(1),30000);
function emit(v){process.stdout.write(JSON.stringify(v)+'\n');}
function finish(code=0){if(done)return;done=true;clearTimeout(timer);stop?.();
 emit({event:'finished',tokens,creations,gaps,upstream_attempts:attempts,fetch_attempts:fetches,image_verified:false,development:true});process.exitCode=code;}
stop=startPumpPortalSource({pumpPortalSource:'shared',pumpPortalSocket:endpoint},
 x=>{if(tokens.length>=32)throw Error('bound');tokens.push(x.discoverySource);emit({event:'discovery',source:x.discoverySource});},
 ()=>{},{success(){},failure(){gaps++;finish();}},()=>{creations++;});
emit({event:'ready',image_verified:false,development:true});
