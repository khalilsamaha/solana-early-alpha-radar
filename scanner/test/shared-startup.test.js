import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {Health} from '../src/core/health.js';
import {readConfig} from '../src/config.js';

test('shared discovery health tracks waiting, success and gaps without an upstream key',()=>{
  const config=readConfig({PUMPPORTAL_SOURCE:'shared',PUMPPORTAL_SOCKET:'/tmp/fixture/discovery.sock'});
  const health=new Health(config,()=>1000);
  assert.equal(health.snapshot(config).providers.pumpportal.state,'waiting');
  assert.equal(health.snapshot(config).providers.pumpportal.enabled,true);
  health.success('pumpportal');
  assert.equal(health.snapshot(config).providers.pumpportal.state,'ok');
  health.failure('pumpportal','Shared discovery unavailable; gap reported');
  assert.equal(health.snapshot(config).providers.pumpportal.state,'error');
});
test('direct provider health keeps its existing key requirement',()=>{
  for(const key of ['', 'synthetic-fixture-key']){
    const config=readConfig({PUMPPORTAL_API_KEY:key});
    assert.equal(new Health(config).snapshot(config).providers.pumpportal.enabled,Boolean(key));
  }
});
for(const kind of ['missing','regular-file','symlink'])test(`${kind} shared endpoint refuses full startup before storage or network attempts`,()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'r1-start-'));
  const endpoint=path.join(root,'discovery.sock'),data=path.join(root,'unused-data');
  try{
    if(kind==='regular-file')fs.writeFileSync(endpoint,'fixture',{mode:0o600});
    if(kind==='symlink')fs.symlinkSync(path.join(root,'missing'),endpoint);
    const entry=pathToFileURL(fileURLToPath(new URL('../src/index.js',import.meta.url))).href;
    const script=`let sockets=0,requests=0;globalThis.WebSocket=class{constructor(){sockets++;throw Error('blocked');}};globalThis.fetch=async()=>{requests++;throw Error('blocked');};let refused=false;try{await import(${JSON.stringify(entry)});}catch{refused=true;}console.log(JSON.stringify({refused,sockets,requests}));`;
    const result=spawnSync(process.execPath,['--disable-warning=ExperimentalWarning','--input-type=module','-e',script],{
      cwd:root,env:{PATH:process.env.PATH,LANG:'C.UTF-8',PUMPPORTAL_SOURCE:'shared',PUMPPORTAL_SOCKET:endpoint,DATA_DIR:data},
      encoding:'utf8',timeout:3000,maxBuffer:65536});
    assert.equal(result.status,0,result.stderr);assert.equal(result.error,undefined);
    assert.deepEqual(JSON.parse(result.stdout),{refused:true,sockets:0,requests:0});
    assert.equal(fs.existsSync(data),false);
  }finally{fs.rmSync(root,{recursive:true,force:true});}
});
