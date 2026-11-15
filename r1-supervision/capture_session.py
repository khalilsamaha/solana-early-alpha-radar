"""Existing capture/session library under manifest limits; fixed offline peers only."""
import asyncio
from dataclasses import asdict
from datetime import datetime
import os
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
m=r.m;p=r.preparation
MODES={'session-normal','session-cleanup-failure','session-operator-stop'}
FILES=('admission.json','research-retired.json','stopped.json','session.jsonl','capture/ticks.db')


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
        expected_cleanup='unsubscribed' if mode=='session-normal' else 'upstream-aborted'
        m.check(retired['research']['cleanup']['outcome']==expected_cleanup
                and retired['discovery_continues'] is (mode=='session-normal')
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
        return {'kind':'manifest-supervised-capture-fixture','mode':mode,
                'storage_gate_sha256':m.digest(gate_bytes),
                'artifact_sha256':{name:m.digest(value) for name,value in data.items()},
                'research_cleanup':expected_cleanup,'discovery_continued_after_retirement':retired['discovery_continues'],
                'capture_thread_joined':True,'local_upstream_closed':True,
                'synthetic_upstream_attempts':1,'research_attachments':1,
                'transport':'in-process-fixture','peer_uid_verified':False,
                'provider_connection_opened':False,'real_credential_used':False,'activation_authorized':False}
    finally:os.close(fd)


async def exercise(manifest,mode):
    selected=mode.removeprefix('session-');peer=fixtures.Peer(selected,4)
    shutdown,retired,bound,peer_ready,started,admitted=(asyncio.Event() for _ in range(6))
    attempts=0
    async def factory():
        nonlocal attempts
        attempts+=1;peer.frames.put_nowait(peer.event('create'))
        return Wire(peer,secret_variants(fixtures.SECRET))
    original=s.Server;s.Server=fixtures.TestServer
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
        shutdown.set()
        await asyncio.wait_for(asyncio.shield(task),manifest['policy']['shutdown_seconds'])
        m.check(attempts==1 and peer.closed,'session-owner-not-closed')
    finally:
        shutdown.set()
        if not task.done():
            task.cancel();await asyncio.gather(task,return_exceptions=True)
        s.Server=original


def run(manifest,mode):
    m.check(mode in MODES,'session-mode')
    # The parent claim has already consumed the attempt; session.run exclusively
    # creates its control directory. It never reopens an interrupted capture.
    asyncio.run(exercise(manifest,mode))
    return expected_terminal(manifest,mode,replay=True)
