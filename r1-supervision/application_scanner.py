"""The accepted full application image under the existing offline session owner.

Only fresh fixture storage and the pinned network-none image are supported.
No production data, provider credentials or image/command override is accepted.
"""
from contextlib import closing
import copy
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import time
import runtime as r
# Resolve the capture library before the image checker adds its control helpers
# to sys.path; both legacy trees contain a module named shared_session.
import capture_session
sys.path.insert(0,str(r.ROOT.parent/'r1-native-handoff'))
import native as n
sys.path.insert(0,str(r.ROOT.parent/'r1-image'))
import check_runtime as check
m=r.m;p=r.preparation
MODE='session-application-normal'
IMAGE=check.DIAGNOSTIC_IMAGE
MANIFEST=check.DIAGNOSTIC_MANIFEST
TREE=check.DIAGNOSTIC_TREE
COMMAND=check.command('normal')
DATA='application-data'
MAX_DATABASE=262144
MAX_STORAGE=2*1024**2


def remaining(deadline,cap):
    left=deadline-time.monotonic()
    m.check(left>0,'application-deadline')
    return min(cap,left)


def enabled(manifest):return manifest['config'].get('shared_scanner_image') is not None


def validate_profile(manifest):
    cfg=manifest['config'];policy=manifest['policy']
    m.check(cfg.get('shared_scanner_image')==IMAGE and cfg.get('shared_scanner_manifest_sha256')==MANIFEST,
            'application-manifest-image')
    m.check(policy['memory_bytes']>=512*1024**2 and policy['shutdown_seconds']>=5,
            'application-fixture-profile')


def validate_result(row):
    identity={'status':'image-bytes-verified','manifest_sha256':MANIFEST,'files':60,
              'source_tree':TREE,'activation_authorized':False}
    m.check(type(row) is dict and m.raw(row.get('identity'))==m.raw(identity),'application-image-result')
    check.verify_runtime_fields(row,'normal')


def isolation(row,token,registry):
    fixed={'image':IMAGE,'label':token,'user':'1000:1000','network':'none','readonly':True,
        'privileged':False,'restart':'no','memory':512*1024**2,'swap':512*1024**2,'pids':64,
        'cpus':1000000000,'init':True,'logging':'none','caps':['ALL'],'cmd':COMMAND,'entrypoint':n.c.ENTRY}
    m.check(all(type(row.get(k)) is type(v) and row[k]==v for k,v in fixed.items()),'application-isolation')
    m.check(type(token) is str and re.fullmatch('[a-f0-9]{32}',token) and
            row.get('security') in (['no-new-privileges:true'],['no-new-privileges']),'application-security')
    m.check(re.fullmatch('[a-f0-9]{64}',row.get('id','')) and type(row.get('running')) is bool and
            type(row.get('pid')) is int and row['pid']>=0 and type(row.get('exit_code')) is int,
            'application-state')
    for field in ('started','finished'):
        m.check(type(row.get(field)) is str and re.fullmatch('[0-9TZ:.+\\-]{20,40}',row[field]),'application-time')
    mounts=row.get('mounts');m.check(type(mounts) is list and len(mounts)==2,'application-mount-count')
    expected={'/r1-ipc':(str(registry),False),'/r1-data':(str(registry/DATA),True)}
    m.check({mount.get('Destination') for mount in mounts}==set(expected),'application-destinations')
    for mount in mounts:
        source,writable=expected[mount['Destination']]
        m.check(mount.get('Type')=='bind' and mount.get('Source')==source and mount.get('RW') is writable,
                'application-mount')


def comparable(row):
    value=copy.deepcopy(row);value['mounts']=sorted(value['mounts'],key=lambda mount:mount['Destination'])
    return value


