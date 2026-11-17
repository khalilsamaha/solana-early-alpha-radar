"""Exact isolated scanner consumer and kernel Unix-peer binding; never production."""
import asyncio
import os
from pathlib import Path
import shutil
import socket
import stat
import struct
import subprocess
import sys
import time
import runtime as r
import application_scanner as application
sys.path.insert(0,str(r.ROOT.parent/'r1-native-handoff'))
import native as n
m=r.m;p=r.preparation
ENDPOINT='supervision-endpoint.json';INTENT='native-scanner-intent.json'
IDENTITY='native-scanner-identity.json';PEER='native-scanner-peer.json'


def read(registry,name):
    fd=p.s.open_directory(registry)
    try:
        raw=p.read_at(fd,name);row=m.parse(raw);m.check(m.raw(row)==raw,'native-canonical')
        return row,raw
    finally:os.close(fd)


def write(registry,name,row):
    fd=p.s.open_directory(registry)
    try:return p.write_at(fd,name,row)
    finally:os.close(fd)


def socket_identity(path):
    st=path.lstat()
    m.check(stat.S_ISSOCK(st.st_mode) and st.st_uid==os.getuid() and st.st_gid==os.getgid()
            and stat.S_IMODE(st.st_mode)==0o600,'native-endpoint-private')
    return {'device':st.st_dev,'inode':st.st_ino,'uid':st.st_uid,'gid':st.st_gid,'mode':stat.S_IMODE(st.st_mode)}


def validate_endpoint(row,claim_bytes,manifest,development):
    m.check(set(row)=={'schema','kind','claim_sha256','manifest_sha256','path','development','socket'}
            and type(row['schema']) is int and row['schema']==1 and row['kind']=='private-unix-endpoint'
            and row['claim_sha256']==m.digest(claim_bytes) and row['manifest_sha256']==m.digest(m.raw(manifest))
            and row['path']==manifest['config']['endpoint_path'] and row['development'] is development,'native-endpoint-binding')
    st=row['socket']
    m.check(set(st)=={'device','inode','uid','gid','mode'} and all(type(v) is int for v in st.values())
            and st['device']>=0 and st['inode']>0 and st['uid']==os.getuid() and st['gid']==os.getgid()
            and st['mode']==0o600,'native-endpoint-metadata')


def expected_result(mode,development):
    normal=mode=='session-native-normal'
    return {'event':'finished','tokens':['pumpportal:create','pumpportal:migration']+
            (['pumpportal:create'] if normal else []),'creations':2 if normal else 1,'gaps':1,
            'upstream_attempts':0,'fetch_attempts':0,'image_verified':not development,'development':development}


def validate_identity(row,claim_bytes,manifest,development):
    m.check(set(row)=={'schema','kind','claim_sha256','manifest_sha256','development','actor','process_identity'}
            and type(row['schema']) is int and row['schema']==1 and row['kind']=='isolated-native-scanner-identity'
            and row['claim_sha256']==m.digest(claim_bytes) and row['manifest_sha256']==m.digest(m.raw(manifest))
            and row['development'] is development,'native-identity-binding')
    proc=row['process_identity']
    m.check(type(proc) is dict and set(proc)=={'pid','ppid','start_ticks'} and
            all(type(v) is int and v>0 for v in proc.values()),'native-process-identity')
    if development:m.check(row['actor'] is None,'native-development-actor')
    else:
        actor=row['actor']
        validator=application.isolation if application.enabled(manifest) else n.consumer_isolation
        validator(actor,actor['label'],Path(manifest['config']['registry_path']))
        m.check(actor['running'] is True and actor['pid']==proc['pid'],'native-container-process')


def validate_peer(row,identity,identity_raw,endpoint_raw,claim_bytes,development):
    m.check(set(row)=={'schema','kind','claim_sha256','identity_sha256','endpoint_sha256','pid','uid','gid','process_identity'}
            and type(row['schema']) is int and row['schema']==1 and row['kind']=='kernel-unix-peer'
            and row['claim_sha256']==m.digest(claim_bytes) and row['identity_sha256']==m.digest(identity_raw)
            and row['endpoint_sha256']==m.digest(endpoint_raw),'native-peer-binding')
    proc=row['process_identity']
    m.check(set(proc)=={'pid','ppid','start_ticks'} and all(type(v) is int and v>0 for v in proc.values())
            and type(row['pid']) is int and row['pid']==proc['pid']
            and type(row['uid']) is int and row['uid']==os.getuid()
            and type(row['gid']) is int and row['gid']==os.getgid(),'native-peer-credentials')
    if development:m.check(proc==identity['process_identity'],'native-peer-process')
    else:m.check(proc['ppid']==identity['process_identity']['pid'],'native-peer-parent')


