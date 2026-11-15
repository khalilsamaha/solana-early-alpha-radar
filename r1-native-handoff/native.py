"""Image-bound native adapters; offline synthetic owner only."""
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parent
sys.path.insert(0,str(REPO/'r1-handoff'))
import coordinator as h
c=h.c;image=h.check_control.image
CONSUMER=(ROOT/'consumer.mjs').read_text()

def pins():
    return {**h.source_pins(),**{str(p.relative_to(REPO)):c.digest(p.read_bytes()) for p in
        [*sorted(ROOT.glob('*.py')),ROOT/'consumer.mjs',ROOT/'README.md',REPO/'scripts/r1-native-handoff-kali.sh']}}

def proc_identity(pid):
    text=Path('/proc',str(pid),'stat').read_text();fields=text[text.rindex(')')+2:].split()
    return {'pid':pid,'ppid':int(fields[1]),'start_ticks':int(fields[19])}

def line(process,seconds=6):
    data=bytearray();deadline=time.monotonic()+seconds
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout,selectors.EVENT_READ)
        while not data.endswith(b'\n'):
            left=deadline-time.monotonic();c.check(left>0 and selector.select(left),'child-read-timeout')
            b=os.read(process.stdout.fileno(),1);c.check(b and len(data)<4096,'child-output');data.extend(b)
    return bytes(data)

def reap(process,*,terminate=False):
    if process is None:return
    try:
        if terminate and process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait(timeout=2)
        tail=process.stdout.read(4097) if process.stdout and not process.stdout.closed else b''
        c.check(len(tail)<=4096 and not image.DIAGNOSTIC.search(tail.decode(errors='replace')),'child-diagnostic')
        if not terminate:c.check(process.returncode==0 and tail==b'','child-terminal')
        return tail
    finally:
        for stream in (process.stdin,process.stdout):
            if stream:stream.close()

def consumer_isolation(row,token,registry):
    c.check(row.get('cmd')==['--input-type=module','-e',CONSUMER,'--','--unix','/r1-ipc/discovery.sock'],'consumer-command')
    mounts=row.get('mounts');c.check(isinstance(mounts,list) and len(mounts)==1,'consumer-mounts')
    m=mounts[0];c.check(m.get('Type')=='bind' and m.get('Source')==str(registry) and
        m.get('Destination')=='/r1-ipc' and m.get('RW') is False,'consumer-mount')
    c.isolated({**row,'cmd':c.CMD,'mounts':[]},token)
    c.check(row['restart']=='no','consumer-restart')