def storage_proof(registry):
    directory=registry/DATA;fd=p.s.open_directory(directory)
    try:
        raw=p.read_at(fd,'radar.sqlite');m.check(len(raw)<=MAX_DATABASE,'application-database-bound')
        total=0;files=0;file_sha256={}
        for count,path in enumerate(directory.rglob('*'),1):
            m.check(count<=64,'application-storage-nodes')
            info=path.lstat()
            m.check(not stat.S_ISLNK(info.st_mode),'application-storage-link')
            m.check(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode),'application-storage-type')
            if stat.S_ISREG(info.st_mode):
                files+=1;total+=info.st_size
                m.check(files<=32 and total<=MAX_STORAGE,'application-storage-bound')
                parent=p.s.open_directory(path.parent)
                try:content=p.read_at(parent,path.name)
                finally:os.close(parent)
                file_sha256[str(path.relative_to(directory))]=m.digest(content)
        with closing(sqlite3.connect((directory/'radar.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
            m.check(db.execute('PRAGMA integrity_check').fetchall()==[('ok',)],'application-database-integrity')
            counts={table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('candidates','launch_registry')}
        m.check(counts=={'candidates':3,'launch_registry':2} and p.read_at(fd,'radar.sqlite')==raw,
                'application-database-replay')
        for name,digest in file_sha256.items():
            path=directory/name;parent=p.s.open_directory(path.parent)
            try:m.check(m.digest(p.read_at(parent,path.name))==digest,'application-storage-changed')
            finally:os.close(parent)
        p.same_directory(directory,fd)
        return {'schema':1,'sha256':m.digest(raw),'bytes':len(raw),'counts':counts,
                'storage_bytes':total,'storage_files':files,'file_sha256':file_sha256,'production_data_used':False}
    finally:os.close(fd)


class Actor(n.Actor):
    def __init__(self,cli,registry):
        super().__init__(cli,'consumer',registry)
        self.database=None;self.capacity=None

    def validate(self,row):
        isolation(row,self.token,self.registry)
        m.check(self.cid is None or row['id']==self.cid,'application-container-id')

    def observe(self,deadline=None):
        m.check(len(self.observations)<128,'application-observation-bound')
        row=m.parse(check.run(self.cli+['inspect','--type','container','--format',n.c.FORMAT,self.cid or self.name],
                             seconds=4 if deadline is None else remaining(deadline,4)))
        self.validate(row);self.observations.append(row);return row

    def start(self,deadline=None):
        # Explicit default applies only to direct offline Actor tests. The actual
        # supervisor always supplies its own remaining aggregate deadline.
        if deadline is None:deadline=time.monotonic()+20
        remaining(deadline,10)
        m.check(not self.attempted,'application-reuse')
        directory=self.registry/DATA;directory.mkdir(mode=0o700)
        fd=p.s.open_directory(directory)
        try:
            sample=p.s.sample(fd);self.capacity=sample
            m.check(sample['available_bytes']>=4*MAX_STORAGE,'application-storage-insufficient')
        finally:os.close(fd)
        args=['create','--name',self.name,'--label',n.c.LABEL+'='+self.token,'--pull=never',
            '--network=none','--restart=no','--read-only','--init','--user=1000:1000','--cap-drop=ALL',
            '--security-opt=no-new-privileges:true','--memory=512m','--memory-swap=512m','--cpus=1',
            '--pids-limit=64','--log-driver=none','--no-healthcheck','--stop-timeout=35','--stop-signal=SIGTERM',
            '--mount',f'type=bind,src={self.registry},dst=/r1-ipc,readonly',
            '--mount',f'type=bind,src={directory},dst=/r1-data',IMAGE,*COMMAND]
        self.attempted=True
        candidate=check.run(self.cli+args,seconds=remaining(deadline,10)).decode().strip()
        m.check(re.fullmatch('[a-f0-9]{64}',candidate),'application-create-id')
        self.cid=candidate;self.created=True
        m.check(not self.observe(deadline)['running'],'application-created-running')
        remaining(deadline,1)
        self.process=subprocess.Popen(self.cli+['start','--attach',self.cid],stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=n.image.host.ENV,start_new_session=True,bufsize=0)
        deadline=min(deadline,time.monotonic()+6)
        while True:
            row=self.observe(deadline)
            if row['running'] and row['pid']>0:break
            m.check(self.process.poll() is None and time.monotonic()<deadline,'application-start-unconfirmed')
            time.sleep(.02)
        self.initial=row;self.ready=True
        return self

    def stable(self,deadline=None):
        row=self.observe(deadline);m.check(comparable(row)==comparable(self.initial),'application-generation-changed');return row

    def expect_stopped(self,row):
        expected={k:v for k,v in comparable(self.initial).items() if k not in ('running','pid','exit_code','finished')}
        final=comparable(row)
        m.check(all(final.get(k)==v for k,v in expected.items()) and final['running'] is False and
                final['pid']==0 and final['exit_code']==0 and not final['finished'].startswith('0001-'),
                'application-stop-unconfirmed')

    def finish(self,deadline,collect):
        raw,outcome=collect(self.process,remaining(deadline,30))
        m.check(outcome=='returned','application-client-unconfirmed')
        result=m.parse(raw);validate_result(result)
        row=self.observe(deadline);self.expect_stopped(row)
        self.database=storage_proof(self.registry);self.stopped_snapshot=row;self.result=result

    def receipt(self):return {**super().receipt(),'application_storage':self.database,'application_capacity':self.capacity}


def validate_actor_receipt(actor,registry,*,complete):
    return validate_actor_evidence(actor,registry,complete=complete,
                                  storage=storage_proof(registry) if complete else None)


def validate_actor_evidence(actor,registry,*,complete,storage):
    """Pure receipt validation; portable readers must independently replay storage."""
    m.check(actor['development'] is False and actor['removed'] is True and actor['client_reaped'] is True,
            'application-disposal')
    for observation in actor['observations']:
        isolation(observation,actor['token'],registry)
        m.check(observation['id']==actor['id'],'application-receipt-id')
    if actor['initial'] is not None:isolation(actor['initial'],actor['token'],registry)
    if complete:
        initial=actor['initial'];observations=actor['observations']
        m.check(actor['created'] is True and actor['ready'] is True and actor['role']=='consumer' and
                initial is not None and initial['id']==actor['id'] and initial['running'] is True and initial['pid']>0 and observations,
                'application-running-evidence')
        expected={k:v for k,v in comparable(initial).items() if k not in ('running','pid','exit_code','finished')}
        final=comparable(observations[-1])
        m.check(all(final.get(k)==value for k,value in expected.items()) and final['running'] is False and
                final['pid']==0 and final['exit_code']==0 and not final['finished'].startswith('0001-'),
                'application-stopped-evidence')
        m.check(type(actor['application_capacity']['available_bytes']) is int and
                actor['application_capacity']['available_bytes']>=4*MAX_STORAGE and
                m.raw(actor['application_storage'])==m.raw(storage),'application-storage-evidence')
        validate_result(actor['result'])
