"""Reusable bounded shared session, library only; no provider/credential launcher.

The caller supplies a reviewed Wire factory and a discovery consumer. The only
executable entry point in this directory uses an in-memory protocol peer.
"""
import asyncio
import concurrent.futures
from dataclasses import asdict
import common
import os
from pathlib import Path
import shutil
import threading
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO / 'r1-registration'))
import contract
from capture import Capture, CaptureError, Limits, canonical, digest, exclusive_file, lock, private_directory
from handoff import path_without_links
from measurement import Journal
from provider_wire import Wire
from shared_owner import Owner
from shared_discovery import Server
import shared_session
UNIX_SERVER = Server
SPACE_PREFLIGHT = 512 * 1024**2


def pins():
    return common.pins()


def json_bytes(row):
    return (canonical(row) + '\n').encode()


def validate_limits(limits):
    limits.validate()
    ceiling = asdict(Limits())
    for key, value in asdict(limits).items():
        # A smaller modulus increases selection. Allowed for offline validation;
        # recorded limits must still match any future approved pilot contract.
        if key != 'sample_modulus' and value > ceiling[key]:
            raise CaptureError('session-limit-exceeds-draft')


class PreparedOwner(Owner):
    """Buffer upstream until the capture journal has actually started."""
    def __init__(self, factory):
        super().__init__(factory)
        self.capture_ready = asyncio.Event()

    async def _read(self):
        await self.capture_ready.wait()
        await super()._read()


class ReadyLease:
    def __init__(self, lease, owner):
        self.lease, self.owner = lease, owner

    async def remote(self, operation, *args):
        result = await self.lease.remote(operation, *args)
        # shared_session writes Journal.start before its first heartbeat. Open
        # the read gate on the owner loop only after that heartbeat succeeds.
        if operation == 'heartbeat':
            self.lease.loop.call_soon_threadsafe(self.owner.capture_ready.set)
        return result


def read_retirement(control):
    return common.read_private(control/'research-retired.json',262144)


