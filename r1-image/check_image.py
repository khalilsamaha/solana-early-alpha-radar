"""One isolated image build and native Unix discovery check. No production target."""
import argparse
from datetime import datetime,timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
import zipfile
import candidate as c

spec=importlib.util.spec_from_file_location('image_host',c.REPO/'r1-host-review/check.py')
host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
LABEL='org.solana-radar.r1-image-review'
FORMAT='{"id":{{json .Id}},"image":{{json .Image}},"label":{{json (index .Config.Labels "'+LABEL+'")}},"user":{{json .Config.User}},"network":{{json .HostConfig.NetworkMode}},"readonly":{{json .HostConfig.ReadonlyRootfs}},"privileged":{{json .HostConfig.Privileged}},"restart":{{json .HostConfig.RestartPolicy.Name}},"mounts":{{json .Mounts}},"running":{{json .State.Running}},"exit_code":{{json .State.ExitCode}},"memory":{{json .HostConfig.Memory}},"swap":{{json .HostConfig.MemorySwap}},"pids":{{json .HostConfig.PidsLimit}},"cpus":{{json .HostConfig.NanoCpus}},"init":{{json .HostConfig.Init}},"logging":{{json .HostConfig.LogConfig.Type}},"caps":{{json .HostConfig.CapDrop}},"security":{{json .HostConfig.SecurityOpt}}}'
DIAGNOSTIC=re.compile(r'ResourceWarning|unraisable|never retrieved|shielded future|Task was destroyed|Traceback',re.I)

def now():return datetime.now(timezone.utc).isoformat()
def pins():
    names=c.sources()+['r1-host-review/check.py','scripts/r1-image-kali.sh']
    names+=['r1-image/'+p.name for p in c.ROOT.iterdir() if p.is_file()]
    return {n:c.digest((c.REPO/n).read_bytes()) for n in sorted(set(names))}

def bounded(command,seconds=15,cap=1024**2,record=None,local_build=False):
    """Bound and drain combined diagnostics; kill/reap client on uncertainty, never retry."""
    p=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        env={**host.ENV,**({"DOCKER_BUILDKIT":"0"} if local_build else {})},start_new_session=True)
    data=bytearray();deadline=time.monotonic()+seconds
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(p.stdout,selectors.EVENT_READ)
            while True:
                left=deadline-time.monotonic()
                c.check(left>0 and selector.select(left),'command-timeout')
                b=os.read(p.stdout.fileno(),4096)
                if not b:break
                data.extend(b);c.check(len(data)<=cap,'command-output-limit')
        p.wait(timeout=max(.001,deadline-time.monotonic()))
        c.check(p.returncode==0,'command-failed')
        c.check(not DIAGNOSTIC.search(data.decode(errors='replace')),'command-diagnostic')
        return bytes(data)
    finally:
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=2)
        p.stdout.close()
        if record is not None:record.write_bytes(bytes(data[:cap]))

def isolation(row,token,image,ipc):
    expected={'image':image,'label':token,'user':'1000:1000','network':'none','readonly':True,
        'privileged':False,'restart':'no','memory':128*1024**2,'swap':128*1024**2,'pids':32,
        'cpus':1000000000,'init':True,'logging':'none','caps':['ALL']}
    c.check(all(type(row.get(k)) is type(v) and row[k]==v for k,v in expected.items()),'container-isolation')
    c.check(row.get('security') in (['no-new-privileges:true'],['no-new-privileges']),'container-security')
    c.check(re.fullmatch('[a-f0-9]{64}',row.get('id','')),'container-id')
    mounts=row.get('mounts')
    if ipc is None:c.check(mounts==[],'unexpected-mount')
    else:
        c.check(isinstance(mounts,list) and len(mounts)==1,'mount-count')
        m=mounts[0]
        c.check(m.get('Type')=='bind' and m.get('Source')==str(ipc) and
            m.get('Destination')=='/r1-ipc' and m.get('RW') is False,'ipc-mount')

