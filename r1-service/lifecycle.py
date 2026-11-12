"""Durable, one-attempt handoff coordinator. Offline receipt schema; no live CLI."""
import os
from pathlib import Path
import re
import threading
import uuid

from capture import CaptureError, canonical, digest, exclusive_file, private_directory, sync_dir, strict_json
from handoff import path_without_links, read_private
from supervisor import owner_lock

ACTIONS=('disable_direct_restart','stop_direct','bind_endpoint','start_consumer',
         'start_owner','retire_research','stop_shared','restore_direct')
STATES=('prepared','direct_restart_disabled','direct_stopped','endpoint_bound',
        'consumer_ready','shared_active','research_retired','shared_stopped','rolled_back')
MAX_LOG=65536
HEX=re.compile(r'[0-9a-f]{64}\Z')
ID=re.compile(r'[0-9a-f]{32}\Z')


def valid_claim(row):
    if (not isinstance(row,dict) or set(row)!={'schema_version','mode','registration_id','source_digest','attempt_id'}
            or type(row['schema_version']) is not int or row['schema_version']!=1
            or row['mode']!='offline-service-lifecycle' or not isinstance(row['registration_id'],str)
            or not HEX.fullmatch(row['registration_id']) or not isinstance(row['source_digest'],str)
            or not HEX.fullmatch(row['source_digest']) or not isinstance(row['attempt_id'],str)
            or not ID.fullmatch(row['attempt_id'])):
        raise CaptureError('lifecycle-claim')


def operation_id(claim,index):
    return digest((canonical(claim)+':'+str(index)).encode())


def validate_receipt(action,row,op_id,known):
    fields={
        'disable_direct_restart':{'direct_id','restart_disabled'},
        'stop_direct':{'direct_id','direct_reaped','connection_closed'},
        'bind_endpoint':{'endpoint_id','endpoint_ready'},
        'start_consumer':{'endpoint_id','consumer_id','consumer_ready'},
        'start_owner':{'consumer_id','owner_id','upstream_attempts'},
        'retire_research':{'owner_id','admission_closed','cleanup'},
        'stop_shared':{'owner_id','consumer_id','owner_reaped','consumer_reaped','connection_closed'},
        'restore_direct':{'previous_direct_id','new_direct_id','restart_policy_restored'},
    }
    if (not isinstance(row,dict) or set(row)!=fields[action]|{'operation_id','scope'}
            or row['operation_id']!=op_id or row['scope']!='synthetic-process-lifecycle'):
        raise CaptureError('lifecycle-receipt')
    ids=dict(known)
    for key,value in row.items():
        if key.endswith('_id') and key!='operation_id':
            if not isinstance(value,str) or not ID.fullmatch(value):
                raise CaptureError('lifecycle-identity')
            reference='direct_id' if key=='previous_direct_id' else key
            if reference in ids and value!=ids[reference]:
                raise CaptureError('lifecycle-identity')
            ids[key]=value
    flags={'restart_disabled','direct_reaped','connection_closed','endpoint_ready',
           'consumer_ready','admission_closed','owner_reaped','consumer_reaped','restart_policy_restored'}
    if any(row[k] is not True for k in flags & set(row)):
        raise CaptureError('lifecycle-unconfirmed')
    if action=='start_owner' and (type(row['upstream_attempts']) is not int or row['upstream_attempts']!=1):
        raise CaptureError('lifecycle-connection-count')
    if action=='retire_research' and row['cleanup'] not in {'unsubscribed','upstream-aborted'}:
        raise CaptureError('lifecycle-cleanup')
    if action=='restore_direct' and row['new_direct_id'] in set(known.values()):
        raise CaptureError('lifecycle-identity-reused')
    # New identities must not alias another actor/endpoint.
    new={k:v for k,v in ids.items() if k not in known and k!='previous_direct_id'}
    if len(set(new.values()))!=len(new) or any(v in known.values() for v in new.values()):
        raise CaptureError('lifecycle-identity-reused')
    return ids


