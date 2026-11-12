"""Offline lifecycle adapter: real broker/scanner, disposable Docker or explicit pipe development mode."""
import asyncio
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
import uuid

import integrated_common as common
from capture import CaptureError, canonical, digest, exclusive_file, strict_json
from handoff import read_private
from supervisor import kill_group
import credential
from container_boundary import Consumer, host

ROOT=Path(__file__).resolve().parent


def line(process, seconds=4):
    deadline=time.monotonic()+seconds; data=bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout,selectors.EVENT_READ)
        while len(data)<4096:
            remaining=deadline-time.monotonic()
            if remaining<=0 or not selector.select(remaining): raise CaptureError('integration-read-deadline')
            byte=os.read(process.stdout.fileno(),1)
            if not byte: raise CaptureError('integration-child-eof')
            data.extend(byte)
            if byte==b'\n': return bytes(data)
    raise CaptureError('integration-output-bound')


def reap(process):
    if process is None: return
    try:
        if process.poll() is None: kill_group(process,signal.SIGTERM)
        try: process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            kill_group(process,signal.SIGKILL);process.wait(timeout=1)
    finally:
        for stream in (process.stdin,process.stdout):
            if stream and not stream.closed: stream.close()


class Actor:
    def __init__(self,directory,role,ipc,*,pipe_only=False,read_fd=None):
        if role not in ('direct','consumer'): raise CaptureError('integration-role')
        self.identity=uuid.uuid4().hex; self.role=role; self.ipc=ipc
        self.pipe_only=pipe_only; self.read_fd=read_fd; self.process=None
        self.policy='no'; self.transitions=[]; self.result=None; self.stopped=False
        self.container=None
        if not pipe_only:
            self.container=Consumer(directory)
            if role=='direct':
                target=self.container.code/'r1-service/direct_fixture.mjs'
                target.parent.mkdir(mode=0o700)
                exclusive_file(target,(ROOT/'direct_fixture.mjs').read_bytes())
                self.container.code_pins['r1-service/direct_fixture.mjs']=digest(target.read_bytes())

    def start(self):
        if self.process is not None: raise CaptureError('integration-actor-reuse')
        script='r1-service/direct_fixture.mjs' if self.role=='direct' else 'r1-data/shared_scanner_fixture.mjs'
        if self.pipe_only:
            node=shutil.which('node')
            if node is None: raise CaptureError('integration-node-required')
            command=[node,str(common.REPO/script)]+([] if self.role=='direct' else ['pipe'])
            self.process=subprocess.Popen(command,env=common.ENVIRONMENT,
                stdin=self.read_fd if self.role=='consumer' else subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,close_fds=True,start_new_session=True,bufsize=0)
        else:
            c=self.container; host.trusted_local_docker()
            args=c.create_args(self.ipc)
            if self.role=='direct': args=args[:-3]+['/r1-code/'+script]
            c.attempted=True
            cid=c.command(*args).decode('ascii').strip()
            import re
            if not re.fullmatch(r'[0-9a-f]{64}',cid): raise CaptureError('integration-create-unconfirmed')
            c.cid,c.created=cid,True
            row=c.identify(cid);c.isolation(row)
            if row['running'] is not False: raise CaptureError('integration-start-state')
            c.inspected_before_start=True
            self.process=subprocess.Popen(c.cli('start','--attach','--interactive',cid),env=host.ENV,
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                close_fds=True,start_new_session=True,bufsize=0)
        if line(self.process)!=b'ready\n': raise CaptureError('integration-node-start')
        if self.container and self.container.identify(self.container.cid)['running'] is not True:
            raise CaptureError('integration-container-not-running')

    def set_restart(self,policy):
        if self.role!='direct' or policy not in ('no','unless-stopped') or self.process.poll() is not None:
            raise CaptureError('integration-restart-policy')
        before=self.policy
        if self.container:
            c=self.container; row=c.identify(c.cid)
            if row['restart']!=before or row['running'] is not True:
                raise CaptureError('integration-policy-before')
            if c.command('update','--restart='+policy,c.cid).decode('ascii').strip()!=c.cid:
                raise CaptureError('integration-policy-ack')
            row=c.identify(c.cid)
            if row['restart']!=policy or row['running'] is not True:
                raise CaptureError('integration-policy-after')
        self.policy=policy;self.transitions.append({'before':before,'after':policy,'simulated':self.pipe_only})

    def stop_direct(self):
        if self.role!='direct' or self.policy!='no' or self.stopped:
            raise CaptureError('integration-direct-stop-order')
        if self.container:
            c=self.container;row=c.identify(c.cid)
            if row['restart']!='no' or row['running'] is not True:
                raise CaptureError('integration-direct-state')
            if c.command('stop','-t','1',c.cid).decode('ascii').strip()!=c.cid:
                raise CaptureError('integration-stop-ack')
        else: kill_group(self.process,signal.SIGTERM)
        self.result=strict_json(line(self.process))
        self.process.wait(timeout=2)
        expected={'attempts':1,'closed':True,'subscriptions':['subscribeNewToken','subscribeMigration'],
                  'provider_connections_opened':0}
        if self.process.returncode!=0 or self.result!=expected:
            raise CaptureError('integration-direct-closure')
        if self.container:
            row=self.container.identify(self.container.cid)
            if row['running'] is not False or row['exit_code']!=0:
                raise CaptureError('integration-direct-reaping')
        self.stopped=True

    def finish_consumer(self,scenario):
        if self.role!='consumer': raise CaptureError('integration-consumer-role')
        result=strict_json(line(self.process))
        self.process.wait(timeout=2)
        count=3 if scenario=='normal' else 2
        if (self.process.returncode!=0 or result!={'tokens':count,'creations':count-1,'discovery_gaps':1,
                'sources':['pumpportal:create','pumpportal:migration']+(['pumpportal:create'] if count==3 else []),'upstream_connections_opened':0}):
            raise CaptureError('integration-consumer-result')
        if self.container:
            row=self.container.identify(self.container.cid)
            if row['running'] is not False or row['exit_code']!=0:
                raise CaptureError('integration-consumer-reaping')
        self.result=result; self.stopped=True

    def close(self):
        try:
            if self.container: asyncio.run(self.container.cleanup())
        finally: reap(self.process)

    def receipt(self):
        return {'identity':self.identity,'role':self.role,'result':self.result,
                'process_reaped':self.process is None or self.process.returncode is not None,
                'restart_transitions':self.transitions,'container':self.container.receipt() if self.container else None}


