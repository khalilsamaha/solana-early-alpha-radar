"""Owned inert original for the combined native check; no external selector."""
import os
import selectors
import subprocess
import time
import uuid
import check_retained as retained
import admission
c=retained.c


class Original:
    def __init__(self,cli,directory):
        self.cli=list(cli);self.token=uuid.uuid4().hex
        self.directory=directory
        self.name='radar-r1-combined-'+self.token
        self.cid=None;self.process=None;self.attempted=False
        self.receipt={'token':self.token,'name':self.name,'id':None,'create_attempted':False,
                      'ready':False,'removed':False,'client_reaped':False}

    def start(self):
        args=['create','--name',self.name,'--label',c.LABEL+'='+self.token,'--pull=never','--network=none',
            '--restart=unless-stopped','--read-only','--init','--user=1000:1000','--cap-drop=ALL',
            '--security-opt=no-new-privileges:true','--memory=128m','--memory-swap=128m',
            '--cpus=1','--pids-limit=32','--log-driver=none','--no-healthcheck',
            '--stop-timeout=2','--stop-signal=SIGTERM',c.IMAGE,*c.CMD]
        c.write_new(self.directory/'fixture-intent.json',c.raw({'schema':1,'kind':'owned-inert-original-create',
            'name':self.name,'token':self.token,'image':c.IMAGE,'created_utc':c.now(),
            'network':'none','production_modified':False,'activation_authorized':False}))
        self.attempted=True;self.receipt['create_attempted']=True
        value=retained.run(self.cli+args).decode().strip()
        c.check(retained.re.fullmatch('[a-f0-9]{64}',value),'create-identity')
        self.cid=value;self.receipt['id']=value
        row=retained.fixture(self.cli,self.cid,self.token)
        c.check(row['id']==self.cid and not row['running'],'create-state')
        self.process=subprocess.Popen(self.cli+['start','--attach',self.cid],stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=retained.image.host.ENV,start_new_session=True)
        ready=bytearray();deadline=time.monotonic()+5
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout,selectors.EVENT_READ)
            while not ready.endswith(b'\n'):
                left=deadline-time.monotonic()
                c.check(left>0 and selector.select(left),'ready-timeout')
                value=os.read(self.process.stdout.fileno(),1)
                c.check(value and len(ready)<128,'ready-output');ready.extend(value)
        c.check(bytes(ready)==b'r1-control-ready\n','actor-ready')
        backend=admission.IsolatedBoundDocker(self.cli,self.cid,self.token,retained.run)
        self.receipt['ready']=True
        return backend

    def close(self):
        try:
            if self.attempted:
                row=retained.fixture(self.cli,self.cid or self.name,self.token)
                c.check(self.cid is None or row['id']==self.cid,'cleanup-identity')
                self.receipt['id']=row['id'];self.receipt['last_observation']=row
                ack=retained.run(self.cli+['rm','--force',row['id']]).decode().strip()
                c.check(ack==row['id'],'cleanup-ack');self.receipt['removed']=True
        except BaseException as exc:
            self.receipt['cleanup_failure']=retained.diagnostic(exc)
            raise
        finally:
            if self.process is not None:
                try:
                    try:self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(self.process.pid,retained.signal.SIGKILL);self.process.wait(timeout=2)
                    self.receipt['client_reaped']=True
                finally:self.process.stdout.close()
