"""Durable offline handoff/rollback coordinator; backend injection only, no live CLI."""
import os
from pathlib import Path
import re
import sys
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'r1-control'))
import control as c
import check_control

ACTIONS=('bind_endpoint','start_consumer','start_owner','retire_research','stop_shared','restore_direct')
STATES=('direct-stopped','endpoint-bound','consumer-ready','shared-active','research-retired','shared-stopped','rolled-back')
HEX=re.compile('[a-f0-9]{64}')
MAX_LOG=131072

def source_pins():
    repo=Path(__file__).resolve().parents[1]
    names=[*sorted((repo/'r1-handoff').glob('*.py')),repo/'r1-handoff/README.md']
    return {**check_control.pins(),**{str(p.relative_to(repo)):c.digest(p.read_bytes()) for p in names}}

def valid_proof(proof):
    c.check(isinstance(proof,dict) and set(proof)=={'claim','events'},'control-proof')
    c.check(isinstance(proof['events'],str) and len(proof['events'].encode())<=65536,'control-proof-bound')
    state=c.replay(proof['claim'],proof['events'].encode())
    c.check(proof['claim']['source_sha256']==c.digest(c.raw(check_control.pins())),'control-source')
    c.check(state['local_stop_verified'] and state['pending_action'] is None and state['records']==4,'direct-not-stopped')
    # Only the already validated network-none fixture is covered by this coordinator.
    c.check(state['target']['network']=='none','offline-only')
    return state

def config_identity(target):
    return c.digest(c.raw({k:v for k,v in target.items() if k not in ('id','label','pid','started','finished','running','exit_code','restart')}))

def claim_check(claim):
    c.check(isinstance(claim,dict) and set(claim)=={'schema','scope','registry','source_sha256','control_proof','created_utc'},'claim-fields')
    c.check(type(claim['schema']) is int and claim['schema']==1 and claim['scope']=='offline-handoff-v1','claim-scope')
    c.check(claim['source_sha256']==source_pins(),'handoff-source')
    path=Path(claim['registry']);c.check(path.is_absolute() and str(path)==os.path.normpath(str(path)),'registry-path')
    c.timestamp(claim['created_utc']);return valid_proof(claim['control_proof'])

def op_id(claim,index):return c.digest(c.raw(claim)+str(index).encode())
def hexid(value):return isinstance(value,str) and HEX.fullmatch(value) is not None

def validate(action,receipt,claim,index,known):
    fields={'bind_endpoint':{'endpoint_id','endpoint_path'},
        'start_consumer':{'endpoint_id','consumer_id','image','ready'},
        'start_owner':{'endpoint_id','consumer_id','owner_id','synthetic_attempts'},
        'retire_research':{'owner_id','admission_closed','cleanup','discovery_continues'},
        'stop_shared':{'owner_id','consumer_id','owner_reaped','consumer_reaped','local_connection_closed'},
        'restore_direct':{'previous_direct_id','new_direct_id','image','config_sha256','restart_policy','ready'}}
    base={'scope','operation_id','provider_connection_closed','billing_cutoff_verified'}
    c.check(isinstance(receipt,dict) and set(receipt)==fields[action]|base,'receipt-fields')
    c.check(receipt['scope']=='isolated-handoff-adapter' and receipt['operation_id']==op_id(claim,index),'receipt-binding')
    c.check(receipt['provider_connection_closed'] is False and receipt['billing_cutoff_verified'] is False,'remote-claim')
    ids=dict(known)
    for key,value in receipt.items():
        if key.endswith('_id') and key!='operation_id':
            c.check(hexid(value),'actor-identity')
            old='direct_id' if key=='previous_direct_id' else key
            if old in known:c.check(value==known[old],'actor-generation')
            elif value in known.values():c.check(False,'actor-alias')
            else:
                c.check(value not in ids.values(),'actor-alias');ids[key]=value
    if action=='bind_endpoint':
        c.check(receipt['endpoint_path']==str(Path(claim['registry'])/'discovery.sock'),'endpoint-binding')
    if action=='start_consumer':c.check(receipt['image']==c.IMAGE and receipt['ready'] is True,'consumer-not-ready')
    if action=='start_owner':c.check(type(receipt['synthetic_attempts']) is int and receipt['synthetic_attempts']==1,'owner-attempts')
    if action=='retire_research':
        c.check(receipt['admission_closed'] is True and receipt['cleanup'] in ('unsubscribed','upstream-aborted'),'research-cleanup')
        c.check(type(receipt['discovery_continues']) is bool and receipt['discovery_continues']==(receipt['cleanup']=='unsubscribed'),'discovery-outcome')
    if action=='stop_shared':c.check(all(receipt[k] is True for k in ('owner_reaped','consumer_reaped','local_connection_closed')),'shared-not-stopped')
    if action=='restore_direct':
        original=claim['control_proof']['claim']['target']
        c.check(receipt['image']==c.IMAGE and receipt['config_sha256']==config_identity(original) and
            receipt['restart_policy']==original['restart'] and receipt['ready'] is True,'restore-config')
    return ids

