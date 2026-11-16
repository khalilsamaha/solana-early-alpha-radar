"""Build and check the full scanner application on owned offline containers only."""
import argparse
from contextlib import closing
import io
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import struct
import sys
import tempfile
import threading
import unittest
import uuid
import zipfile
import check_image as image
c=image.c
sys.path.insert(0,str(c.REPO/'r1-production-control'))
import production_control as pc
import command_io

CASES=('normal','sequence-gap','missing-endpoint')
LABEL='org.solana-radar.r1-full-scanner-review'
DIAGNOSTIC_IMAGE='sha256:55d2f2369e0a03835441a02ad9a65568a9288c3753aa276a89ff252c62eeac7f'
DIAGNOSTIC_REVISION='6270ada51ae04e1e0efbc6895286a327f764ee5c'
DIAGNOSTIC_TREE='be15ea96816aaae67339cfe94539d6eca52a090a'
DIAGNOSTIC_MANIFEST='bf330643bec5835413fbe85231f5bad876ecaf18a0b4c5e5618dcdddf8d7f694'


def run(command,**kwargs):return command_io.bounded(command,env=image.host.ENV,**kwargs)


def pins():
    return {**image.pins(),
        **{name:c.digest((c.REPO/name).read_bytes()) for name in
           ('r1-production-control/production_control.py','r1-production-control/command_io.py',
            'r1-control/control.py','scripts/r1-scanner-runtime-kali.sh','scripts/r1-scanner-runtime-diagnostic-kali.sh')}}


def configuration_fields(raw):
    """Diagnose owned fixture drift without exporting environment/command values."""
    row=pc.c.parse(raw);fields={}
    def visit(value,path):
        if type(value) is dict and value:
            for key,item in sorted(value.items()):visit(item,path+'/'+key.replace('~','~0').replace('/','~1'))
        elif type(value) is list and value:
            for index,item in enumerate(value):visit(item,path+'/'+str(index))
        else:
            item={'sha256':c.digest(c.raw(value)),'type':type(value).__name__}
            # Scalar engine flags and empty defaults are useful diagnostics.
            # Arbitrary strings (including argv, environment and paths) stay hashed.
            if value is None or type(value) in (bool,int,float) or value==[] or value=={}:item['value']=value
            elif type(value) is str and value in ('','none','private','rprivate','runc','no','SIGTERM','/app','1000:1000'):
                item['value']=value
            fields[path]=item
    for key in ('config','host','mounts'):visit(row[key],'/'+key)
    c.check(len(c.raw(fields))<=65536,'runtime-configuration-bound')
    return fields


def configuration_changes(before,after):
    return {key:{'before':before.get(key),'after':after.get(key)} for key in sorted(set(before)|set(after))
            if before.get(key)!=after.get(key)}


def diagnostic_candidate(destination):
    expected=c.stage(destination)
    # Reconstruct only the already verified image identity. The full manifest
    # hash must still match; changed packaged bytes cannot use this shortcut.
    expected['manifest'].update(source_revision=DIAGNOSTIC_REVISION,source_tree=DIAGNOSTIC_TREE)
    raw=c.raw(expected['manifest']);c.check(c.digest(raw)==DIAGNOSTIC_MANIFEST,'runtime-diagnostic-source-drift')
    expected['manifest_sha256']=DIAGNOSTIC_MANIFEST
    (destination/'app/manifest.json').write_bytes(raw)
    return expected


def command(case):return ['--disable-warning=ExperimentalWarning','/app/runtime-probe.mjs',case]


