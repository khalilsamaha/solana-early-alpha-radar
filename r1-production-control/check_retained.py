"""Isolated retained-container check. No production selector or provider access."""
import argparse
import io
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time
import unittest
import uuid
import zipfile
import production_control as p
import command_io
c = p.c
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(p.ROOT/'r1-image'))
import check_image as image
# Never emit arbitrary exception text, raw diagnostics or frame locals.
SAFE_CODES = {'adapter-target','adapter-action','command-ack','target-drift','restart-unconfirmed',
              'stop-unconfirmed','start-unconfirmed','projection-bound','projection-fields',
              'engine-state-unavailable','configuration-fields','restart-policy','stop-signal',
              'stop-timeout-required','target-fields','target-identity','target-name','target-policy',
              'target-state','target-time','journal-changed','clock-regressed','short-write',
              'command-timeout','command-output-limit','command-diagnostic-limit','command-failed',
              'deliberate-lost-response','cleanup-identity','cleanup-ack','fixture-memory',
              'ready-timeout','ready-output','actor-ready','create-identity','create-state','target',
              'drift-ack','source-change','dirty-source','tests','uid','image-unavailable'}


def diagnostic(exc):
    if isinstance(exc, ValueError) and len(exc.args)==1 and type(exc.args[0]) is str and exc.args[0] in SAFE_CODES:
        return exc.args[0]
    for cls, code in ((PermissionError,'permission-denied'),(FileNotFoundError,'path-unavailable'),
                      (KeyError,'required-field-unavailable'),(UnicodeError,'encoding-invalid')):
        if isinstance(exc,cls):return code
    return 'operation-unavailable'


def run(command, **kwargs):
    return command_io.bounded(command,env=image.host.ENV,**kwargs)


CASES = ('normal', 'lost-stop', 'lost-start', 'configuration-drift')


def pins():
    names = ['r1-control/control.py', 'r1-control/test_control.py',
             'r1-image/check_image.py', 'r1-image/candidate.py', 'r1-host-review/check.py',
             'scripts/r1-retained-control-kali.sh']
    names += [str(x.relative_to(p.ROOT)) for x in ROOT.iterdir() if x.is_file() and x.suffix in ('.py','.md')]
    return {n:c.digest((p.ROOT/n).read_bytes()) for n in sorted(names)}


def fixture(cli, selector, token, *, changed=False):
    row = c.parse(run(cli+['inspect','--type','container','--format',c.FORMAT,selector],seconds=4))
    # Only this known resource change is allowed for disposal in the drift case.
    c.check(row['memory'] == (96 if changed else 128)*1024**2, 'fixture-memory')
    c.isolated({**row, 'memory':128*1024**2}, token)
    return row


class Backend(p.Docker):
    def __init__(self, cli, target, lost):
        super().__init__(cli,target,run)
        self.lost=lost;self.reached=False;self.calls=[];self.phase='not-started'
        self.command_events=[];self.last_observation=None
        self.bounded=lambda args,**kw:run(args,events=self.command_events,**kw)
    def observe(self,cid):
        self.phase='inspect'
        self.last_observation=super().observe(cid)
        return self.last_observation
    def mutate(self, action, cid):
        self.calls.append(action);self.phase='dispatch-'+action
        result=super().mutate(action,cid)
        if action == self.lost:
            self.reached=True
            raise ValueError('deliberate-lost-response')
        return result