def evidence(manifest,development):
    registry=manifest['config']['registry_path'];claim,claim_bytes=read(registry,'supervision-claim.json')
    endpoint,endpoint_raw=read(registry,ENDPOINT);identity,identity_raw=read(registry,IDENTITY)
    peer,peer_raw=read(registry,PEER)
    validate_endpoint(endpoint,claim_bytes,manifest,development)
    validate_identity(identity,claim_bytes,manifest,development)
    validate_peer(peer,identity,identity_raw,endpoint_raw,claim_bytes,development)
    return {'endpoint_sha256':m.digest(endpoint_raw),'identity_sha256':m.digest(identity_raw),
            'peer_sha256':m.digest(peer_raw),'peer':peer,'development':development,
            'kernel_uid_gid_verified':True,'container_parent_verified':not development}


def server_class(base,manifest,development):
    registry=manifest['config']['registry_path'];_,claim_bytes=read(registry,'supervision-claim.json')
    class VerifiedUnixServer(base):
        async def start(self):
            await super().start()
            write(registry,ENDPOINT,{'schema':1,'kind':'private-unix-endpoint','claim_sha256':m.digest(claim_bytes),
                'manifest_sha256':m.digest(m.raw(manifest)),'path':str(self.path),'development':development,
                'socket':socket_identity(self.path)})
        async def _client(self,reader,writer):
            try:
                sock=writer.get_extra_info('socket')
                pid,uid,gid=struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                async with asyncio.timeout(manifest['policy']['setup_seconds']):
                    while True:
                        try:identity,raw=read(registry,IDENTITY);break
                        except FileNotFoundError:await asyncio.sleep(.005)
                validate_identity(identity,claim_bytes,manifest,development)
                endpoint,endpoint_raw=read(registry,ENDPOINT)
                peer={'schema':1,'kind':'kernel-unix-peer','claim_sha256':m.digest(claim_bytes),
                      'identity_sha256':m.digest(raw),'endpoint_sha256':m.digest(endpoint_raw),
                      'pid':pid,'uid':uid,'gid':gid,'process_identity':n.proc_identity(pid)}
                validate_peer(peer,identity,raw,endpoint_raw,claim_bytes,development)
                m.check(socket_identity(self.path)==endpoint['socket'],'native-endpoint-replaced')
                write(registry,PEER,peer)
                await super()._client(reader,writer)
            except Exception:
                writer.close()
                try:await writer.wait_closed()
                except Exception:pass
    return VerifiedUnixServer


