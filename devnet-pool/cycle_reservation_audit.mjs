// Read-only bridge to the same reservation check used by the signer.
// No signer import, key access, network, or filesystem write.
import fs from 'node:fs';
import path from 'node:path';
import {verifyCycleReservation} from './cycle_policy.mjs';
const check=v=>{if(!v)throw new Error('refused');};
function read(p,max){
 const fd=fs.openSync(p,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
 try{const s=fs.fstatSync(fd);check(s.isFile()&&s.uid===process.getuid()&&(s.mode&0o777)===0o600&&s.nlink===1&&s.size<=max);
  return JSON.parse(fs.readFileSync(fd));
 }finally{fs.closeSync(fd);}
}
try{
 const raw=fs.readFileSync(0);check(raw.length<=4096);const r=JSON.parse(raw);
 check(Object.keys(r).join('|')==='directory'&&path.isAbsolute(r.directory)&&fs.realpathSync(r.directory)===r.directory);
 const home=path.join(r.directory,'controlled-cycle-0002'),child=path.join(home,'swap-execution-v1');
 const state=verifyCycleReservation(r.directory,home,read(path.join(child,'plan.json'),32768),
  read(path.join(child,'preflight.json'),4*1024*1024),'entry');
 check(Object.keys(state.legs).join('|')==='entry');
 process.stdout.write(JSON.stringify({reservationVerified:true,preparationHashBasis:'sealed-file-bytes-v1'}));
}catch{process.stderr.write('Read-only reservation audit refused.\n');process.exitCode=1;}
