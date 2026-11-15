// Image-contained scanner modules; this source-bound probe starts no scanner loops.
import {pathToFileURL} from 'node:url';
const mode=process.argv[1],endpoint=process.argv[2];
const development=mode==='--development-pipe'&&process.env.R1_DEVELOPMENT==='1';
let root='/app/scanner',verified=false;
if(development)root=endpoint;
else{
 if(mode!=='--unix'||endpoint!=='/r1-ipc/discovery.sock')throw Error('mode');
 const {verify}=await import('/app/verify.mjs');
 if(verify().manifest_sha256!=='e23bb7b4628496f5083fc26817f67f863bb248e412f9f83b0a4fdf64b6d1daf9')throw Error('image');
 verified=true;
}
const {startPumpPortalSource}=await import(pathToFileURL(root+'/src/adapters/pumpportal-source.js'));
const {consumeSharedDiscovery}=await import(pathToFileURL(root+'/src/adapters/pumpportal-shared.js'));
let attempts=0,fetches=0,stop,done=false,gaps=0,creations=0,tokens=[];
globalThis.WebSocket=class{constructor(){attempts++;throw Error('upstream forbidden');}};
globalThis.fetch=()=>{fetches++;throw Error('fetch forbidden');};
const timer=setTimeout(()=>finish(1),45000);
function emit(v){process.stdout.write(JSON.stringify(v)+'\n');}
function finish(code=0){if(done)return;done=true;clearTimeout(timer);stop?.();
 emit({event:'finished',tokens,creations,gaps,upstream_attempts:attempts,fetch_attempts:fetches,image_verified:verified,development});process.exitCode=code;}
const args=[x=>{tokens.push(x.discoverySource);emit({event:'discovery',source:x.discoverySource});},()=>{},
 {success(){},failure(){gaps++;finish();}},()=>{creations++;}];
stop=development?consumeSharedDiscovery(process.stdin,...args):startPumpPortalSource({pumpPortalSource:'shared',pumpPortalSocket:endpoint},...args);
emit({event:'ready',image_verified:verified,development});