def case(out, cli, name, report):
    token=uuid.uuid4().hex; cname='radar-r1-retained-'+token
    registry=out/name;registry.mkdir(mode=0o700)
    receipt={'case':name,'token':token,'started_utc':c.now(),'removed':False,'client_reaped':False}
    report['cases'].append(receipt)
    cid=None;attempted=False;process=None;changed=False;backend=None
    phase='create'
    try:
        args=['create','--name',cname,'--label',c.LABEL+'='+token,'--pull=never','--network=none',
              '--restart=unless-stopped','--read-only','--init','--user=1000:1000','--cap-drop=ALL',
              '--security-opt=no-new-privileges:true','--memory=128m','--memory-swap=128m',
              '--cpus=1','--pids-limit=32','--log-driver=none','--no-healthcheck',
              '--stop-timeout=2','--stop-signal=SIGTERM',
              '--env','R1_CONTROL_TEST_VALUE=nonsecret-fixture',c.IMAGE,*c.CMD]
        attempted=True;cid=run(cli+args).decode().strip()
        c.check(re.fullmatch('[a-f0-9]{64}',cid),'create-identity')
        row=fixture(cli,cid,token);c.check(row['id']==cid and not row['running'],'create-state')
        phase='attach-ready'
        process=subprocess.Popen(cli+['start','--attach',cid],stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                 env=image.host.ENV,start_new_session=True)
        ready=bytearray();deadline=time.monotonic()+5
        with selectors.DefaultSelector() as sel:
            sel.register(process.stdout,selectors.EVENT_READ)
            while not ready.endswith(b'\n'):
                left=deadline-time.monotonic();c.check(left>0 and sel.select(left),'ready-timeout')
                value=os.read(process.stdout.fileno(),1);c.check(value and len(ready)<128,'ready-output');ready.extend(value)
        c.check(bytes(ready)==b'r1-control-ready\n','actor-ready')
        fixture(cli,cid,token)
        phase='target-projection'
        target=p.project(run(cli+['inspect','--type','container','--format',p.FORMAT,cid],seconds=4,cap=262144))
        c.check(target['id']==cid and target['image']==c.IMAGE and target['running'],'target')
        backend=Backend(cli,target,{'lost-stop':'stop','lost-start':'start_original'}.get(name))
        drift_refused=False
        phase='control'
        with p.Control(registry,target,c.digest(c.raw(pins())),backend) as control:
            try:
                control.step('disable_restart');control.step('stop')
                if name=='configuration-drift':
                    # Deliberate test-only resource drift, on the exact owned stopped fixture.
                    fixture(cli,cid,token)
                    ack=run(cli+['update','--memory=96m',cid]).decode().strip()
                    changed=True;c.check(ack==cid,'drift-ack')
                    fixture(cli,cid,token,changed=True)
                control.step('start_original');control.step('restore_restart')
            except ValueError as exc:
                if name=='configuration-drift' and changed and exc.args==('target-drift',):
                    drift_refused=True
                elif not (backend.reached and name in ('lost-stop','lost-start') and exc.args==('deliberate-lost-response',)):
                    raise
        before={f.name:f.read_bytes() for f in registry.iterdir()}
        state=p.inspect(registry)
        c.check(before=={f.name:f.read_bytes() for f in registry.iterdir()},'recovery-write')
        if name=='normal':
            c.check(state['original_restored'] and state['records']==8 and state['target']['id']==cid and
                    state['target']['config_sha256']==target['config_sha256'],'roundtrip')
        elif name=='configuration-drift':
            c.check(drift_refused and state['state']=='locally-stopped' and state['pending_action'] is None and
                    backend.calls==['disable_restart','stop'],'drift-started')
        else:
            c.check(state['pending_action']==backend.lost and state['reconciliation_required'] and
                    not state['original_restored'],'uncertainty-lost')
        receipt.update(target=target,recovery=state,commands=backend.calls,
                       fault_reached=backend.reached or drift_refused,finished_utc=c.now())
    except BaseException as exc:
        receipt['failure']={'phase':phase,'adapter_phase':backend.phase if backend else None,'code':diagnostic(exc)}
        raise
    finally:
        if backend:
            receipt['commands_attempted']=list(backend.calls)
            receipt['last_observation']=backend.last_observation
            receipt['command_observations']=list(backend.command_events)
        try:
            if attempted:
                row=fixture(cli,cid or cname,token,changed=changed)
                c.check(cid is None or row['id']==cid,'cleanup-identity')
                receipt['id']=row['id']
                ack=run(cli+['rm','--force',row['id']]).decode().strip()
                c.check(ack==row['id'],'cleanup-ack');receipt['removed']=True
        except BaseException as exc:
            receipt['cleanup_failure']={'code':diagnostic(exc)}
            raise
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory',required=True)
    args=parser.parse_args();os.umask(0o077)
    out=Path(args.output_directory).absolute()
    c.check(not out.exists() and all(not q.is_symlink() for q in (out,*out.parents)),'output')
    out.mkdir(mode=0o700);log=io.StringIO()
    report={'schema':1,'status':'retained-control-failed-live-blocked','started_utc':c.now(),
            'production_modified':False,'provider_connection_opened':False,'activation_authorized':False,
            'shared_handoff_validated':False,'cases':[]}
    stage='source'
    try:
        report['source_sha256']=pins();c.check(not image.c.git('status','--porcelain').strip(),'dirty-source')
        stage='tests'
        suite=unittest.defaultTestLoader.discover(str(ROOT),pattern='test_*.py')
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        report['tests']={'run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'skipped':len(result.skipped)}
        c.check(result.wasSuccessful() and result.testsRun>0 and not result.skipped and
                not image.DIAGNOSTIC.search(log.getvalue()),'tests')
        stage='docker';image.host.trusted_local_docker()
        c.check(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000,'uid')
        config=out/'empty-docker-config';config.mkdir(mode=0o700)
        cli=[image.host.DOCKER,'--config',str(config),'--host','unix://'+image.host.SOCKET]
        c.check(run(cli+['image','inspect','--format','{{.Id}}',c.IMAGE]).decode().strip()==c.IMAGE,'image-unavailable')
        for name in CASES:stage=name;case(out,cli,name,report)
        stage='final';c.check(pins()==report['source_sha256'] and not image.c.git('status','--porcelain').strip(),'source-change')
        report['status']='retained-control-offline-passed-live-blocked'
    except BaseException as exc:
        report.update(failure_stage=stage,failure_type=type(exc).__name__,failure_code=diagnostic(exc))
    finally:
        report['finished_utc']=c.now();(out/'report.json').write_bytes(c.raw(report));(out/'validation.log').write_text(log.getvalue())
        with zipfile.ZipFile(out/'acceptance.zip','x',compression=zipfile.ZIP_STORED) as archive:
            for n in ('report.json','validation.log'):archive.write(out/n,n)
            for name in CASES:
                for n in ('claim.json','events.jsonl'):
                    file=out/name/n
                    if file.is_file():archive.write(file,name+'/'+n)
    print(report['status']);print(out/'acceptance.zip')
    return 0 if report['status']=='retained-control-offline-passed-live-blocked' else 1


if __name__=='__main__':sys.exit(main())
