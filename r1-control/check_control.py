"""Consolidated exact-target control check using only owned inert containers."""
import argparse
import importlib.util
import io
import os
import re
from pathlib import Path
import sys
import time
import selectors
import subprocess
import signal
import unittest
import uuid
import zipfile
import control as c
ROOT=Path(__file__).resolve().parent;REPO=ROOT.parent
sys.path.insert(0,str(REPO/'r1-image'))
import check_image as image

class Docker:
    def __init__(self,cli,fault=None):self.cli=cli;self.fault=fault;self.reached=False;self.calls=[]
    def observe(self,cid):return c.parse(image.bounded(self.cli+['inspect','--type','container','--format',c.FORMAT,cid]))
    def mutate(self,action,cid):
        self.calls.append(action)
        args=['update','--restart=no',cid] if action=='disable_restart' else ['stop','-t','2',cid]
        ack=image.bounded(self.cli+args).decode().strip()
        if self.fault==action:self.reached=True;raise ValueError('deliberate-lost-response')
        return ack

def pins():
    paths=[*ROOT.glob('*.py'),ROOT/'README.md',REPO/'scripts/r1-control-kali.sh',
        REPO/'r1-image/check_image.py',REPO/'r1-image/candidate.py',REPO/'r1-host-review/check.py']
    return {str(p.relative_to(REPO)):c.digest(p.read_bytes()) for p in paths}

def case(output,cli,name,report):
    token=uuid.uuid4().hex;container='radar-r1-control-'+token;cid=None;attempted=False;process=None
    backend=Docker(cli,{'lost-update':'disable_restart','lost-stop':'stop'}.get(name))
    registry=output/name;registry.mkdir(mode=0o700)
    receipt={'case':name,'started_utc':c.now(),'token':token,'removed':False,'fault_reached':False}
    report['cases'].append(receipt)
    try:
        args=['create','--name',container,'--label',c.LABEL+'='+token,'--pull=never','--network=none',
            '--restart=unless-stopped','--read-only','--init','--user=1000:1000','--cap-drop=ALL',
            '--security-opt=no-new-privileges:true','--memory=128m','--memory-swap=128m',
            '--cpus=1','--pids-limit=32','--log-driver=none','--no-healthcheck',c.IMAGE,*c.CMD]
        attempted=True;cid=image.bounded(cli+args).decode().strip()
        c.check(re.fullmatch('[a-f0-9]{64}',cid),'create-identity')
        row=backend.observe(cid);c.isolated(row,token);c.check(row['id']==cid and not row['running'],'create')
        process=subprocess.Popen(cli+['start','--attach',cid],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,env=image.host.ENV,start_new_session=True)
        ready=bytearray();deadline=time.monotonic()+5
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout,selectors.EVENT_READ)
            while not ready.endswith(b'\n'):
                left=deadline-time.monotonic();c.check(left>0 and selector.select(left),'ready-timeout')
                b=os.read(process.stdout.fileno(),1);c.check(b and len(ready)<128,'ready-output');ready.extend(b)
        c.check(bytes(ready)==b'r1-control-ready\n','actor-not-ready');receipt['actor_ready']=True
        target=backend.observe(cid);c.isolated(target,token)
        c.check(target['running'] and target['pid']>0,'not-running')
        # The image-bound inert actor verifies its manifest before remaining alive.
        # Later exact-identity observations must still find the same process/start.
        with c.Control(registry,target,c.digest(c.raw(pins())),backend) as control:
            try:
                control.step('disable_restart');control.step('stop')
            except ValueError:
                c.check(name!='normal' and backend.reached,'unexpected-failure')
        before_bytes={p.name:p.read_bytes() for p in registry.iterdir()}
        recovery=c.inspect(registry)
        c.check(before_bytes=={p.name:p.read_bytes() for p in registry.iterdir()},'reader-write')
        if name=='normal':c.check(recovery['local_stop_verified'] and not recovery['reconciliation_required'],'normal')
        else:c.check(recovery['pending_action']==backend.fault and recovery['reconciliation_required'] and not recovery['local_stop_verified'],'uncertainty-lost')
        c.check(not recovery['shared_start_authorized'] and not recovery['provider_connection_closed'],'authority')
        receipt.update(target=target,recovery=recovery,commands=backend.calls,fault_reached=backend.reached,finished_utc=c.now())
    finally:
        try:
          if attempted:
            row=backend.observe(cid or container);c.isolated(row,token)
            c.check(cid is None or row['id']==cid,'cleanup-identity')
            receipt['id']=row['id']
            # Cleanup is fixture disposal, never a successful control confirmation.
            ack=image.bounded(cli+['rm','--force',row['id']]).decode().strip()
            c.check(ack==row['id'],'cleanup-ack');receipt['removed']=True
        finally:
            if process:
                try:
                    process.wait(timeout=3)
                    c.check(process.stdout.read(4097)==b'','actor-extra-output')
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=2)
                finally:process.stdout.close()
                receipt['client_reaped']=True

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-directory',required=True)
    args=parser.parse_args();os.umask(0o077);out=Path(args.output_directory).absolute()
    c.check(not out.exists() and all(not p.is_symlink() for p in [out,*out.parents]),'output')
    out.mkdir(mode=0o700);log=io.StringIO()
    report={'schema':1,'status':'service-control-failed-live-blocked','started_utc':c.now(),
        'production_modified':False,'provider_connection_opened':False,'activation_authorized':False,'cases':[]}
    stage='source'
    try:
        report['source_sha256']=pins();c.check(not image.c.git('status','--porcelain').strip(),'dirty-source')
        stage='tests';suite=unittest.defaultTestLoader.discover(str(ROOT),pattern='test_*.py')
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        report['tests']={'run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'skipped':len(result.skipped)}
        c.check(result.wasSuccessful() and result.testsRun>0 and not result.skipped and not image.DIAGNOSTIC.search(log.getvalue()),'tests')
        stage='docker';image.host.trusted_local_docker()
        c.check(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000,'uid')
        config=out/'empty-docker-config';config.mkdir(mode=0o700)
        cli=[image.host.DOCKER,'--config',str(config),'--host','unix://'+image.host.SOCKET]
        c.check(image.bounded(cli+['image','inspect','--format','{{.Id}}',c.IMAGE]).decode().strip()==c.IMAGE,'image-unavailable')
        for name in ('normal','lost-update','lost-stop'):stage=name;case(out,cli,name,report)
        stage='final';c.check(pins()==report['source_sha256'] and not image.c.git('status','--porcelain').strip(),'source-change')
        report['status']='service-control-offline-passed-live-blocked'
    except BaseException as e:
        report.update(failure_stage=stage,failure_type=type(e).__name__)
    finally:
        report['finished_utc']=c.now();(out/'report.json').write_bytes(c.raw(report));(out/'validation.log').write_text(log.getvalue())
        with zipfile.ZipFile(out/'acceptance.zip','x',compression=zipfile.ZIP_STORED) as z:
            for name in ('report.json','validation.log'):z.write(out/name,name)
            for case_name in ('normal','lost-update','lost-stop'):
                for name in ('claim.json','events.jsonl'):
                    p=out/case_name/name
                    if p.is_file():z.write(p,case_name+'/'+name)
    print(report['status']);print(out/'acceptance.zip')
    return 0 if report['status']=='service-control-offline-passed-live-blocked' else 1
if __name__=='__main__':sys.exit(main())
