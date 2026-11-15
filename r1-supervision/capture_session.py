"""Existing capture/session library under manifest limits; fixed offline peers only."""
import asyncio
from dataclasses import asdict
from datetime import datetime
import os
import stat
from pathlib import Path
import sys
import runtime as r
sys.path.insert(0,str(r.ROOT.parent/'r1-integration'))
import common as c
import separated_session as s
import fixtures
import capture
import measurement
from provider_wire import Wire,secret_variants
from shared_discovery import deliver
m=r.m;p=r.preparation
PIPE_MODES={'session-scanner-normal','session-scanner-cleanup-failure'}
NATIVE_MODES={'session-native-normal','session-native-cleanup-failure'}
SCANNER_MODES=PIPE_MODES|NATIVE_MODES
MODES={'session-normal','session-cleanup-failure','session-operator-stop'}|SCANNER_MODES
FILES=('admission.json','research-retired.json','stopped.json','session.jsonl','capture/ticks.db')


def kind(mode):
    return mode.replace('session-scanner-','session-').replace('session-native-','session-')


def validate_mode(manifest,mode):
    limits(manifest)
    if mode in PIPE_MODES:
        m.check(manifest['policy']['research_seconds']<=3 and manifest['policy']['service_seconds']<=5
                and r.profile(manifest)['wall_seconds']<=12,'scanner-fixture-duration')
    if mode in NATIVE_MODES:
        import native_scanner as native
        m.check(manifest['config']['scanner_image']==native.n.c.IMAGE,'native-manifest-image')
        m.check(manifest['policy']['research_seconds']<=3 and manifest['policy']['service_seconds']<=5
                and r.profile(manifest)['wall_seconds']<=30,'native-fixture-duration')


def limits(manifest):
    policy=manifest['policy']
    m.check(policy['research_seconds'] is not None,'session-research-duration-required')
    value=capture.Limits(messages=4,seconds=policy['research_seconds'],
                         raw_bytes=policy['raw_bytes'],sample_modulus=1)
    s.validate_limits(value)
    m.check(policy['memory_bytes']>=256*1024**2 and policy['open_files']>=32,'session-resource-minimum')
    return value


def directory(manifest):
    return Path(manifest['config']['capture_path'])/'supervised-session'