def replay(claim,raw):
    valid_claim(claim)
    if type(raw) is not bytes or len(raw)>MAX_LOG:
        raise CaptureError('lifecycle-log-bound')
    if raw and not raw.endswith(b'\n'):
        raise CaptureError('lifecycle-torn-log')
    previous=digest((canonical(claim)+'\n').encode());index=0;pending=False;known={};records=0
    for line in raw.splitlines():
        row=strict_json(line)
        if (not isinstance(row,dict) or set(row)!={'seq','kind','action','operation_id','previous','receipt','hash'}
                or type(row['seq']) is not int or row['seq']!=records+1
                or row['previous']!=previous or index>=len(ACTIONS)
                or row['action']!=ACTIONS[index] or row['operation_id']!=operation_id(claim,index)):
            raise CaptureError('lifecycle-log-order')
        body={k:v for k,v in row.items() if k!='hash'}
        if row['hash']!=digest(canonical(body).encode()) or canonical(row).encode()!=line:
            raise CaptureError('lifecycle-log-chain')
        if not pending:
            if row['kind']!='intent' or row['receipt'] is not None:
                raise CaptureError('lifecycle-intent')
            pending=True
        else:
            if row['kind']!='confirmed':raise CaptureError('lifecycle-confirmation')
            known=validate_receipt(row['action'],row['receipt'],row['operation_id'],known)
            pending=False;index+=1
        previous=row['hash'];records+=1
    return {'state':STATES[index],'pending_action':ACTIONS[index] if pending else None,
            'records':records,'last_hash':previous,'known':known,
            'complete':index==len(ACTIONS),'automatic_resume_allowed':False,
            'reconciliation_required':index!=len(ACTIONS)}


class Lifecycle:
    def __init__(self,registry,output,registration_id,source_digest):
        self.registry=path_without_links(registry);self.output=path_without_links(output)
        private_directory(self.registry);private_directory(self.output)
        if self.registry==self.output or self.registry in self.output.parents or self.output in self.registry.parents:
            raise CaptureError('lifecycle-path-overlap')
        self.claim={'schema_version':1,'mode':'offline-service-lifecycle','registration_id':registration_id,
                    'source_digest':source_digest,'attempt_id':uuid.uuid4().hex}
        valid_claim(self.claim)
        self.context=None;self.raw=b'';self.poisoned=False;self.mutex=threading.Lock();self.fd=None

    def __enter__(self):
        self.context=owner_lock(self.registry);self.context.__enter__()
        try:
            # One claim for the whole stable registry, independent of output path
            # or new registration ID. Never unlink this claim or its lock.
            exclusive_file(self.registry/'claim.json',(canonical(self.claim)+'\n').encode())
            sync_dir(self.registry)
            exclusive_file(self.output/'events.jsonl',b'')
            sync_dir(self.output)
            self.fd=os.open(self.output/'events.jsonl',os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_CLOEXEC)
            self.inode=os.fstat(self.fd).st_ino
            return self
        except BaseException:
            if self.fd is not None:os.close(self.fd);self.fd=None
            self.context.__exit__(*__import__('sys').exc_info());self.context=None
            raise

    def __exit__(self,*args):
        if self.fd is not None:os.close(self.fd);self.fd=None
        if self.context:self.context.__exit__(*args);self.context=None

    def _append(self,kind,action,receipt):
        state=replay(self.claim,self.raw);index=ACTIONS.index(action)
        body={'seq':state['records']+1,'kind':kind,'action':action,'operation_id':operation_id(self.claim,index),
              'previous':state['last_hash'],'receipt':receipt}
        row={**body,'hash':digest(canonical(body).encode())};line=(canonical(row)+'\n').encode()
        candidate=self.raw+line
        replay(self.claim,candidate)
        if (read_private(self.registry/'claim.json',4096)!=(canonical(self.claim)+'\n').encode()
                or read_private(self.output/'events.jsonl',MAX_LOG)!=self.raw
                or os.fstat(self.fd).st_ino!=self.inode
                or (self.output/'events.jsonl').lstat().st_ino!=self.inode):
            raise CaptureError('lifecycle-log-replaced')
        if os.write(self.fd,line)!=len(line):raise CaptureError('lifecycle-short-write')
        os.fsync(self.fd)
        self.raw=candidate

    def step(self,action,backend):
        if self.fd is None or self.poisoned or not self.mutex.acquire(blocking=False):
            raise CaptureError('lifecycle-not-admitted')
        try:
            state=replay(self.claim,self.raw)
            index=state['records']//2
            if state['pending_action'] or index>=len(ACTIONS) or action!=ACTIONS[index]:
                raise CaptureError('lifecycle-action-order')
            self._append('intent',action,None)  # Durable before ANY external side effect.
            row=backend.perform(action,operation_id(self.claim,index),dict(state['known']))
            validate_receipt(action,row,operation_id(self.claim,index),state['known'])
            self._append('confirmed',action,row)
            return replay(self.claim,self.raw)
        except BaseException:
            self.poisoned=True
            raise CaptureError('lifecycle-operation-unconfirmed') from None
        finally:self.mutex.release()


def inspect(registry,output):
    # Read-only recovery. It never executes, retries, restores direct or creates a file.
    claim=strict_json(read_private(Path(registry)/'claim.json',4096))
    raw=read_private(Path(output)/'events.jsonl',MAX_LOG)
    return replay(claim,raw)