def isolation(raw,token,image_id,ipc,data,case):
    row=pc.c.parse(raw);target=pc.project(raw);cfg=row['config'];host=row['host']
    c.check(target['image']==image_id and target['restart']=='no' and target['stop_seconds']==35,'runtime-target')
    c.check(cfg.get('Labels',{}).get(LABEL)==token and cfg.get('User')=='1000:1000' and
            cfg.get('Entrypoint')==pc.c.ENTRY and cfg.get('Cmd')==command(case) and
            cfg.get('StopSignal')=='SIGTERM','runtime-command')
    expected={'NetworkMode':'none','ReadonlyRootfs':True,'Privileged':False,'Memory':512*1024**2,
        'MemorySwap':512*1024**2,'NanoCpus':1000000000,'PidsLimit':64,'Init':True,'CapDrop':['ALL']}
    c.check(all(type(host.get(k)) is type(v) and host[k]==v for k,v in expected.items()),'runtime-isolation')
    c.check(host.get('SecurityOpt') in (['no-new-privileges'],['no-new-privileges:true']) and
            host.get('LogConfig',{}).get('Type')=='none' and not host.get('PortBindings'),'runtime-security')
    mounts=row['mounts'];c.check(len(mounts)==2,'runtime-mount-count')
    wanted={'/r1-ipc':(str(ipc),False),'/r1-data':(str(data),True)}
    c.check({r.get('Destination') for r in mounts}==set(wanted),'runtime-mounts')
    for mount in mounts:
        source,rw=wanted[mount['Destination']]
        c.check(mount.get('Type')=='bind' and mount.get('Source')==source and mount.get('RW') is rw,'runtime-mount')
    return target


def verify_result(row,expected,case):
    image.c.verify_result(row.get('identity'),expected)
    missing=case=='missing-endpoint';normal=case=='normal'
    fixed={'schema':1,'kind':'full-scanner-runtime-probe','case':case,
        'outcome':'startup-refused-before-storage' if missing else 'application-gap-and-shutdown-confirmed',
        'application_entrypoint_started':not missing,'upstream_attempts':0,'public_http_connections_opened':0,
        'loopback_http_checked':not missing,'overall_ready':None if missing else False,
        'provider_enabled':None if missing else True,'provider_state':None if missing else 'error',
        'discovery_messages':3 if normal else 0,'discovery_gaps':0 if missing else 1,
        'candidates':3 if normal else 0,'persisted_candidates':None if missing else 3 if normal else 0,
        'persisted_launches':None if missing else 2 if normal else 0,
        'fixture_index_prepared':not missing,'statistics_worker_succeeded':not missing,
        'storage_created':not missing,'storage_closed':not missing,'radar_stopped':not missing,
        'activation_authorized':False}
    c.check(set(row)==set(fixed)|{'identity','blocked_public_http_attempts'} and
            all(type(row[k]) is type(value) and row[k]==value for k,value in fixed.items()),'runtime-result')
    c.check(type(row['blocked_public_http_attempts']) is int and row['blocked_public_http_attempts']>=0 and
            (not missing or row['blocked_public_http_attempts']==0),'runtime-fetch-count')


def proc_identity(pid):
    raw=Path('/proc',str(pid),'stat').read_text();fields=raw[raw.rindex(')')+2:].split()
    return {'pid':pid,'ppid':int(fields[1]),'start_ticks':int(fields[19])}


def validate_peer(peer,target):
    c.check(target['running'] and target['pid']>0 and peer['uid']==peer['gid']==1000 and
            peer['pid']==peer['process']['pid'] and peer['process']['ppid']==target['pid'] and
            peer['process']['start_ticks']>0,'runtime-peer')