def expected_terminal(manifest,mode,*,replay=False):
    """Recheck fixed receipts and bytes; initial parent validation also replays DB/journal.

    Historical inspection never calls capture.verify/measurement.replay because
    their lock helper may create a missing lock. No filesystem repair is allowed.
    """
    m.check(mode in MODES,'session-mode')
    registry=manifest['config']['registry_path'];regfd=p.s.open_directory(registry)
    try:
        preparation_claim=m.parse(p.read_at(regfd,p.CLAIM))
        prepared=p.inspect(registry,m.digest(m.raw(manifest)))
        gate_bytes=p.read_at(regfd,'supervision-storage.json');gate=m.parse(gate_bytes)
        attempt=m.parse(p.read_at(regfd,'supervision-claim.json'))
        p.validate_observation(gate,manifest,preparation_claim)
        m.check(m.raw(gate)==gate_bytes and gate['capacity_sample_sufficient']
            and datetime.fromisoformat(gate['started_utc'])>=datetime.fromisoformat(attempt['created_utc']) and all(
            p.s.identity(gate['before'][role])==p.s.identity(prepared['observation']['after'][role])
            for role in p.s.ROLES),'session-storage-binding')
    finally:os.close(regfd)
    root=directory(manifest);fd=p.s.open_directory(root)
    try:
        data={}
        for name in FILES:
            if name.startswith('capture/'):
                capfd=p.s.open_directory(root/'capture')
                try:data[name]=p.read_at(capfd,'ticks.db')
                finally:os.close(capfd)
            else:data[name]=p.read_at(fd,name)
        admission,retired,stopped=(m.parse(data[name]) for name in FILES[:3])
        m.check(m.raw(admission)==m.raw({'schema_version':1,'kind':'r1-separated-session-v1',
                'limits':asdict(limits(manifest)),'service_seconds':manifest['policy']['service_seconds'],
                'source_sha256':c.pins(),'live_launch_authorized':False,
                'production_handoff_verified':False,'automatic_resume_allowed':False}),'session-admission-binding')
        policy=manifest['policy']
        m.check(len(data['capture/ticks.db'])<=policy['database_bytes']
                and len(data['session.jsonl'])<=policy['journal_bytes']
                and sum(len(data[name]) for name in FILES[:3])<=policy['receipt_bytes'],'session-artifact-budget')
        for row in (retired,stopped):
            m.check(row['admission_sha256']==m.digest(data['admission.json'])
                    and row['live_launch_authorized'] is False,'session-terminal-admission')
        m.check(stopped['retirement_sha256']==m.digest(data['research-retired.json'])
                and stopped['research']==retired['research'] and stopped['capture_thread_joined'] is True
                and stopped['local_upstream_closed'] is True and stopped['peer_uid_verified'] is False
                and stopped['production_handoff_verified'] is False
                and stopped['provider_acknowledgement_verified'] is False
                and stopped['billing_cutoff_verified'] is False
                and retired['research_cannot_rearm'] is True,'session-stop-binding')
        expected_cleanup='unsubscribed' if kind(mode)=='session-normal' else 'upstream-aborted'
        m.check(retired['research']['cleanup']['outcome']==expected_cleanup
                and retired['discovery_continues'] is (kind(mode)=='session-normal')
                and stopped['owner']['research_attachments']==1 and stopped['owner']['upstream_attempts']==1,
                'session-owner-binding')
        if replay:
            cap=capture.verify(root/'capture');journal=measurement.replay(root/'capture',root/'session.jsonl')
            m.check(journal['capture_chain_sha256']==cap['chain_sha256'],'session-replay')
        p.same_directory(root,fd)
        # Recapture all bytes to reject changes across semantic validation.
        for name in FILES:
            if name.startswith('capture/'):
                other=p.s.open_directory(root/'capture')
                try:current=p.read_at(other,'ticks.db')
                finally:os.close(other)
            else:current=p.read_at(fd,name)
            m.check(current==data[name],'session-evidence-changed')
        result={'kind':'manifest-supervised-capture-fixture','mode':mode,
                'storage_gate_sha256':m.digest(gate_bytes),
                'artifact_sha256':{name:m.digest(value) for name,value in data.items()},
                'research_cleanup':expected_cleanup,'discovery_continued_after_retirement':retired['discovery_continues'],
                'capture_thread_joined':True,'local_upstream_closed':True,
                'synthetic_upstream_attempts':1,'research_attachments':1,
                'transport':'unix' if mode in NATIVE_MODES else 'pipe' if mode in PIPE_MODES else 'in-process-fixture','peer_uid_verified':False,
                'provider_connection_opened':False,'real_credential_used':False,'activation_authorized':False}
        if mode in NATIVE_MODES:
            import native_scanner as native
            result['native_peer']=native.evidence(manifest,attempt['native_development'])
        return result
    finally:os.close(fd)