def run_case(cli,image,expected,case,receipts):
    token=uuid.uuid4().hex;name='radar-r1-image-'+token
    receipt={'case':case,'name':name,'token':token,'started_utc':now(),'removed':False,'source_overlay':False}
    receipts.append(receipt)
    ipc=Path(tempfile.mkdtemp(prefix='r1-img-',dir='/tmp')) if case!='verify' else None
    server=None;thread=None;errors=[];accepted=[];cid=None;attempted=False
    def serve():
        try:
            with server.accept()[0] as conn:
                conn.settimeout(3);accepted.append(True)
                seqs=[2] if case=='sequence-gap' else [1,2,3]
                for seq in seqs:
                    e={'txType':'migration' if seq==2 and case=='normal' else 'create',
                       'mint':'1'*31+str(seq+1),'signature':'2'*88,'initialBuy':0}
                    conn.sendall(c.raw({'v':1,'seq':seq,'event':e}))
                conn.shutdown(socket.SHUT_WR)
        except BaseException as e:errors.append(type(e).__name__)
    try:
        if ipc and case!='missing-endpoint':
            server=socket.socket(socket.AF_UNIX);server.settimeout(12)
            server.bind(str(ipc/'discovery.sock'));os.chmod(ipc/'discovery.sock',0o600);server.listen(1)
            thread=threading.Thread(target=serve);thread.start()
        args=['create','--name',name,'--label',LABEL+'='+token,'--pull=never','--network=none',
            '--restart=no','--read-only','--init','--user=1000:1000','--cap-drop=ALL',
            '--security-opt=no-new-privileges:true','--memory=128m','--memory-swap=128m',
            '--cpus=1','--pids-limit=32','--log-driver=none','--no-healthcheck']
        if ipc:args+=['--mount',f'type=bind,src={ipc},dst=/r1-ipc,readonly']
        args+=[image]
        if case!='verify':args+=['/app/probe.mjs','/r1-ipc/discovery.sock']
        attempted=True
        cid=bounded(cli+args).decode().strip();c.check(re.fullmatch('[a-f0-9]{64}',cid),'create-unconfirmed')
        receipt['id']=cid
        def inspect(ref):return host.strict_json(bounded(cli+['inspect','--type','container','--format',FORMAT,ref]))
        row=inspect(cid);isolation(row,token,image,ipc);c.check(row['running'] is False,'prestart-state')
        receipt['before']=row
        result=host.strict_json(bounded(cli+['start','--attach',cid],seconds=15))
        if case=='verify':c.verify_result(result,expected)
        else:c.verify_probe(result,expected,case)
        row=inspect(cid);isolation(row,token,image,ipc)
        c.check(row['running'] is False and type(row['exit_code']) is int and row['exit_code']==0,'exit-unconfirmed')
        if thread:thread.join(timeout=13);c.check(not thread.is_alive() and accepted==[True] and not errors,'unix-server')
        receipt.update(result=result,after=row,native_unix=bool(accepted),finished_utc=now())
    finally:
        if server:server.close()
        if thread:thread.join(timeout=13)
        # A lost create response is reconciled by random name + exact ownership before removal.
        if attempted:
            row=host.strict_json(bounded(cli+['inspect','--type','container','--format',FORMAT,cid or name]))
            isolation(row,token,image,ipc)
            c.check(cid is None or row['id']==cid,'cleanup-identity')
            receipt['id']=row['id']
            ack=bounded(cli+['rm','--force',row['id']]).decode().strip()
            c.check(ack==row['id'],'cleanup-unconfirmed');receipt['removed']=True
        if ipc and (not attempted or receipt['removed']):shutil.rmtree(ipc)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-directory',required=True)
    args=parser.parse_args();os.umask(0o077)
    out=Path(args.output_directory).absolute()
    c.check(not out.exists() and all(not p.is_symlink() for p in [out.parent,*out.parents]),'output-reuse-or-link')
    out.mkdir(mode=0o700);log=io.StringIO()
    report={'schema':1,'status':'image-check-failed-live-blocked','started_utc':now(),
        'production_modified':False,'provider_connection_opened':False,'activation_authorized':False,'cases':[]}
    stage='source'
    try:
        report['source_sha256']=pins();c.check(not c.git('status','--porcelain').strip(),'source-not-clean')
        stage='tests';suite=unittest.defaultTestLoader.discover(str(c.ROOT),pattern='test_*.py')
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        report['tests']={'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}
        c.check(result.wasSuccessful() and result.testsRun and not result.skipped and not DIAGNOSTIC.search(log.getvalue()),'tests')
        stage='context';expected=c.stage(out/'context');report['candidate']=expected
        c.check(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000,'uid-required')
        host.trusted_local_docker();config=out/'empty-docker-config';config.mkdir(mode=0o700)
        cli=[host.DOCKER,'--config',str(config),'--host','unix://'+host.SOCKET]
        stage='base';base=bounded(cli+['image','inspect','--format','{{.Id}}',c.BASE]).decode().strip()
        c.check(base==c.BASE,'base-image-missing-or-changed')
        stage='build';(out/'build-intent.json').write_bytes(c.raw({'candidate':expected,'started_utc':now(),'retry_allowed':False}))
        build=bounded(cli+['build','--network=none','--pull=false','--no-cache','--iidfile',str(out/'image.id'),str(out/'context')],seconds=120,record=out/'build.log',local_build=True)
        (out/'build.log').write_bytes(build)
        image=(out/'image.id').read_text().strip();c.check(re.fullmatch('sha256:[a-f0-9]{64}',image),'build-unconfirmed')
        report['image_id']=image
        image_format='{"id":{{json .Id}},"user":{{json .Config.User}},"entrypoint":{{json .Config.Entrypoint}},"cmd":{{json .Config.Cmd}},"workdir":{{json .Config.WorkingDir}}}'
        image_config=host.strict_json(bounded(cli+['image','inspect','--format',image_format,image]))
        c.check(image_config=={'id':image,'user':'1000:1000','entrypoint':['/usr/bin/env','-i',
            'PATH=/usr/local/bin:/usr/bin:/bin','LANG=C.UTF-8','node'],
            'cmd':['/app/verify.mjs'],'workdir':'/app'},'image-config-mismatch')
        report['image_config']=image_config
        stage='cases'
        for case in ('verify','normal','sequence-gap','missing-endpoint'):run_case(cli,image,expected,case,report['cases'])
        stage='final'
        c.check(pins()==report['source_sha256'] and not c.git('status','--porcelain').strip(),'source-changed')
        c.check(all(r['removed'] for r in report['cases']),'cleanup')
        candidate={'schema':1,'image_id':image,'image_config':image_config,
            'source_revision':expected['manifest']['source_revision'],
            'source_tree':expected['manifest']['source_tree'],'manifest_sha256':expected['manifest_sha256'],
            'base_image':c.BASE,'scanner_source_mode':'shared','activation_authorized':False,
            'production_configuration_approved':False,'upstream_owner_included':False,
            'tested_scope':'isolated-image-bytes-and-synthetic-discovery',
            'remaining_gates':['production-handoff-rollback','live-supervision-credentials',
                'real-evidence-delivery-retention-capacity','approved-pilot-terms-and-rollout']}
        (out/'deployment-candidate.json').write_bytes(c.raw(candidate))
        report['deployment_candidate_sha256']=c.digest(c.raw(candidate))
        report['status']='image-candidate-offline-passed-live-blocked'
    except BaseException as e:
        report.update(failure_stage=stage,failure_type=type(e).__name__,
            failure_code=str(e) if type(e) is ValueError and re.fullmatch('[a-z-]+',str(e)) else 'operation-unconfirmed')
    finally:
        report['finished_utc']=now();(out/'report.json').write_bytes(c.raw(report));(out/'validation.log').write_text(log.getvalue())
        with zipfile.ZipFile(out/'acceptance.zip','x',compression=zipfile.ZIP_STORED) as archive:
            for name in ('report.json','validation.log','build-intent.json','build.log','image.id','deployment-candidate.json','context/app/manifest.json','context/Dockerfile'):
                if (out/name).is_file():archive.write(out/name,name)
    print(report['status']);print(out/'acceptance.zip')
    return 0 if report['status']=='image-candidate-offline-passed-live-blocked' else 1

if __name__=='__main__':sys.exit(main())
