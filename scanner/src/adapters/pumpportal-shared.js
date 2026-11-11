import fs from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import {TextDecoder} from 'node:util';
import {dispatchPumpPortalEvent} from './pumpportal-events.js';

const MAX_LINE=66000;

// Discovery-only framing: this consumer has no subscription or upstream client.
export function consumeSharedDiscovery(stream,onToken,onStatus=()=>{},health,onCreation=()=>{}) {
  let buffer=Buffer.alloc(0),sequence=0,stopped=false,lastMessage=Date.now();
  const decoder=new TextDecoder('utf-8',{fatal:true});
  const fail=()=>{
    if(stopped)return;
    stopped=true;clearInterval(watchdog);buffer=Buffer.alloc(0);
    health?.failure('pumpportal','Shared discovery unavailable; gap reported');
    onStatus('PumpPortal shared discovery unavailable; no direct fallback');
    stream.destroy();
  };
  const watchdog=setInterval(()=>{if(Date.now()-lastMessage>180000)fail();},30000);
  watchdog.unref();
  stream.on('data',chunk=>{
    if(stopped)return;
    try {
      // Node stream chunks are bounded; reject caller-provided oversized chunks
      // before combining them with the one bounded incomplete record.
      if(!Buffer.isBuffer(chunk)||chunk.length>65536)throw Error();
      buffer=Buffer.concat([buffer,chunk]);
      let end;
      while((end=buffer.indexOf(10))>=0){
        if(end+1>MAX_LINE)throw Error();
        const row=JSON.parse(decoder.decode(buffer.subarray(0,end)));
        buffer=buffer.subarray(end+1);
        if(!row||Object.keys(row).sort().join(',')!=='event,seq,v'||row.v!==1||
          !Number.isSafeInteger(row.seq)||row.seq!==sequence+1||!row.event||Array.isArray(row.event)||
          !['create','migration','migrate'].includes(row.event.txType)||
          typeof row.event.mint!=='string'||!/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(row.event.mint))throw Error();
        sequence=row.seq;lastMessage=Date.now();
        health?.success('pumpportal');
        dispatchPumpPortalEvent(row.event,onToken,onStatus,onCreation,lastMessage);
      }
      if(buffer.length>=MAX_LINE)throw Error();
    } catch {fail();}
  });
  stream.on('error',fail);stream.on('end',fail);stream.on('close',fail);
  return ()=>{if(stopped)return;stopped=true;clearInterval(watchdog);buffer=Buffer.alloc(0);stream.destroy();};
}

export function connectSharedDiscovery(socketPath,onToken,onStatus=()=>{},health,onCreation=()=>{}) {
  // A same-UID, private Unix endpoint only. Never parse a URL or fall back to TCP.
  if(typeof socketPath!=='string'||!path.isAbsolute(socketPath)||socketPath!==path.normalize(socketPath)||
     Buffer.byteLength(socketPath)>100)throw Error('Invalid shared discovery endpoint');
  let current=path.parse(socketPath).root;
  for(const part of socketPath.split(path.sep).filter(Boolean)){
    current=path.join(current,part);
    if(fs.lstatSync(current).isSymbolicLink())throw Error('Unsafe shared discovery endpoint');
  }
  const parent=fs.lstatSync(path.dirname(socketPath)),socket=fs.lstatSync(socketPath);
  if(!parent.isDirectory()||parent.uid!==process.getuid()||(parent.mode&0o077)||
     !socket.isSocket()||socket.uid!==process.getuid()||(socket.mode&0o077))
    throw Error('Unsafe shared discovery endpoint');
  const stream=net.createConnection({path:socketPath});
  stream.setTimeout(3000,()=>stream.destroy());
  stream.once('connect',()=>stream.setTimeout(0));
  return consumeSharedDiscovery(stream,onToken,onStatus,health,onCreation);
}