def case(out,cli,image_id,expected,name,report):
    root=out/name;root.mkdir(mode=0o700)
    ipc=Path(tempfile.mkdtemp(prefix='r1-app-'));data=root/'data';data.mkdir(mode=0o700)
    token=uuid.uuid4().hex;cname='radar-r1-app-'+token
    receipt={'case':name,'token':token,'name':cname,'started_utc':image.now(),'ipc':str(ipc),
             'data':str(data),'id':None,'removed':False,'attach_client_completed':False}
    report['cases'].append(receipt)
    server=None;broker=None;client=None;cid=None;attempted=False;peer=[];errors=[];outputs=[]
    accepted=threading.Event();admitted=threading.Event();abort=threading.Event()
    def serve():
        try:
            with server.accept()[0] as conn:
                conn.settimeout(15)
                pid,uid,gid=struct.unpack('3i',conn.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                peer.append({'pid':pid,'uid':uid,'gid':gid,'process':proc_identity(pid)})
                accepted.set()
                c.check(admitted.wait(12),'runtime-peer-admission-timeout')
                if abort.is_set():return
                for seq in ([1,2,3] if name=='normal' else [2]):
                    event={'txType':'migration' if seq==2 and name=='normal' else 'create',
                           'mint':'1'*31+str(seq+1),'signature':'2'*88,'initialBuy':0}
                    conn.sendall(c.raw({'v':1,'seq':seq,'event':event}))
                conn.shutdown(socket.SHUT_WR)
                c.check(conn.recv(1)==b'','runtime-peer-unexpected-output')
        except BaseException as exc:errors.append(type(exc).__name__);accepted.set()
    def attach():
        try:outputs.append(run(cli+['start','--attach',cid],seconds=50,cap=65536))
        except BaseException as exc:errors.append(type(exc).__name__)
    def observe(selector,phase=None):
        raw=run(cli+['inspect','--type','container','--format',pc.FORMAT,selector],seconds=4,cap=262144)
        target=isolation(raw,token,image_id,ipc,data,name)
        if phase:
            fields=configuration_fields(raw);receipt[phase+'_configuration']=fields
            if phase!='before':receipt[phase+'_changes_from_created']=configuration_changes(receipt.get('before_configuration',{}),fields)
        return target
    try:
        if name!='missing-endpoint':
            server=socket.socket(socket.AF_UNIX);server.settimeout(10)
            server.bind(str(ipc/'discovery.sock'));os.chmod(ipc/'discovery.sock',0o600);server.listen(1)
            broker=threading.Thread(target=serve);broker.start()
        pc.c.write_new(root/'create-intent.json',c.raw({'schema':1,'name':cname,'token':token,
            'image':image_id,'case':name,'ipc':str(ipc),'data':str(data),'created_utc':image.now()}))
        args=['create','--name',cname,'--label',LABEL+'='+token,'--pull=never','--network=none',
            '--restart=no','--read-only','--init','--user=1000:1000','--cap-drop=ALL',
            '--security-opt=no-new-privileges:true','--memory=512m','--memory-swap=512m',
            '--cpus=1','--pids-limit=64','--log-driver=none','--no-healthcheck',
            '--stop-timeout=35','--stop-signal=SIGTERM',
            '--mount',f'type=bind,src={ipc},dst=/r1-ipc,readonly',
            '--mount',f'type=bind,src={data},dst=/r1-data',image_id,*command(name)]
        attempted=True;cid=run(cli+args).decode().strip()
        c.check(re.fullmatch('[a-f0-9]{64}',cid),'runtime-create-unconfirmed');receipt['id']=cid
        receipt['before']=observe(cid,'before');c.check(not receipt['before']['running'],'runtime-prestart')
        pc.c.write_new(root/'start-intent.json',c.raw({'schema':1,'id':cid,'target':receipt['before'],'created_utc':image.now()}))
        client=threading.Thread(target=attach);client.start()
        if broker:
            c.check(accepted.wait(10) and len(peer)==1 and not errors,'runtime-peer-unavailable')
            running=observe(cid,'running');validate_peer(peer[0],running)
            receipt.update(running=running,peer=peer[0]);admitted.set()
        client.join(timeout=51);c.check(not client.is_alive() and len(outputs)==1 and not errors,'runtime-client-unconfirmed')
        receipt['attach_client_completed']=True
        if broker:broker.join(timeout=16);c.check(not broker.is_alive() and not errors,'runtime-broker-unconfirmed')
        result=pc.c.parse(outputs[0]);verify_result(result,expected,name)
        receipt['result']=result
        after=observe(cid,'after');receipt['after']=after
        c.check(not after['running'] and after['pid']==0 and after['exit_code']==0,'runtime-exit-unconfirmed')
        c.check(after['config_sha256']==receipt['before']['config_sha256'],'runtime-configuration-changed')
        receipt.update(result=result,after=after,finished_utc=image.now())
    finally:
        abort.set();admitted.set()
        if server:server.close()
        try:
            if attempted:
                current=observe(cid or cname,'disposal');receipt['disposal_observation']=current
                c.check(cid is None or current['id']==cid,'runtime-cleanup-identity');receipt['id']=current['id']
                ack=run(cli+['rm','--force',current['id']],seconds=8).decode().strip()
                c.check(ack==current['id'],'runtime-cleanup-unconfirmed');receipt['removed']=True
        finally:
            if broker:broker.join(timeout=16)
            if client:client.join(timeout=51)
            receipt['threads_joined']=(broker is None or not broker.is_alive()) and (client is None or not client.is_alive())
            pc.c.write_new(root/'disposal.json',c.raw(receipt))
    c.check(receipt['removed'] and receipt['threads_joined'],'runtime-final-cleanup')
    db=data/'radar.sqlite'
    if name=='missing-endpoint':c.check(not db.exists() and not list(data.iterdir()),'runtime-refusal-wrote-storage')
    else:
        raw=pc.c.read(db,2*1024**2)
        with closing(sqlite3.connect(db.as_uri()+'?mode=ro&immutable=1',uri=True)) as connection:
            counts={table:connection.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('candidates','launch_registry')}
        c.check(counts=={'candidates':receipt['result']['persisted_candidates'],'launch_registry':receipt['result']['persisted_launches']}
                and pc.c.read(db,2*1024**2)==raw,'runtime-independent-database-replay')
        pc.c.write_new(root/'database-replay.json',c.raw({'schema':1,'counts':counts,'sha256':c.digest(raw),'bytes':len(raw),
            'production_data_used':False,'activation_authorized':False}))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-directory',required=True)
    parser.add_argument('--diagnose-existing-image',action='store_true')
    args=parser.parse_args();os.umask(0o077);out=Path(args.output_directory).absolute()
    c.check(not out.exists() and all(not p.is_symlink() for p in (out,*out.parents)),'runtime-output')
    out.mkdir(mode=0o700);log=io.StringIO();stage='source'
    report={'schema':1,'status':'scanner-runtime-failed-live-blocked','started_utc':image.now(),
        'cases':[],'production_modified':False,'provider_connection_opened':False,'activation_authorized':False,
        'diagnostic_only':args.diagnose_existing_image}
    try:
        report['source_sha256']=pins();c.check(not c.git('status','--porcelain').strip(),'dirty-source')
        stage='tests'
        import test_runtime
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_runtime))
        report['tests']={'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}
        c.check(result.wasSuccessful() and result.testsRun and not result.skipped,'runtime-tests')
        if not args.diagnose_existing_image:
            node=shutil.which('node');c.check(node is not None,'runtime-node-unavailable')
            node_log=run([node,'--test','--test-reporter=tap',str(c.REPO/'scanner/test/shared-startup.test.js'),
                str(c.REPO/'scanner/test/pumpportal-shared.test.js')],seconds=30,cap=262144).decode()
            log.write(node_log)
            counts={key:int(re.search(r'^# '+key+r' (\d+)$',node_log,re.M).group(1)) for key in ('tests','fail','cancelled','skipped')}
            c.check(counts['tests']>0 and not any(counts[k] for k in ('fail','cancelled','skipped')),'runtime-node-tests')
            report['node_tests']=counts
        stage='context';expected=(diagnostic_candidate if args.diagnose_existing_image else c.stage)(out/'context');report['candidate']=expected
        c.check(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000,'runtime-uid')
        image.host.trusted_local_docker();config=out/'empty-docker-config';config.mkdir(mode=0o700)
        cli=[image.host.DOCKER,'--config',str(config),'--host','unix://'+image.host.SOCKET]
        if args.diagnose_existing_image:
            image_id=DIAGNOSTIC_IMAGE
            c.check(run(cli+['image','inspect','--format','{{.Id}}',image_id]).decode().strip()==image_id,'runtime-diagnostic-image-unavailable')
            pc.c.write_new(out/'image.id',(image_id+'\n').encode())
        else:
            c.check(run(cli+['image','inspect','--format','{{.Id}}',c.BASE]).decode().strip()==c.BASE,'runtime-base-unavailable')
            pc.c.write_new(out/'build-intent.json',c.raw({'candidate':expected,'created_utc':image.now(),'retry_allowed':False}))
            stage='build';image.bounded(cli+['build','--network=none','--pull=false','--no-cache','--iidfile',str(out/'image.id'),str(out/'context')],
                seconds=120,record=out/'build.log',local_build=True)
            image_id=(out/'image.id').read_text().strip();c.check(re.fullmatch('sha256:[a-f0-9]{64}',image_id),'runtime-image-unconfirmed')
        report['image_id']=image_id
        stage='image-configuration'
        image_format='{"id":{{json .Id}},"user":{{json .Config.User}},"entrypoint":{{json .Config.Entrypoint}},"cmd":{{json .Config.Cmd}},"workdir":{{json .Config.WorkingDir}}}'
        image_config=pc.c.parse(run(cli+['image','inspect','--format',image_format,image_id]))
        c.check(image_config=={'id':image_id,'user':'1000:1000','entrypoint':pc.c.ENTRY,
            'cmd':['/app/verify.mjs'],'workdir':'/app'},'runtime-image-config')
        report['image_config']=image_config
        if not args.diagnose_existing_image:
            stage='verify-image';image.run_case(cli,image_id,expected,'verify',report['cases'])
        for name in (('normal',) if args.diagnose_existing_image else CASES):stage=name;case(out,cli,image_id,expected,name,report)
        c.check(pins()==report['source_sha256'] and not c.git('status','--porcelain').strip(),'runtime-source-changed')
        if args.diagnose_existing_image:
            report['status']='scanner-runtime-diagnostic-recorded-live-blocked'
        else:
            report['status']='scanner-runtime-offline-passed-live-blocked'
            pc.c.write_new(out/'deployment-candidate.json',c.raw({'schema':1,'image_id':image_id,
                'source_revision':expected['manifest']['source_revision'],'source_tree':expected['manifest']['source_tree'],
                'manifest_sha256':expected['manifest_sha256'],'tested_scope':'full-scanner-startup-shared-ipc-storage-shutdown-offline',
                'default_command':'verify-only','production_configuration_approved':False,'activation_authorized':False,
                'provider_connection_opened':False,'production_data_used':False}))
    except BaseException as exc:
        report.update(failure_stage=stage,failure_type=type(exc).__name__,
            failure_code=str(exc) if type(exc) is ValueError and re.fullmatch('[a-z-]+',str(exc)) else 'operation-unconfirmed')
    finally:
        report['finished_utc']=image.now();pc.c.write_new(out/'report.json',c.raw(report))
        pc.c.write_new(out/'validation.log',log.getvalue().encode())
        with zipfile.ZipFile(out/'acceptance.zip','x',compression=zipfile.ZIP_STORED) as archive:
            members={}
            names=['report.json','validation.log','build-intent.json','build.log','image.id','deployment-candidate.json',
                   'context/app/manifest.json','context/Dockerfile']
            names += [case+'/'+name for case in CASES for name in ('create-intent.json','start-intent.json','disposal.json','database-replay.json','data/radar.sqlite')]
            for name in names:
                path=out/name
                if path.is_file():
                    if name.endswith('/data/radar.sqlite'):
                        disposal=out/name.split('/')[0]/'disposal.json'
                        if not disposal.is_file():continue
                        closed=pc.c.parse(pc.c.read(disposal,2*1024**2))
                        if not closed.get('removed') or not closed.get('threads_joined'):continue
                    c.check(not path.is_symlink() and path.stat().st_size<=2*1024**2,'runtime-archive-bound')
                    raw=path.read_bytes();c.check(len(raw)<=2*1024**2,'runtime-archive-bound')
                    members[name]={'bytes':len(raw),'sha256':c.digest(raw)}
                    archive.writestr(name,raw)
            archive.writestr('members.json',c.raw({'schema':1,'members':members}))
    print(report['status']);print(out/'acceptance.zip')
    return 0 if report['status'] in ('scanner-runtime-offline-passed-live-blocked','scanner-runtime-diagnostic-recorded-live-blocked') else 1


if __name__=='__main__':raise SystemExit(main())
