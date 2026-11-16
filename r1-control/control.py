"""Exact-target isolated Docker quiescence; no production launcher or retry mode."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
from datetime import datetime,timezone

IMAGE='sha256:8c6e3458333f587cb1a5110dbfdc2d6c98f2bdcc6892eb589ee08cf8b9b66140'
MANIFEST='e23bb7b4628496f5083fc26817f67f863bb248e412f9f83b0a4fdf64b6d1daf9'
LABEL='org.solana-radar.r1-control-review'
ACTOR="import {verify} from '/app/verify.mjs';if(verify().manifest_sha256!=='"+MANIFEST+"')throw Error('image');process.on('SIGTERM',()=>process.exit(0));setInterval(()=>{},1000);console.log('r1-control-ready');"
CMD=['--input-type=module','-e',ACTOR]
ENTRY=['/usr/bin/env','-i','PATH=/usr/local/bin:/usr/bin:/bin','LANG=C.UTF-8','node']
FORMAT='{"id":{{json .Id}},"image":{{json .Image}},"label":{{json (index .Config.Labels "'+LABEL+'")}},"user":{{json .Config.User}},"network":{{json .HostConfig.NetworkMode}},"readonly":{{json .HostConfig.ReadonlyRootfs}},"privileged":{{json .HostConfig.Privileged}},"restart":{{json .HostConfig.RestartPolicy.Name}},"mounts":{{json .Mounts}},"running":{{json .State.Running}},"exit_code":{{json .State.ExitCode}},"pid":{{json .State.Pid}},"started":{{json .State.StartedAt}},"finished":{{json .State.FinishedAt}},"memory":{{json .HostConfig.Memory}},"swap":{{json .HostConfig.MemorySwap}},"pids":{{json .HostConfig.PidsLimit}},"cpus":{{json .HostConfig.NanoCpus}},"init":{{json .HostConfig.Init}},"logging":{{json .HostConfig.LogConfig.Type}},"caps":{{json .HostConfig.CapDrop}},"security":{{json .HostConfig.SecurityOpt}},"cmd":{{json .Config.Cmd}},"entrypoint":{{json .Config.Entrypoint}}}'
ACTIONS=('disable_restart','stop')
def raw(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def digest(value):return hashlib.sha256(value).hexdigest()
def check(ok,code):
    if not ok:raise ValueError(code)
def now():return datetime.now(timezone.utc).isoformat()
def timestamp(value):
    check(isinstance(value,str),'timestamp-type')
    parsed=datetime.fromisoformat(value)
    check(parsed.tzinfo is not None and parsed.utcoffset().total_seconds()==0,'timestamp-zone')
    return parsed
def parse(value):
    def pairs(items):
        result={}
        for k,v in items:check(k not in result,'duplicate-key');result[k]=v
        return result
    return json.loads(value,object_pairs_hook=pairs,parse_constant=lambda _:check(False,'json-constant'))

def isolated(row,token):
    fixed={'image':IMAGE,'label':token,'user':'1000:1000','network':'none','readonly':True,
        'privileged':False,'mounts':[],'memory':128*1024**2,'swap':128*1024**2,'pids':32,
        'cpus':1000000000,'init':True,'logging':'none','caps':['ALL'],'cmd':CMD,'entrypoint':ENTRY}
    check(re.fullmatch('[a-f0-9]{32}',token or '') is not None,'token')
    check(all(type(row.get(k)) is type(v) and row[k]==v for k,v in fixed.items()),'isolation')
    check(row.get('security') in (['no-new-privileges:true'],['no-new-privileges']),'security')
    check(re.fullmatch('[a-f0-9]{64}',row.get('id','')) is not None,'id')
    check(type(row.get('pid')) is int and row['pid']>=0 and type(row.get('running')) is bool,'state')
    check(type(row.get('exit_code')) is int,'exit')
    for field in ('started','finished'):check(isinstance(row.get(field),str) and re.fullmatch('[0-9TZ:.+\\-]{20,40}',row[field]),'timestamp')
    check(row.get('restart') in ('no','unless-stopped'),'restart')

def before(row,expected):
    isolated(row,expected['label']);check(row==expected,'target-changed')

def after(action,row,prior):
    isolated(row,prior['label'])
    if action=='disable_restart':
        check(row=={**prior,'restart':'no'},'restart-unconfirmed')
    else:
        fixed={k:v for k,v in prior.items() if k not in ('pid','running','exit_code','finished')}
        check(all(row.get(k)==v for k,v in fixed.items()) and row['running'] is False and row['pid']==0
            and row['exit_code']==0 and not row['finished'].startswith('0001-'),'stop-unconfirmed')

def read(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        s=os.fstat(fd);check(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_uid==os.getuid() and not s.st_mode&0o077,'private-file')
        with os.fdopen(fd,'rb',closefd=False) as f:value=f.read(limit+1)
        check(len(value)<=limit,'file-bound');return value
    finally:os.close(fd)

def write_new(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:check(os.write(fd,value)==len(value),'short-write');os.fsync(fd)
    finally:os.close(fd)
    d=os.open(path.parent,os.O_DIRECTORY)
    try:os.fsync(d)
    finally:os.close(d)

def replay(claim,data):
    check(set(claim)=={'schema','scope','registry','target','source_sha256','created_utc'},'claim-fields')
    check(claim['schema']==1 and claim['scope']=='isolated-exact-target-control','claim-scope')
    check(isinstance(claim['source_sha256'],str) and re.fullmatch('[a-f0-9]{64}',claim['source_sha256']),'source-identity')
    isolated(claim['target'],claim['target']['label'])
    check(claim['target']['running'] is True and claim['target']['pid']>0 and claim['target']['restart']=='unless-stopped','initial-state')
    check(len(data)<=65536 and (not data or data.endswith(b'\n')),'log-boundary')
    last_time=timestamp(claim['created_utc'])
    previous=digest(raw(claim));pending=None;index=0;records=0;current=claim['target']
    for line in data.splitlines():
        row=parse(line);body={k:v for k,v in row.items() if k!='hash'}
        check(set(row)=={'seq','action','kind','previous','at','receipt','hash'} and raw(row).rstrip(b'\n')==line,'record-format')
        check(index<2 and row['seq']==records+1 and row['action']==ACTIONS[index] and row['previous']==previous and row['hash']==digest(raw(body)),'record-chain')
        current_time=timestamp(row['at']);check(current_time>=last_time,'clock-regressed');last_time=current_time
        if pending is None:
            check(row['kind']=='intent' and row['receipt'] is None,'intent');pending=ACTIONS[index]
        else:
            check(row['kind']=='confirmed' and isinstance(row['receipt'],dict),'receipt')
            receipt=row['receipt'];check(set(receipt)=={'scope','before','after','provider_connection_closed','billing_cutoff_verified'},'receipt-fields')
            check(receipt['scope']=='docker-local-state-only' and receipt['provider_connection_closed'] is False and receipt['billing_cutoff_verified'] is False,'remote-claim')
            before(receipt['before'],current);after(pending,receipt['after'],current)
            current=receipt['after'];pending=None;index+=1
        previous=row['hash'];records+=1
    return {'state':('prepared','restart-disabled','locally-stopped')[index],'pending_action':pending,
        'records':records,'last_hash':previous,'target':current,'local_stop_verified':index==2,
        'reconciliation_required':index!=2,'automatic_resume_allowed':False,
        'shared_start_authorized':False,'provider_connection_closed':False,'billing_cutoff_verified':False}

def inspect(registry):
    registry=Path(registry).absolute()
    check(all(not p.is_symlink() for p in [registry,*registry.parents]),'registry-link')
    claim_bytes=read(registry/'claim.json',16384);data=read(registry/'events.jsonl',65536)
    claim=parse(claim_bytes);check(claim['registry']==str(registry),'registry-binding')
    result=replay(claim,data)
    check(read(registry/'claim.json',16384)==claim_bytes and read(registry/'events.jsonl',65536)==data,'read-changed')
    return result

class Control:
    # Profile hooks retain the original isolated contract by default. Production
    # adapters must supply a distinct claim/replay schema; never relabel fixtures.
    scope = 'isolated-exact-target-control'
    actions = ACTIONS
    def replay(self, claim, data): return replay(claim, data)
    def before(self, row, expected): return before(row, expected)
    def after(self, action, row, prior): return after(action, row, prior)
    def receipt(self, prior, observed):
        return {'scope':'docker-local-state-only','before':prior,'after':observed,
                'provider_connection_closed':False,'billing_cutoff_verified':False}
    def __init__(self,registry,target,source_sha256,backend):
        self.registry=Path(registry).absolute();self.backend=backend;self.fd=None;self.poisoned=False;self.mutex=threading.Lock()
        check(all(not p.is_symlink() for p in [self.registry,*self.registry.parents]),'registry-link')
        s=self.registry.stat();check(stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid() and not s.st_mode&0o077,'registry-mode')
        self.claim={'schema':1,'scope':self.scope,'registry':str(self.registry),
            'target':target,'source_sha256':source_sha256,'created_utc':now()}
        self.replay(self.claim,b'');self.data=b''
    def __enter__(self):
        self.lock=os.open(self.registry/'lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            ls=os.fstat(self.lock);check(stat.S_ISREG(ls.st_mode) and ls.st_nlink==1 and ls.st_uid==os.getuid() and not ls.st_mode&0o077,'lock-mode')
            self.lock_inode=ls.st_ino
            fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            write_new(self.registry/'claim.json',raw(self.claim));write_new(self.registry/'events.jsonl',b'')
            self.fd=os.open(self.registry/'events.jsonl',os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW)
            self.inode=os.fstat(self.fd).st_ino;return self
        except BaseException:os.close(self.lock);raise
    def __exit__(self,*_):
        if self.fd is not None:os.close(self.fd);self.fd=None
        os.close(self.lock)
    def append(self,kind,action,receipt):
        state=self.replay(self.claim,self.data)
        body={'seq':state['records']+1,'action':action,'kind':kind,'previous':state['last_hash'],'at':now(),'receipt':receipt}
        line=raw({**body,'hash':digest(raw(body))});self.replay(self.claim,self.data+line)
        check(read(self.registry/'claim.json',16384)==raw(self.claim) and read(self.registry/'events.jsonl',65536)==self.data and
            (self.registry/'events.jsonl').stat().st_ino==self.inode and
            (self.registry/'lock').lstat().st_ino==self.lock_inode,'journal-changed')
        check(os.write(self.fd,line)==len(line),'short-write');os.fsync(self.fd);self.data+=line
    def step(self,action):
        check(self.fd is not None and not self.poisoned,'consumed-or-closed')
        check(self.mutex.acquire(blocking=False),'concurrent-operation')
        try:
            state=self.replay(self.claim,self.data);index=state['records']//2
            check(index<len(self.actions) and state['pending_action'] is None and action==self.actions[index],'action-order')
            expected=state['target'];observed=self.backend.observe(expected['id']);self.before(observed,expected)
            self.append('intent',action,None)
            # Recheck exact identity after durable intent, immediately before mutation.
            self.before(self.backend.observe(expected['id']),expected)
            ack=self.backend.mutate(action,expected['id']);check(ack==expected['id'],'command-ack')
            observed_after=self.backend.observe(expected['id']);self.after(action,observed_after,expected)
            self.append('confirmed',action,self.receipt(expected,observed_after))
            return self.replay(self.claim,self.data)
        except BaseException:self.poisoned=True;raise
        finally:self.mutex.release()
