// Optional synthetic scale exercise; creates and removes temporary databases.
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {DatabaseSync} from 'node:sqlite';import {pathToFileURL,fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {benchmark}=await import(pathToFileURL(root+'/statistics-lab/compact-benchmark.mjs'));
const large=process.argv.includes('--large'),sparse=process.argv.includes('--sparse'),covering=process.argv.includes('--covering-index');
const storeAt=process.argv.indexOf('--store');
const candidate=storeAt<0?root+'/statistics-lab/compact-store.mjs':path.resolve(process.argv[storeAt+1]||'');
if(process.argv.slice(2).some((a,i,all)=>!['--large','--sparse','--store','--covering-index'].includes(a)&&all[i-1]!=='--store'))throw Error('Use --large, --sparse, --covering-index or --store PATH');
const alertCount=large?25000:10000,researchCount=large?12000:5000,expectedRows=alertCount*4+researchCount*5;
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'radar-large-cache-'));
try{
 const database=dir+'/source.sqlite',cache=dir+'/compact.sqlite';fs.writeFileSync(cache,'');const db=new DatabaseSync(database);
 db.exec('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,id TEXT NOT NULL,at INTEGER NOT NULL,data TEXT NOT NULL,UNIQUE(kind,id));CREATE INDEX events_kind_seq ON events(kind,seq);CREATE INDEX events_at ON events(kind,at);BEGIN');const put=db.prepare('INSERT INTO events(kind,id,at,data) VALUES(?,?,?,?)');
 let sequence=0,filler=0;
 // Deterministic out-of-order timestamps exercise the competing production index.
 const record=(kind,id,at,data)=>{const stamp=at+((sequence*104729)%1000003);put.run(kind,id,stamp,data);sequence++;
  if(sparse){for(let j=0;j<8;j++){put.run('snapshots','padding-'+(++filler),at+((sequence*104729)%1000003),'x'.repeat(2048));sequence++;}}
 };
 const at=1700000000000,history='x'.repeat(7000);
 for(let i=0;i<alertCount;i++){
  const mint=('synthetic'+i).padEnd(44,'x');record('alerts',mint,at,JSON.stringify({id:mint+':'+at+':first',candidate:{mint,history},engineVersion:'0.2.9'}));
  for(const horizon of ['5m','15m','60m'])record('outcomes',mint+horizon,at,JSON.stringify({mint,alertAt:at,version:'price-v2',horizon,status:'observed',multiple:1.1,maxMultiple:1.2,coverage:'sampled',score:75,entryMarketCap:10000}));
 }
 for(let i=0;i<researchCount;i++){
  const id=('research'+i).padEnd(100,'x');record('research-entries',id,at,JSON.stringify({id,at,version:'research-0.2.9',cohort:'early-activity',history:history.slice(0,3000)}));
  for(const horizon of ['30s','1m','2m','5m'])record('research-outcomes',id+horizon,at,JSON.stringify({entryId:id,horizon,status:'observed',returnPct:-3,coverage:'sampled',history:history.slice(0,500)}));
 }
 db.exec('COMMIT');const indexStarted=performance.now();
 let indexBuildMs=null,indexAddedBytes=0,indexInstall=null,indexBeforeBytes=fs.statSync(database).size;
 if(covering){
  db.exec('PRAGMA journal_mode=WAL');
  const install=spawnSync('python3',['-E','-s',root+'/statistics-lab/source-index.py','--worker',database,'--apply'],{encoding:'utf8',timeout:45000,maxBuffer:16384});
  indexInstall=JSON.parse(install.stdout);if(install.status!==0||indexInstall.state!=='index-installed')throw Error('Synthetic index installation failed: '+JSON.stringify(indexInstall));
  indexBuildMs=performance.now()-indexStarted;
 }
 db.close();if(covering)indexAddedBytes=fs.statSync(database).size-indexBeforeBytes;const radar=root+'/scanner/src/core/radar.js';
 const r=await benchmark({database,cache,storeSource:fs.readFileSync(candidate,'utf8'),expected:{[radar]:createHash('sha256').update(fs.readFileSync(radar)).digest('hex')},radarUrl:pathToFileURL(radar).href,compactUrl:pathToFileURL(root+'/scanner/src/core/stats-memory.js').href,toleranceMs:120000,budgetMs:120000});
 console.log(JSON.stringify({fixtureVersion:"production-event-indexes-2",timestampOrder:"permuted",covering,indexBuildMs,indexAddedBytes,indexInstall,expectedRows,unrelatedRows:filler,sourceBytes:fs.statSync(database).size,state:r.state,error:r.error,diagnostic:r.diagnostic,cacheBytes:fs.statSync(cache).size},null,2));if(r.state!=='completed'||r.diagnostic.rounds[1].readRows!==0||r.diagnostic.rounds[1].reusedRows!==expectedRows)process.exitCode=1;
}finally{fs.rmSync(dir,{recursive:true,force:true});}