async def exercise(manifest,mode,pipe_fd=-1,native_development=False):
    selected=kind(mode).removeprefix('session-')
    class ScannerUpstream(fixtures.Peer):
        async def send(self,command):
            row=c.strict_json(command.encode());self.sent.append(row)
            if row['method']=='subscribeTokenTrade':
                for event in ('buy','sell','migration'):self.frames.put_nowait(self.event(event))
            if row['method']=='unsubscribeTokenTrade' and selected=='cleanup-failure':
                raise RuntimeError(fixtures.SECRET)
    peer=(ScannerUpstream if mode in SCANNER_MODES else fixtures.Peer)(selected,4)
    discovery_progress=None
    class PipeServer(fixtures.TestServer):
        async def start(self):
            nonlocal discovery_progress
            discovery_progress=self.progress
            self.accepted=True;self.connected.set();loop=asyncio.get_running_loop()
            self.file=os.fdopen(pipe_fd,'wb',buffering=0)
            class Protocol(asyncio.streams.FlowControlMixin):
                def __init__(self):
                    super().__init__(loop=loop);self.closed=loop.create_future()
                def connection_lost(self,exc):
                    super().connection_lost(exc)
                    if not self.closed.done():self.closed.set_result(None)
                def _get_close_waiter(self,stream):return self.closed
            self.transport,protocol=await loop.connect_write_pipe(Protocol,self.file)
            self.writer=asyncio.StreamWriter(self.transport,protocol,None,loop)
            self.task=asyncio.create_task(deliver(self.owner,self.writer,self.progress))
        async def close(self):
            await super().close();self.writer.close()
            await asyncio.wait_for(self.writer.wait_closed(),1)
    shutdown,retired,bound,peer_ready,started,admitted=(asyncio.Event() for _ in range(6))
    attempts=0
    async def factory():
        nonlocal attempts
        attempts+=1;peer.frames.put_nowait(peer.event('create'))
        return Wire(peer,secret_variants(fixtures.SECRET))
    original=s.Server
    if mode in NATIVE_MODES:
        import native_scanner as native
        base=native.server_class(original,manifest,native_development)
        class TrackedUnixServer(base):
            async def start(self):
                nonlocal discovery_progress
                discovery_progress=self.progress;await super().start()
        s.Server=TrackedUnixServer
    else:s.Server=PipeServer if mode in PIPE_MODES else fixtures.TestServer
    task=asyncio.create_task(s.run(directory(manifest),Path(manifest['config']['registry_path']),factory,limits(manifest),
        shutdown=shutdown,research_done=retired,endpoint_ready=bound,peer_ready=peer_ready,upstream_ready=started,
        admitted=admitted,service_seconds=manifest['policy']['service_seconds']))
    async def wait_event(event,seconds):
        waiter=asyncio.create_task(event.wait())
        try:
            done,_=await asyncio.wait((task,waiter),timeout=seconds,return_when=asyncio.FIRST_COMPLETED)
            if task in done and not event.is_set():await task;raise ValueError('session-early-exit')
            m.check(event.is_set(),'session-phase-deadline')
        finally:
            waiter.cancel();await asyncio.gather(waiter,return_exceptions=True)
    try:
        await wait_event(peer_ready,manifest['policy']['setup_seconds']);admitted.set()
        await wait_event(started,manifest['policy']['setup_seconds'])
        if mode=='session-operator-stop':shutdown.set()
        await wait_event(retired,manifest['policy']['research_seconds']+manifest['policy']['shutdown_seconds'])
        if mode in ('session-scanner-normal','session-native-normal'):
            event=c.strict_json(peer.event('create',10));event['mint']='1'*31+'3'
            peer.frames.put_nowait(c.canonical(event).encode())
            # Wait for delivery itself, not a timing rehearsal or arbitrary sleep.
            async with asyncio.timeout(manifest['policy']['shutdown_seconds']):
                while discovery_progress['frames_sent']<3:await asyncio.sleep(.005)
        shutdown.set()
        await asyncio.wait_for(asyncio.shield(task),manifest['policy']['shutdown_seconds'])
        m.check(attempts==1 and peer.closed,'session-owner-not-closed')
    finally:
        shutdown.set()
        if not task.done():
            task.cancel();await asyncio.gather(task,return_exceptions=True)
        s.Server=original


def run(manifest,mode,pipe_fd=-1,native_development=False):
    m.check(mode in MODES,'session-mode')
    validate_mode(manifest,mode)
    if mode in PIPE_MODES:
        m.check(type(pipe_fd) is int and pipe_fd>=3 and stat.S_ISFIFO(os.fstat(pipe_fd).st_mode),'scanner-pipe-required')
    else:m.check(pipe_fd==-1,'unexpected-scanner-pipe')
    # The parent claim has already consumed the attempt; session.run exclusively
    # creates its control directory. It never reopens an interrupted capture.
    asyncio.run(exercise(manifest,mode,pipe_fd,native_development))
    return expected_terminal(manifest,mode,replay=True)