class Backend:
    def __init__(self,directory,ipc,scenario,*,pipe_only=False):
        if scenario not in ('normal','cleanup-failure'): raise CaptureError('integration-scenario')
        self.directory=directory;self.ipc=ipc;self.scenario=scenario;self.pipe_only=pipe_only
        self.actors=[];self.direct=self.consumer=None;self.broker=None;self.read_fd=None
        self.previous=None;self.endpoint=uuid.uuid4().hex;self.owner_id=uuid.uuid4().hex
        self.peer=False;self.active=False;self.shared_stopped=False;self.research=None;self.worker=None
        self.actions=[];self.max_owners=0;self.restore_calls=0;self.protocol=[]

    def actor(self,role):
        directory=self.directory/('actor-'+str(len(self.actors)));directory.mkdir(mode=0o700)
        actor=Actor(directory,role,self.ipc,pipe_only=self.pipe_only,read_fd=self.read_fd)
        self.actors.append(actor);actor.start();return actor

    def prepare(self):
        self.direct=self.actor('direct');self.previous=self.direct.identity
        self.direct.set_restart('unless-stopped');self.count()

    def count(self):
        n=int(self.direct is not None and not self.direct.stopped)+int(self.active)
        self.max_owners=max(self.max_owners,n)
        if n>1: raise CaptureError('integration-owner-overlap')

    def bind(self):
        if not self.direct.stopped or self.broker is not None: raise CaptureError('integration-bind-order')
        directory=self.directory/'broker';directory.mkdir(mode=0o700)
        manifest={'schema_version':1,'mode':'offline-service-integration','parent_pid':os.getpid(),
                  'scenario':self.scenario,'transport':'pipe' if self.pipe_only else 'unix',
                  'source_sha256':common.pins(),'resources':common.RESOURCES}
        exclusive_file(directory/'manifest.json',(canonical(manifest)+'\n').encode())
        fd=write_fd=None
        try:
            fd=credential.sealed(('R1-SYNTHETIC-'+uuid.uuid4().hex).encode())
            if self.pipe_only: self.read_fd,write_fd=os.pipe()
            command=[sys.executable,'-E','-s','-B','-W','error::ResourceWarning',str(ROOT/'broker_fixture.py'),
                     str(directory),str(self.ipc),str(os.getpid()),str(fd),self.scenario,str(write_fd if write_fd is not None else -1)]
            self.broker=subprocess.Popen(command,env=common.ENVIRONMENT,stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,close_fds=True,
                pass_fds=(fd,) if write_fd is None else (fd,write_fd),start_new_session=True,bufsize=0)
        finally:
            if fd is not None: os.close(fd)
            if write_fd is not None: os.close(write_fd)
        row=strict_json(line(self.broker))
        if row!={'event':'bound','upstream_attempts':0,'credential_descriptor_closed':True}:
            raise CaptureError('integration-broker-bound')
        if not self.pipe_only:
            st=(self.ipc/'discovery.sock').lstat()
            if not stat.S_ISSOCK(st.st_mode) or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o600:
                raise CaptureError('integration-endpoint-identity')
        self.protocol.append(row)

    def command(self,command):
        if self.broker.poll() is not None: raise CaptureError('integration-broker-dead')
        self.broker.stdin.write((command+'\n').encode());self.broker.stdin.flush()
        row=strict_json(line(self.broker,9 if command=='retire' else 4));self.protocol.append(row);return row

    def perform(self,action,op,known):
        self.count();self.actions.append(action);row={'scope':'synthetic-process-lifecycle','operation_id':op}
        if action=='disable_direct_restart':
            self.direct.set_restart('no');row.update(direct_id=self.direct.identity,restart_disabled=True)
        elif action=='stop_direct':
            self.direct.stop_direct();row.update(direct_id=self.direct.identity,direct_reaped=True,connection_closed=True)
        elif action=='bind_endpoint':
            self.bind();row.update(endpoint_id=self.endpoint,endpoint_ready=True)
        elif action=='start_consumer':
            self.consumer=self.actor('consumer')
            if self.read_fd is not None: os.close(self.read_fd);self.read_fd=None
            if self.command('peer')!={'event':'peer','peer_uid_verified':not self.pipe_only,'upstream_attempts':0}:
                raise CaptureError('integration-peer')
            self.peer=True;row.update(endpoint_id=self.endpoint,consumer_id=self.consumer.identity,consumer_ready=True)
        elif action=='start_owner':
            if not self.peer or not self.direct.stopped or self.consumer.process.poll() is not None:
                raise CaptureError('integration-owner-order')
            if self.command('start')!={'event':'started','upstream_attempts':1}: raise CaptureError('integration-owner-start')
            self.active=True;row.update(consumer_id=self.consumer.identity,owner_id=self.owner_id,upstream_attempts=1)
        elif action=='retire_research':
            result=self.command('retire');cleanup='unsubscribed' if self.scenario=='normal' else 'upstream-aborted'
            if result!={'event':'retired','cleanup':cleanup,'admission_closed':True}: raise CaptureError('integration-retirement')
            self.research=result;row.update(owner_id=self.owner_id,admission_closed=True,cleanup=cleanup)
        elif action=='stop_shared':
            if self.command('stop')!={'event':'closed','connection_closed':True}: raise CaptureError('integration-shared-close')
            self.broker.wait(timeout=5)
            if self.broker.returncode!=0: raise CaptureError('integration-broker-exit')
            self.consumer.finish_consumer(self.scenario)
            self.worker=strict_json(read_private(self.directory/'broker/worker-result.json',65536))
            manifest=read_private(self.directory/'broker/manifest.json',65536)
            if self.worker['manifest_sha256']!=digest(manifest) or not self.worker['shared']['owner']['closed']:
                raise CaptureError('integration-worker-binding')
            self.active=False;self.shared_stopped=True
            row.update(owner_id=self.owner_id,consumer_id=self.consumer.identity,owner_reaped=True,
                       consumer_reaped=True,connection_closed=True)
        elif action=='restore_direct':
            if (not self.shared_stopped or self.broker.poll() is None or self.consumer.process.poll() is None):
                raise CaptureError('integration-rollback-order')
            self.direct=self.actor('direct');self.direct.set_restart('unless-stopped');self.restore_calls+=1
            row.update(previous_direct_id=self.previous,new_direct_id=self.direct.identity,restart_policy_restored=True)
        else: raise CaptureError('integration-action')
        self.count();return row

    def close(self):
        failed=False
        # Abort broker before any cleanup; cleanup never restores direct service.
        try: reap(self.broker)
        except Exception: failed=True
        if self.read_fd is not None: os.close(self.read_fd);self.read_fd=None
        for actor in reversed(self.actors):
            try:
                if actor.role=='direct' and actor.process and actor.process.poll() is None:
                    actor.set_restart('no');actor.stop_direct()
            except Exception: failed=True
            finally:
                try: actor.close()
                except Exception: failed=True
        if failed: raise CaptureError('integration-cleanup-unconfirmed')

    def receipt(self):
        return {'actions':self.actions,'max_simultaneous_synthetic_owners':self.max_owners,
                'direct_restore_calls':self.restore_calls,'broker_reaped':self.broker is not None and self.broker.returncode is not None,
                'protocol':self.protocol,'actors':[a.receipt() for a in self.actors],
                'worker':self.worker,'restart_policy_simulated':self.pipe_only,'transport':'pipe' if self.pipe_only else 'unix',
                'provider_connections_opened':0,'production_modified':False}
