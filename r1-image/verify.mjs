// Image default: verify packaged bytes only. No service activation entry point.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
export function verify(){
  const raw=fs.readFileSync(path.join(root,'manifest.json'));
  const m=JSON.parse(raw);
  if(m.schema!==1||m.activation_authorized!==false||!m.files||!/^sha256:[a-f0-9]{64}$/.test(m.base_image))throw Error('manifest');
  const found=[];
  function walk(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){
    const p=path.join(dir,entry.name),rel=path.relative(root,p);
    if(entry.isSymbolicLink())throw Error('link');
    if(entry.isDirectory())walk(p);
    else if(entry.isFile()&&rel!=='manifest.json')found.push(rel);
    else if(!entry.isFile())throw Error('type');
  }}
  walk(root);found.sort();
  if(JSON.stringify(found)!==JSON.stringify(Object.keys(m.files).sort()))throw Error('members');
  for(const name of found)if(hash(fs.readFileSync(path.join(root,name)))!==m.files[name])throw Error('bytes');
  return {status:'image-bytes-verified',manifest_sha256:hash(raw),files:found.length,
    source_tree:m.source_tree,activation_authorized:false};
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
  try{console.log(JSON.stringify(verify()));}catch{console.error('image-verification-refused');process.exitCode=1;}
}