async def run(control, ipc, factory, limits=Limits(), *, shutdown, research_done,
              endpoint_ready, peer_ready, upstream_ready, admitted, service_seconds,
              setup_seconds=15, shutdown_seconds=3, server_factory=None):
    """One consumed directory, one peer, one upstream, one capture, no restart.

    Cancellation/failure shuts down upstream and waits at most three seconds for
    the capture thread. An unjoined worker produces no completion receipt and
    requires the enclosing process supervisor to terminate the process. This
    library is not a process containment or production-handoff implementation.
    """
    validate_limits(limits)
    if type(service_seconds) is not int or not limits.seconds <= service_seconds <= 172800:
        raise CaptureError("integration-service-duration")
    if any(type(v) is not int or not 1 <= v <= 30 for v in (setup_seconds, shutdown_seconds)):
        raise CaptureError('session-phase-budget')
    if shutdown.is_set():
        raise CaptureError('session-stopped-before-setup')
    control, ipc = map(path_without_links, (control, ipc))
    private_directory(control.parent)
    private_directory(ipc)
    if control == ipc or control in ipc.parents or ipc in control.parents:
        raise CaptureError('session-overlapping-directories')
    if shutil.disk_usage(control.parent).free < SPACE_PREFLIGHT:
        raise CaptureError('session-insufficient-space')
    before = pins()
    control.mkdir(mode=0o700)  # retained forever as this attempt's no-rearm claim
    fd = lock(control)
    owner = server = worker = None
    resources_closed = False
    lease_input = concurrent.futures.Future()
    done = threading.Event()
    box = {}
    loop = asyncio.get_running_loop()
    capture_ready = asyncio.Event()
    admission = {'schema_version': 1, 'kind': 'r1-separated-session-v1',
                 'limits': asdict(limits), 'service_seconds':service_seconds, 'source_sha256': before,
                 'live_launch_authorized': False, 'production_handoff_verified': False,
                 'automatic_resume_allowed': False}

    async def reviewed_factory():
        if shutdown.is_set() or owner.closed:
            raise CaptureError('session-stopped-before-connect')
        wire = await factory()
        if type(wire) is not Wire:
            raise CaptureError('session-reviewed-wire-required')
        return wire

    def capture_worker():
        try:
            with Journal(control / 'session.jsonl') as journal:
                with Capture(control / 'capture', limits) as capture:
                    loop.call_soon_threadsafe(capture_ready.set)
                    lease = lease_input.result(timeout=setup_seconds + shutdown_seconds)
                    box['research'] = asyncio.run(shared_session.run(capture, lease, journal))
        except BaseException:
            box['failed'] = True  # never retain exception text or credentials
        finally:
            done.set()

    try:
        exclusive_file(control / 'admission.json', json_bytes(admission))
        owner = PreparedOwner(reviewed_factory)
        server = (server_factory or Server)(owner, ipc)

        async def setup():
            nonlocal worker
            await server.start()
            endpoint_ready.set()
            await server.connected.wait()
            peer_ready.set()
            await admitted.wait()
            if owner.closed or shutdown.is_set():
                raise CaptureError('session-peer-ended-before-start')
            worker = threading.Thread(target=capture_worker, name='r1-capture', daemon=True)
            worker.start()
            while not capture_ready.is_set():
                if done.is_set():
                    raise CaptureError('session-capture-start-failed')
                await asyncio.sleep(0.005)
            await owner.start()
            if shutdown.is_set():
                raise CaptureError('session-stopped-during-setup')
            lease = owner.attach(limits.seconds)
            lease_input.set_result(ReadyLease(lease, owner))
            upstream_ready.set()

        # One deadline covers endpoint, peer, admission, capture and connection.
        # STOP interrupts every startup wait, including an in-flight factory.
        setup_task = asyncio.create_task(setup())
        stop_task = asyncio.create_task(shutdown.wait())
        try:
            completed, _ = await asyncio.wait((setup_task, stop_task), timeout=setup_seconds,
                                             return_when=asyncio.FIRST_COMPLETED)
            if shutdown.is_set():
                raise CaptureError('session-stopped-during-setup')
            if setup_task not in completed:
                raise CaptureError('session-setup-deadline')
            await setup_task
        finally:
            for task in (setup_task, stop_task):
                if not task.done(): task.cancel()
            await asyncio.gather(setup_task, stop_task, return_exceptions=True)
        service_deadline=loop.time()+service_seconds
        async with asyncio.timeout(limits.seconds + shutdown_seconds):
            while not done.is_set():
                if shutdown.is_set():
                    owner.abort('operator-stop')
                await asyncio.sleep(0.01)
        worker.join(timeout=0)
        if worker.is_alive() or box.get('failed') or 'research' not in box:
            raise CaptureError('session-worker-incomplete')
        retirement={'schema_version':1,'kind':'r1-research-retired-v1',
                    'admission_sha256':digest(json_bytes(admission)),
                    'research':box['research'],'owner':owner.receipt(),
                    'discovery_frames':server.progress['frames_sent'],
                    'research_cannot_rearm':owner.attached and not owner.lease.active,
                    'discovery_continues':not owner.closed,
                    'live_launch_authorized':False}
        if not retirement['research_cannot_rearm']:
            raise CaptureError('integration-research-still-active')
        exclusive_file(control/'research-retired.json',json_bytes(retirement))
        research_done.set()
        # Discovery has a separate finite lifetime. No research reattach/reconnect.
        while not owner.closed and not shutdown.is_set() and loop.time()<service_deadline:
            await asyncio.sleep(0.01)
        await owner.close()
        await server.close()
        resources_closed = True
        if owner.reason in ('abort-failed', 'close-failed'):
            raise CaptureError('session-upstream-close-unverified')
        if pins() != before:
            raise CaptureError('session-source-changed')
        receipt = {'schema_version': 1, 'kind': 'r1-separated-session-stopped-v1',
                   'admission_sha256': digest(json_bytes(admission)),
                   'research': box['research'], 'owner': owner.receipt(),
                   'retirement_sha256':digest(read_retirement(control)),
                   'discovery_frames': server.progress['frames_sent'],
                   'capture_thread_joined': True, 'local_upstream_closed': True,
                   'peer_uid_verified': server.accepted and type(server) is UNIX_SERVER,
                   'provider_acknowledgement_verified': False, 'billing_cutoff_verified': False,
                   'live_launch_authorized': False, 'production_handoff_verified': False}
        exclusive_file(control / 'stopped.json', json_bytes(receipt))
        return receipt
    finally:
        # No completed marker is written on startup failure, cancellation,
        # incomplete worker shutdown, source drift or failed receipt durability.
        if not lease_input.done():
            lease_input.set_exception(CaptureError('session-start-abandoned'))
        try:
            if owner is not None and not resources_closed:
                await owner.close()
            if server is not None and not resources_closed:
                await server.close()
            if worker is not None:
                async with asyncio.timeout(shutdown_seconds):
                    while worker.is_alive():
                        await asyncio.sleep(0.01)
                worker.join(timeout=0)
        finally:
            os.close(fd)