class Scanner:
    def __init__(self,manifest,development):
        self.manifest=manifest;self.registry=Path(manifest['config']['registry_path']);self.development=development
        self.actor=None;self.process=None;self.result=None;self.initial=None;self.removed=False
        _,self.claim_bytes=read(self.registry,'supervision-claim.json')

    def start(self,worker,deadline):
        # The owned worker creates the private endpoint before any consumer.
        end=min(deadline,time.monotonic()+self.manifest['policy']['setup_seconds'])
        while True:
            try:endpoint,_=read(self.registry,ENDPOINT);break
            except FileNotFoundError:
                m.check(worker.poll() is None and time.monotonic()<end,'native-endpoint-not-ready');time.sleep(.01)
        validate_endpoint(endpoint,self.claim_bytes,self.manifest,self.development)
        claim=m.parse(self.claim_bytes)
        m.check(endpoint['socket']==socket_identity(self.registry/'discovery.sock')
                and read(self.registry,'supervision-claim.json')[1]==self.claim_bytes
                and r.pins()==claim['source_sha256']
                and m.inspect(claim['manifest_directory'],claim['manifest_sha256'])==self.manifest
                and m.digest(m.raw(p.inspect(self.registry,claim['manifest_sha256'])))==claim['preparation_sha256'],
                'native-endpoint-before-consumer')
        if self.development:
            write(self.registry,INTENT,{'schema':1,'claim_sha256':m.digest(self.claim_bytes),'development':True,
                                       'kind':'local-node-unix-fixture'})
            node=shutil.which('node');m.check(node is not None,'native-node-unavailable')
            self.process=subprocess.Popen([node,str(r.ROOT/'scanner_unix_fixture.mjs'),str(self.registry/'discovery.sock')],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                env=n.image.host.ENV,start_new_session=True,bufsize=0)
            m.check(m.parse(n.line(self.process))=={'event':'ready','image_verified':False,'development':True},'native-ready')
            self.initial=n.proc_identity(self.process.pid);actor=None
        else:
            n.image.host.trusted_local_docker()
            m.check(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000,'native-uid')
            config=self.registry/'native-docker-config';config.mkdir(mode=0o700)
            cli=[n.image.host.DOCKER,'--config',str(config),'--host','unix://'+n.image.host.SOCKET]
            full=application.enabled(self.manifest);image_id=application.IMAGE if full else n.c.IMAGE
            m.check(n.image.bounded(cli+['image','inspect','--format','{{.Id}}',image_id]).decode().strip()==image_id,'native-image-unavailable')
            self.actor=application.Actor(cli,self.registry) if full else n.Actor(cli,'consumer',self.registry)
            write(self.registry,INTENT,{'schema':1,'claim_sha256':m.digest(self.claim_bytes),'development':False,
                'kind':'isolated-application-consumer' if full else 'isolated-image-consumer',
                'name':self.actor.name,'token':self.actor.token,'image':image_id})
            self.actor.start();self.process=self.actor.process
            actor=self.actor.stable();self.initial=n.proc_identity(actor['pid'])
        m.check(time.monotonic()<deadline,'native-start-deadline')
        write(self.registry,IDENTITY,{'schema':1,'kind':'isolated-native-scanner-identity',
            'claim_sha256':m.digest(self.claim_bytes),'manifest_sha256':m.digest(m.raw(self.manifest)),
            'development':self.development,'actor':actor,'process_identity':self.initial})

    def finish(self,deadline,mode,collect):
        if mode==application.MODE:
            self.actor.finish(deadline,collect);self.result=self.actor.result
            m.check(time.monotonic()<deadline,'native-terminal-deadline');return
        normal=mode=='session-native-normal';wanted=expected_result(mode,self.development)
        sources=wanted['tokens']
        if self.development:
            raw,outcome=collect(self.process,max(.001,deadline-time.monotonic()))
            m.check(outcome=='returned','native-consumer-exit')
            rows=[m.parse(line) for line in raw.splitlines()]
            m.check(rows==[{'event':'discovery','source':source} for source in sources]+[wanted],'native-consumer-output')
            self.result=wanted
        else:
            for source in sources:self.actor.event(source)
            self.actor.finish('unsubscribed' if normal else 'upstream-aborted')
            n.reap(self.actor.process);self.result=self.actor.result
        m.check(time.monotonic()<deadline,'native-terminal-deadline')

    def close(self,reap):
        if self.development:
            if self.process is not None:
                try:reap(self.process);self.removed=True
                finally:self.process.stdout.close()
        elif self.actor is not None:
            # Includes an uncertain create/start: the durable intent binds name/token.
            try:self.actor.dispose()
            finally:self.process=self.actor.process;self.removed=self.actor.removed

    def snapshot(self):
        return {'kind':'isolated-native-scanner','development':self.development,
                'started':int(self.process is not None),'reaped':self.process is not None and self.process.returncode is not None,
                'returncode':None if self.process is None else self.process.returncode,'result':self.result,
                'actor':None if self.actor is None else self.actor.receipt(),'removed':self.removed,'process_identity':self.initial,
                'activation_authorized':False}


def validate(row,mode,*,complete,registry):
    keys={'kind','development','started','reaped','returncode','result','actor','removed','process_identity','activation_authorized'}
    m.check(type(row) is dict and set(row)==keys and row['kind']=='isolated-native-scanner'
            and type(row['development']) is bool and row['activation_authorized'] is False,'native-receipt')
    m.check(type(row['started']) is int and row['started'] in (0,1) and type(row['removed']) is bool,'native-start-count')
    if row['started']:
        m.check(row['reaped'] is True and type(row['returncode']) is int and row['removed'] is True,'native-reaping')
    else:m.check(row['reaped'] is False and row['returncode'] is None and row['result'] is None,'native-not-started')
    if row['development']:m.check(row['actor'] is None,'native-development-container')
    elif row['actor'] is not None:
        actor=row['actor'];m.check(actor['development'] is False and actor['removed'] is True
                                  and actor['client_reaped'] is True and actor['role']=='consumer','native-container-cleanup')
        if mode==application.MODE:application.validate_actor_receipt(actor,Path(registry),complete=complete)
        else:
            for observation in actor['observations']:
                n.consumer_isolation(observation,actor['token'],Path(registry))
                m.check(observation['id']==actor['id'],'native-container-id')
            if actor['initial'] is not None:n.consumer_isolation(actor['initial'],actor['token'],Path(registry))
    if row['result'] is not None:
        m.check(row['started']==1 and row['returncode']==0,'native-result')
        if mode==application.MODE:application.validate_result(row['result'])
        else:m.check(m.raw(row['result'])==m.raw(expected_result(mode,row['development'])),'native-result')
    if complete:
        m.check(row['result'] is not None and (row['development'] or row['actor'] is not None
                and row['actor']['created'] is True and row['actor']['ready'] is True
                and row['actor']['initial']['id']==row['actor']['id'] and row['actor']['observations']
                and row['actor']['result']==row['result']),'native-completion-required')
        identity,_=read(registry,IDENTITY)
        m.check(identity['process_identity']==row['process_identity'] and
                (row['development'] or identity['actor']==row['actor']['initial']),'native-receipt-identity')
