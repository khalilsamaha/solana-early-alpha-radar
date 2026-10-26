// Optional synthetic scale exercise; creates and removes temporary databases.
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {DatabaseSync} from 'node:sqlite';import {pathToFileURL,fileURLToPath} from 'node:url';import {createHash} from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const {benchmark}=await import(pathToFileURL(root+'/statistics-lab/compact-benchmark.mjs'));
const large=process.argv.includes('--large');
if(process.argv.slice(2).some(a=>a!=='--large'))throw Error('Use only --large or no arguments');
const alertCount=large?25000:10000,researchCount=large?12000:5000,expectedRows=alertCount*4+researchCount*5;
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'radar-large-cache-'));
try{
 const database=dir+'/source.sqlite',cache=dir+'/compact.sqlite';fs.writeFileSync(cache,'');const db=new DatabaseSync(database);
 db.exec('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT,id TEXT,at INTEGER,data TEXT);CREATE INDEX events_kind_seq ON events(kind,seq);BEGIN');const put=db.prepare('INSERT INTO events(kind,id,at,data) VALUES(?,?,?,?)');
 const at=1700000000000,history='x'.repeat(7000);
 for(let i=0;i<alertCount;i++){
  const mint=('synthetic'+i).padEnd(44,'x');put.run('alerts',mint,at,JSON.stringify({id:mint+':'+at+':first',candidate:{mint,history},engineVersion:'0.2.9'}));
  for(const horizon of ['5m','15m','60m'])put.run('outcomes',mint+horizon,at,JSON.stringify({mint,alertAt:at,version:'price-v2',horizon,status:'observed',multiple:1.1,maxMultiple:1.2,coverage:'sampled',score:75,entryMarketCap:10000}));
 }
 for(let i=0;i<researchCount;i++){
  const id=('research'+i).padEnd(100,'x');put.run('research-entries',id,at,JSON.stringify({id,at,version:'research-0.2.9',cohort:'early-activity',history:history.slice(0,3000)}));
  for(const horizon of ['30s','1m','2m','5m'])put.run('research-outcomes',id+horizon,at,JSON.stringify({entryId:id,horizon,status:'observed',returnPct:-3,coverage:'sampled',history:history.slice(0,500)}));
 }
 db.exec('COMMIT');db.close();const radar=root+'/scanner/src/core/radar.js';
 const r=await benchmark({database,cache,storeSource:fs.readFileSync(root+'/statistics-lab/compact-store.mjs','utf8'),expected:{[radar]:createHash('sha256').update(fs.readFileSync(radar)).digest('hex')},radarUrl:pathToFileURL(radar).href,compactUrl:pathToFileURL(root+'/scanner/src/core/stats-memory.js').href,toleranceMs:120000,budgetMs:120000});
 console.log(JSON.stringify({expectedRows,state:r.state,error:r.error,diagnostic:r.diagnostic,cacheBytes:fs.statSync(cache).size},null,2));if(r.state!=='completed'||r.diagnostic.rounds[1].readRows!==0||r.diagnostic.rounds[1].reusedRows!==expectedRows)process.exitCode=1;
}finally{fs.rmSync(dir,{recursive:true,force:true});}