def replay(claim,data):
    initial=claim_check(claim)
    c.check(type(data) is bytes and len(data)<=MAX_LOG and (not data or data.endswith(b'\n')),'log-boundary')
    known={'direct_id':initial['target']['id']};index=0;pending=None;records=0
    previous=c.digest(c.raw(claim));last_time=c.timestamp(claim['created_utc']);research=None
    for line in data.splitlines():
        row=c.parse(line);body={k:v for k,v in row.items() if k!='hash'}
        c.check(set(row)=={'seq','action','kind','previous','at','receipt','hash'} and c.raw(row).rstrip(b'\n')==line,'record-format')
        c.check(index<len(ACTIONS) and type(row['seq']) is int and row['seq']==records+1 and
            row['action']==ACTIONS[index] and row['previous']==previous and row['hash']==c.digest(c.raw(body)),'record-chain')
        stamp=c.timestamp(row['at']);c.check(stamp>=last_time,'clock-regressed');last_time=stamp
        if pending is None:
            c.check(row['kind']=='intent' and row['receipt'] is None,'intent');pending=ACTIONS[index]
        else:
            c.check(row['kind']=='confirmed','confirmation')
            known=validate(pending,row['receipt'],claim,index,known)
            if pending=='retire_research':research=row['receipt']['cleanup']
            pending=None;index+=1
        previous=row['hash'];records+=1
    return {'state':STATES[index],'pending_action':pending,'records':records,'last_hash':previous,'known':known,
        'complete':index==len(ACTIONS),'research_cleanup':research,'reconciliation_required':index!=len(ACTIONS),
        'automatic_resume_allowed':False,'production_activation_authorized':False,
        'provider_connection_closed':False,'billing_cutoff_verified':False}

def inspect(registry):
    registry=Path(registry).absolute()
    c.check(all(not p.is_symlink() for p in [registry,*registry.parents]),'registry-link')
    claim_raw=c.read(registry/'handoff-claim.json',65536);data=c.read(registry/'handoff-events.jsonl',MAX_LOG)
    claim=c.parse(claim_raw);c.check(claim['registry']==str(registry),'registry-binding')
    result=replay(claim,data)
    c.check(c.read(registry/'handoff-claim.json',65536)==claim_raw and c.read(registry/'handoff-events.jsonl',MAX_LOG)==data,'read-changed')
    return result

class Coordinator:
    def __init__(self,registry,proof,backend):
        self.registry=Path(registry).absolute();self.backend=backend;self.fd=None;self.poisoned=False
        self.mutex=threading.Lock();self.data=b''
        c.check(all(not p.is_symlink() for p in [self.registry,*self.registry.parents]),'registry-link')
        s=self.registry.stat();c.check(self.registry.is_dir() and s.st_uid==os.getuid() and not s.st_mode&0o077,'registry-mode')
        self.claim={'schema':1,'scope':'offline-handoff-v1','registry':str(self.registry),
            'source_sha256':source_pins(),'control_proof':proof,'created_utc':c.now()}
        claim_check(self.claim)
    def __enter__(self):
        import fcntl,stat
        self.lock=os.open(self.registry/'handoff.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            ls=os.fstat(self.lock);c.check(stat.S_ISREG(ls.st_mode) and ls.st_nlink==1 and ls.st_uid==os.getuid() and not ls.st_mode&0o077,'lock-mode')
            self.lock_inode=ls.st_ino;fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            c.write_new(self.registry/'handoff-claim.json',c.raw(self.claim));c.write_new(self.registry/'handoff-events.jsonl',b'')
            self.fd=os.open(self.registry/'handoff-events.jsonl',os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW)
            self.inode=os.fstat(self.fd).st_ino;return self
        except BaseException:os.close(self.lock);raise
    def __exit__(self,*_):
        if self.fd is not None:os.close(self.fd);self.fd=None
        os.close(self.lock)
    def append(self,kind,action,receipt):
        state=replay(self.claim,self.data)
        body={'seq':state['records']+1,'action':action,'kind':kind,'previous':state['last_hash'],'at':c.now(),'receipt':receipt}
        line=c.raw({**body,'hash':c.digest(c.raw(body))});replay(self.claim,self.data+line)
        c.check(c.read(self.registry/'handoff-claim.json',65536)==c.raw(self.claim) and
            c.read(self.registry/'handoff-events.jsonl',MAX_LOG)==self.data and
            (self.registry/'handoff-events.jsonl').lstat().st_ino==self.inode and
            (self.registry/'handoff.lock').lstat().st_ino==self.lock_inode,'journal-changed')
        c.check(os.write(self.fd,line)==len(line),'short-write');os.fsync(self.fd);self.data+=line
    def step(self,action):
        c.check(self.fd is not None and not self.poisoned,'consumed-or-closed')
        c.check(self.mutex.acquire(blocking=False),'concurrent-operation')
        try:
            state=replay(self.claim,self.data);index=state['records']//2
            c.check(index<len(ACTIONS) and state['pending_action'] is None and action==ACTIONS[index],'action-order')
            self.append('intent',action,None)
            receipt=self.backend.perform(action,op_id(self.claim,index),dict(state['known']))
            validate(action,receipt,self.claim,index,state['known']);self.append('confirmed',action,receipt)
            return replay(self.claim,self.data)
        except BaseException:self.poisoned=True;raise
        finally:self.mutex.release()
