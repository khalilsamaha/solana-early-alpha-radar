"""Native process lifecycle fixture. Restart policies and endpoint are simulated."""
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import uuid

from capture import CaptureError
from supervisor import ENVIRONMENT, kill_group

ROOT=Path(__file__).resolve().parent


class Actor:
    def __init__(self,role):
        self.identity=uuid.uuid4().hex
        self.process=subprocess.Popen([sys.executable,'-E','-s','-B','-W','error::ResourceWarning',
            str(ROOT/'process_fixture.py'),role,str(os.getpid())],env=ENVIRONMENT,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            close_fds=True,start_new_session=True,bufsize=0)
        try:
            if self.read()!=b'ready\n':raise CaptureError('service-fixture-start')
        except BaseException:self.close();raise

    def read(self):
        with selectors.DefaultSelector() as sel:
            sel.register(self.process.stdout,selectors.EVENT_READ)
            if not sel.select(3):raise CaptureError('service-fixture-timeout')
            raw=os.read(self.process.stdout.fileno(),64)
        return raw

    def command(self,value):
        if self.process.poll() is not None:raise CaptureError('service-fixture-ended')
        self.process.stdin.write(value);self.process.stdin.flush()

    def close(self):
        p=self.process
        if p.poll() is None:kill_group(p,signal.SIGTERM)
        try:p.wait(timeout=0.25)
        except subprocess.TimeoutExpired:kill_group(p,signal.SIGKILL);p.wait(timeout=1)
        finally:
            for stream in (p.stdin,p.stdout):
                if stream and not stream.closed:stream.close()
        if p.returncode is None:raise CaptureError('service-fixture-unreaped')


class Backend:
    def __init__(self,cleanup_failure=False):
        self.direct=Actor('direct');self.consumer=self.owner=None
        self.previous=self.direct.identity;self.endpoint=None;self.restart_disabled=False
        self.cleanup_failure=cleanup_failure;self.actions=[];self.actors=[self.direct]
        self.max_owner_processes=1;self.restore_calls=0

    def count(self):
        active=sum(a.process.poll() is None for a in (self.direct,self.owner) if a)
        self.max_owner_processes=max(self.max_owner_processes,active)
        if active>1:raise CaptureError('service-fixture-overlap')

    def spawn(self,role):
        actor=Actor(role);self.actors.append(actor);return actor

    def perform(self,action,op,known):
        self.actions.append(action);self.count()
        row={'scope':'synthetic-process-lifecycle','operation_id':op}
        if action=='disable_direct_restart':
            self.restart_disabled=True
            row.update(direct_id=self.direct.identity,restart_disabled=True)
        elif action=='stop_direct':
            if not self.restart_disabled:raise CaptureError('service-fixture-order')
            self.direct.close();row.update(direct_id=self.direct.identity,direct_reaped=True,connection_closed=True)
        elif action=='bind_endpoint':
            if self.direct.process.poll() is None:raise CaptureError('service-fixture-order')
            self.endpoint=uuid.uuid4().hex;row.update(endpoint_id=self.endpoint,endpoint_ready=True)
        elif action=='start_consumer':
            if not self.endpoint:raise CaptureError('service-fixture-order')
            self.consumer=self.spawn('consumer');row.update(endpoint_id=self.endpoint,consumer_id=self.consumer.identity,consumer_ready=True)
        elif action=='start_owner':
            if self.direct.process.poll() is None or self.consumer.process.poll() is not None:
                raise CaptureError('service-fixture-order')
            self.owner=self.spawn('owner');row.update(consumer_id=self.consumer.identity,owner_id=self.owner.identity,upstream_attempts=1)
        elif action=='retire_research':
            self.owner.command(b'abort\n' if self.cleanup_failure else b'retire\n')
            if self.cleanup_failure:self.owner.process.wait(timeout=2)
            elif self.owner.read()!=b'retired\n':raise CaptureError('service-fixture-retirement')
            row.update(owner_id=self.owner.identity,admission_closed=True,
                       cleanup='upstream-aborted' if self.cleanup_failure else 'unsubscribed')
        elif action=='stop_shared':
            self.owner.close();self.consumer.close()
            row.update(owner_id=self.owner.identity,consumer_id=self.consumer.identity,owner_reaped=True,
                       consumer_reaped=True,connection_closed=True)
        elif action=='restore_direct':
            if self.owner.process.poll() is None or self.consumer.process.poll() is None:
                raise CaptureError('service-fixture-rollback-overlap')
            self.direct=self.spawn('direct');self.restore_calls+=1;self.restart_disabled=False
            row.update(previous_direct_id=self.previous,new_direct_id=self.direct.identity,restart_policy_restored=True)
        else:raise CaptureError('service-fixture-action')
        self.count();return row

    def close(self):
        failed=False
        for actor in reversed(self.actors):
            try:actor.close()
            except Exception:failed=True
        if failed:raise CaptureError('service-fixture-cleanup-unconfirmed')

    def receipt(self):
        return {'actors_started':len(self.actors),'all_fixture_processes_reaped':all(a.process.returncode is not None for a in self.actors),
                'max_simultaneous_owner_processes':self.max_owner_processes,'direct_restore_calls':self.restore_calls,
                'actions':list(self.actions),'restart_policy_simulated':True,'endpoint_simulated':True,
                'provider_connections_opened':0,'production_modified':False}
