"""Reusable bounded shared session, library only; no provider/credential launcher.

The caller supplies a reviewed Wire factory and a discovery consumer. The only
executable entry point in this directory uses an in-memory protocol peer.
"""
import asyncio
import concurrent.futures
from dataclasses import asdict
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
    result = contract.pins()
    extra = [REPO/'r1-preservation/preserve.py', REPO/'scripts/r1-session-kali.sh']
    for path in sorted([*ROOT.iterdir(), *extra]):
        if path.suffix in ('.py', '.md', '.sh'):
            if path.is_symlink():
                raise CaptureError('session-source-link')
            result[str(path.relative_to(REPO))] = digest(path.read_bytes())
    return dict(sorted(result.items()))


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


async def run(control, ipc, factory, limits=Limits(), *, stop=None):
    """One consumed directory, one peer, one upstream, one capture, no restart.

    Cancellation/failure shuts down upstream and waits at most three seconds for
    the capture thread. An unjoined worker produces no completion receipt and
    requires the enclosing process supervisor to terminate the process. This
    library is not a process containment or production-handoff implementation.
    """
    validate_limits(limits)
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
    admission = {'schema_version': 1, 'kind': 'r1-session-candidate-v1',
                 'limits': asdict(limits), 'source_sha256': before,
                 'live_launch_authorized': False, 'production_handoff_verified': False,
                 'automatic_resume_allowed': False}

    async def reviewed_factory():
        wire = await factory()
        if type(wire) is not Wire:
            raise CaptureError('session-reviewed-wire-required')
        return wire

    def capture_worker():
        try:
            with Journal(control / 'session.jsonl') as journal:
                with Capture(control / 'capture', limits) as capture:
                    loop.call_soon_threadsafe(capture_ready.set)
                    lease = lease_input.result(timeout=10)
                    box['research'] = asyncio.run(shared_session.run(capture, lease, journal))
        except BaseException:
            box['failed'] = True  # never retain exception text or credentials
        finally:
            done.set()

    try:
        exclusive_file(control / 'admission.json', json_bytes(admission))
        owner = PreparedOwner(reviewed_factory)
        server = Server(owner, ipc)
        await server.start()
        await asyncio.wait_for(server.connected.wait(), 3)
        if owner.closed:
            raise CaptureError('session-peer-ended-before-start')
        worker = threading.Thread(target=capture_worker, name='r1-capture', daemon=True)
        worker.start()
        async with asyncio.timeout(3):
            while not capture_ready.is_set():
                if done.is_set():
                    raise CaptureError('session-capture-start-failed')
                await asyncio.sleep(0.005)
        await owner.start()
        lease = owner.attach(limits.seconds)
        lease_input.set_result(ReadyLease(lease, owner))
        async with asyncio.timeout(limits.seconds + 3):
            while not done.is_set():
                if stop is not None and stop.is_set():
                    owner.abort('operator-stop')
                await asyncio.sleep(0.01)
        worker.join(timeout=0)
        if worker.is_alive() or box.get('failed') or 'research' not in box:
            raise CaptureError('session-worker-incomplete')
        await owner.close()
        await server.close()
        resources_closed = True
        if owner.reason in ('abort-failed', 'close-failed'):
            raise CaptureError('session-upstream-close-unverified')
        if pins() != before:
            raise CaptureError('session-source-changed')
        receipt = {'schema_version': 1, 'kind': 'r1-session-stopped-v1',
                   'admission_sha256': digest(json_bytes(admission)),
                   'research': box['research'], 'owner': owner.receipt(),
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
                async with asyncio.timeout(3):
                    while worker.is_alive():
                        await asyncio.sleep(0.01)
                worker.join(timeout=0)
        finally:
            os.close(fd)