class Actor:
    def __init__(self,cli,role,registry,development=False,read_fd=None):
        self.cli=cli;self.role=role;self.registry=registry;self.development=development;self.read_fd=read_fd
        self.token=uuid.uuid4().hex;self.name='radar-r1-native-'+self.token
        self.cid=None;self.process=None;self.attempted=False;self.created=False;self.removed=False;self.ready=False
        self.initial=None;self.observations=[];self.result=None;self.model=None;self.stopped_snapshot=None;self.cleanup_tail=b''
    def validate(self,row):
        if self.role=='direct':c.isolated(row,self.token)
        else:consumer_isolation(row,self.token,self.registry)
        c.check(self.cid is None or row['id']==self.cid,'actor-id')
    def observe(self):
        if self.development:
            row=dict(self.model)
            if self.process and self.process.poll() is not None:
                row.update(running=False,pid=0,exit_code=self.process.returncode,finished=self.finished)
        else:row=c.parse(image.bounded(self.cli+['inspect','--type','container','--format',c.FORMAT,self.cid or self.name]))
        self.validate(row);self.observations.append(row);return row
    def start(self):
        c.check(not self.attempted,'actor-reuse');self.attempted=True
        if self.development:
            from test_control import target
            self.cid=c.digest(self.token.encode());self.finished=c.now()
            args=[shutil.which('node'),'--input-type=module','-e']
            if self.role=='direct':args+=["process.on('SIGTERM',()=>process.exit(0));setInterval(()=>{},1000);console.log('r1-control-ready');"]
            else:args+=[CONSUMER,'--','--development-pipe',str(REPO/'scanner')]
            self.process=subprocess.Popen(args,stdin=self.read_fd if self.role=='consumer' else subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env={**image.host.ENV,'R1_DEVELOPMENT':'1'},start_new_session=True,bufsize=0)
            self.model={**target(),'id':self.cid,'label':self.token,'pid':self.process.pid,'started':c.now()}
            if self.role=='consumer':self.model.update(restart='no',cmd=['--input-type=module','-e',CONSUMER,'--','--unix','/r1-ipc/discovery.sock'],
                mounts=[{'Type':'bind','Source':str(self.registry),'Destination':'/r1-ipc','RW':False}])
            self.created=True
        else:
            args=['create','--name',self.name,'--label',c.LABEL+'='+self.token,'--pull=never','--network=none',
                '--restart='+('unless-stopped' if self.role=='direct' else 'no'),'--read-only','--init','--user=1000:1000',
                '--cap-drop=ALL','--security-opt=no-new-privileges:true','--memory=128m','--memory-swap=128m',
                '--cpus=1','--pids-limit=32','--log-driver=none','--no-healthcheck']
            if self.role=='consumer':args+=['--mount',f'type=bind,src={self.registry},dst=/r1-ipc,readonly']
            args+=[c.IMAGE]+(c.CMD if self.role=='direct' else ['--input-type=module','-e',CONSUMER,'--','--unix','/r1-ipc/discovery.sock'])
            self.cid=image.bounded(self.cli+args).decode().strip();c.check(re.fullmatch('[a-f0-9]{64}',self.cid),'create-id');self.created=True
            c.check(self.observe()['running'] is False,'created-running')
            self.process=subprocess.Popen(self.cli+['start','--attach',self.cid],stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=image.host.ENV,start_new_session=True,bufsize=0)
        ready=line(self.process)
        expected=b'r1-control-ready\n' if self.role=='direct' else c.raw({'event':'ready','image_verified':not self.development,'development':self.development})
        if self.role=='direct':c.check(ready==expected,'direct-ready')
        else:c.check(c.parse(ready)==c.parse(expected),'consumer-ready')
        self.initial=self.observe();c.check(self.initial['running'] and self.initial['pid']>0,'actor-not-running');self.ready=True
        return self
    def stable(self):
        row=self.observe();c.check(row==self.initial,'actor-generation-changed');return row
    def expect_stopped(self,row):
        expected={k:v for k,v in self.initial.items() if k not in ('running','pid','exit_code','finished')}
        c.check(all(row.get(k)==v for k,v in expected.items()) and row['running'] is False and row['pid']==0 and
            row['exit_code']==0 and not row['finished'].startswith('0001-'),'actor-stop-generation')
    def event(self,source):c.check(c.parse(line(self.process))=={'event':'discovery','source':source},'discovery-event')
    def finish(self,cleanup):
        count=3 if cleanup=='unsubscribed' else 2
        result=c.parse(line(self.process))
        c.check(result=={'event':'finished','tokens':['pumpportal:create','pumpportal:migration']+(['pumpportal:create'] if count==3 else []),
            'creations':count-1,'gaps':1,'upstream_attempts':0,'fetch_attempts':0,'image_verified':not self.development,'development':self.development},'consumer-result')
        self.process.wait(timeout=3);row=self.observe();self.expect_stopped(row)
        self.stopped_snapshot=row;self.result=result
    def dispose(self):
        try:
            if self.attempted:
                if self.development:
                    self.cleanup_tail+=reap(self.process,terminate=True);self.removed=True
                else:
                    row=self.observe();ack=image.bounded(self.cli+['rm','--force',row['id']]).decode().strip()
                    c.check(ack==row['id'],'remove-ack');self.removed=True
        finally:
            if self.process:
                self.cleanup_tail+=reap(self.process,terminate=True)
    def receipt(self):return {'role':self.role,'id':self.cid,'token':self.token,'created':self.created,'ready':self.ready,
        'removed':self.removed,'client_reaped':self.process is None or self.process.returncode is not None,
        'initial':self.initial,'cleanup_tail':self.cleanup_tail.decode(),'observations':self.observations,'result':self.result,'development':self.development}

class ControlBackend:
    def __init__(self,actor):self.actor=actor
    def observe(self,cid):c.check(cid==self.actor.cid,'control-target');return self.actor.observe()
    def mutate(self,action,cid):
        c.check(cid==self.actor.cid,'control-target')
        if self.actor.development:
            if action=='disable_restart':self.actor.model['restart']='no'
            else:
                self.actor.finished=c.now();os.killpg(self.actor.process.pid,signal.SIGTERM);self.actor.process.wait(timeout=3)
            return cid
        return image.bounded(self.actor.cli+(['update','--restart=no',cid] if action=='disable_restart' else ['stop','-t','2',cid])).decode().strip()

class Backend:
    def __init__(self,root,registry,cli,cleanup,development=False,fault=None):
        self.root=root;self.registry=registry;self.cli=cli;self.cleanup=cleanup;self.development=development;self.fault=fault
        self.actors=[];self.direct=None;self.consumer=None;self.broker=None;self.read_fd=None;self.worker_identity=None
        self.endpoint=None;self.owner_id=None;self.peer=None;self.shared=False;self.stopped=False;self.retired=False
        self.fault_reached=False;self.restores=0;self.protocol=[];self.operations=[];self.max_owners=0;self.plan=None;self.broker_cleanup_tail=b''
    def actor(self,role):
        actor=Actor(self.cli,role,self.registry,self.development,self.read_fd);self.actors.append(actor);return actor.start()
    def prepare(self):
        self.direct=self.actor('direct');registry=self.root/'control';registry.mkdir(mode=0o700)
        with c.Control(registry,self.direct.initial,c.digest(c.raw(h.check_control.pins())),ControlBackend(self.direct)) as control:
            control.step('disable_restart');state=control.step('stop')
        self.direct_stopped=state['target'];self.original=self.direct
        return {'claim':c.parse(c.read(registry/'claim.json',16384)),'events':c.read(registry/'events.jsonl',65536).decode()}
    def bind_plan(self,claim):
        self.plan={'schema':1,'scope':'native-offline-handoff','source_sha256':pins(),'claim_sha256':c.digest(c.raw(claim)),
            'development':self.development,'cleanup':self.cleanup,'fault':self.fault,'provider_connection_opened':False}
        c.write_new(self.root/'plan.json',c.raw(self.plan))
    def check_plan(self):c.check(self.plan and c.read(self.root/'plan.json',65536)==c.raw(self.plan) and pins()==self.plan['source_sha256'],'plan-changed')
    def count(self):
        direct=bool(self.direct and self.direct.observe()['running']);n=int(direct)+int(self.shared)
        self.max_owners=max(self.max_owners,n);c.check(n<=1,'owner-overlap')
    def verify_peer(self):
        c.check(self.peer is not None,'peer-missing')
        if not self.development:
            st=(self.registry/'discovery.sock').lstat()
            c.check((st.st_dev,st.st_ino)==self.socket_identity and
                proc_identity(self.peer['pid'])==self.peer['process_identity'],'peer-generation-changed')
    def command(self,value):
        c.check(self.broker and self.broker.poll() is None and proc_identity(self.broker.pid)==self.worker_identity,'owner-generation')
        self.broker.stdin.write((value+'\n').encode());self.broker.stdin.flush()
        row=c.parse(line(self.broker,10));self.protocol.append(row);return row
    def perform(self,action,op,known):
        self.check_plan()
        state=h.inspect(self.registry);claim=c.parse(c.read(self.registry/'handoff-claim.json',65536))
        c.check(c.digest(c.raw(claim))==self.plan['claim_sha256'] and state['pending_action']==action and
            state['known']==known and op==h.op_id(claim,state['records']//2),'durable-intent-required')
        self.count()
        row={'scope':'isolated-handoff-adapter','operation_id':op,'provider_connection_closed':False,'billing_cutoff_verified':False}
        if action=='bind_endpoint':
            c.check(self.original.observe()==self.direct_stopped and self.broker is None,'direct-stop-changed')
            write_fd=None
            if self.development:self.read_fd,write_fd=os.pipe()
            try:
                self.broker=subprocess.Popen([sys.executable,'-E','-s','-B','-W','error::ResourceWarning',str(ROOT/'broker.py'),str(self.registry),str(os.getpid()),str(write_fd if write_fd is not None else -1),self.cleanup],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=image.host.ENV,pass_fds=() if write_fd is None else (write_fd,),start_new_session=True,bufsize=0)
            finally:
                if write_fd is not None:os.close(write_fd)
            self.worker_identity=proc_identity(self.broker.pid)
            response=c.parse(line(self.broker));c.check(response=={'event':'bound','development':self.development,'attempts':0},'owner-bind');self.protocol.append(response)
            if not self.development:
                st=(self.registry/'discovery.sock').lstat();c.check(stat.S_ISSOCK(st.st_mode) and st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==0o600,'socket-identity')
                self.socket_identity=(st.st_dev,st.st_ino)
            self.endpoint=c.digest(c.raw({'plan':c.digest(c.raw(self.plan)),'owner':self.worker_identity,'path':str(self.registry/'discovery.sock')}))
            self.owner_id=c.digest(c.raw({'worker':self.worker_identity,'plan':c.digest(c.raw(self.plan))}))
            row.update(endpoint_id=self.endpoint,endpoint_path=str(self.registry/'discovery.sock'))
        elif action=='start_consumer':
            if not self.development:
                st=(self.registry/'discovery.sock').lstat();c.check((st.st_dev,st.st_ino)==self.socket_identity,'socket-replaced')
            self.consumer=self.actor('consumer')
            if self.read_fd is not None:os.close(self.read_fd);self.read_fd=None
            peer=self.command('peer')
            if self.development:c.check(peer=={'event':'peer','development':True},'pipe-peer')
            else:
                c.check(set(peer)=={'event','pid','uid','gid','development'} and peer['event']=='peer' and peer['development'] is False and peer['uid']==peer['gid']==1000,'peer-credentials')
                proc=proc_identity(peer['pid']);c.check(proc['ppid']==self.consumer.initial['pid'],'peer-parent');peer['process_identity']=proc
            self.peer=peer;self.consumer.stable()
            row.update(endpoint_id=self.endpoint,consumer_id=self.consumer.cid,image=c.IMAGE,ready=True)
        elif action=='start_owner':
            c.check(self.original.observe()==self.direct_stopped and self.peer is not None,'start-precondition');self.consumer.stable();self.verify_peer()
            c.check(self.command('start')=={'event':'started','synthetic_attempts':1},'owner-start');self.shared=True
            self.consumer.event('pumpportal:create');self.consumer.event('pumpportal:migration')
            row.update(endpoint_id=self.endpoint,consumer_id=self.consumer.cid,owner_id=self.owner_id,synthetic_attempts=1)
        elif action=='retire_research':
            self.consumer.stable();self.verify_peer();r=self.command('retire')
            c.check(r=={'event':'retired','cleanup':self.cleanup,'admission_closed':True,'discovery_continues':self.cleanup=='unsubscribed'},'research-retirement')
            if self.cleanup=='unsubscribed':self.consumer.event('pumpportal:create');self.consumer.stable()
            else:self.consumer.finish(self.cleanup)
            self.retired=True;row.update(owner_id=self.owner_id,admission_closed=True,cleanup=self.cleanup,discovery_continues=self.cleanup=='unsubscribed')
        elif action=='stop_shared':
            c.check(self.retired,'retirement-required');c.check(self.command('stop')=={'event':'stopped','closed':True},'owner-stop')
            reap(self.broker)
            if self.consumer.result is None:self.consumer.finish(self.cleanup)
            reap(self.consumer.process);self.shared=False;self.stopped=True
            row.update(owner_id=self.owner_id,consumer_id=self.consumer.cid,owner_reaped=True,consumer_reaped=True,local_connection_closed=True)
        elif action=='restore_direct':
            c.check(self.stopped and self.broker.returncode==0 and self.consumer.observe()==self.consumer.stopped_snapshot and self.original.observe()==self.direct_stopped,'restore-precondition')
            self.direct=self.actor('direct');c.check(h.config_identity(self.direct.initial)==h.config_identity(self.original.initial),'restored-config')
            self.restores+=1;row.update(previous_direct_id=self.original.cid,new_direct_id=self.direct.cid,image=c.IMAGE,
                config_sha256=h.config_identity(self.direct.initial),restart_policy=self.direct.initial['restart'],ready=True)
        else:raise ValueError('unknown-action')
        self.count();self.check_plan();self.operations.append({'action':action,'operation_id':op,'receipt':row,'observed_utc':c.now()})
        if action==self.fault:self.fault_reached=True;raise ValueError('deliberate-lost-response')
        return row
    def close(self):
        failed=False
        try:self.broker_cleanup_tail=reap(self.broker,terminate=True) or b''
        except BaseException:failed=True
        if self.read_fd is not None:os.close(self.read_fd);self.read_fd=None
        for actor in reversed(self.actors):
            try:actor.dispose()
            except BaseException:failed=True
        c.check(not failed,'owned-cleanup-unconfirmed')
    def receipt(self):return {'actors':[a.receipt() for a in self.actors],'protocol':self.protocol,'peer':self.peer,
        'broker_cleanup_tail':self.broker_cleanup_tail.decode(),'worker_identity':self.worker_identity,'owner_id':self.owner_id,'endpoint_id':self.endpoint,'operations':self.operations,
        'restores':self.restores,'max_simultaneous_synthetic_owners':self.max_owners,'fault_reached':self.fault_reached,
        'broker_reaped':self.broker is None or self.broker.returncode is not None,'development':self.development,
        'provider_connection_opened':False,'production_modified':False}
