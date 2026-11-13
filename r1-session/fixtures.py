"""Offline peers for candidate-session acceptance; no provider factory import."""
import asyncio
from pathlib import Path
import shutil
import tempfile
from contextlib import nullcontext
from unittest.mock import patch

import session as s
from capture import CaptureError, Limits, canonical, strict_json
from provider_wire import Wire, secret_variants
from supervisor import ENVIRONMENT

SECRET = 'R1-SYNTHETIC-SESSION-CREDENTIAL'
MODES = ('normal', 'cleanup-failure', 'send-failure', 'provider-failure', 'operator-stop', 'idle', 'watch-expiry')


def validate_node(row):
    # Every Node scenario sends one creation. EOF is the expected final gap,
    # but a clean process exit must not hide a dropped discovery event.
    expected = {'tokens': 1, 'creations': 1, 'discovery_gaps': 1, 'upstream_connections_opened': 0}
    if any(type(row.get(k)) is not int or row[k] != value for k, value in expected.items()):
        raise CaptureError('session-fixture-node-boundary')


class Peer:
    def __init__(self, mode, messages):
        self.mode, self.messages = mode, messages
        self.frames = asyncio.Queue()
        self.sent = []
        self.closed = False
        self.transport = self

    def event(self, kind, index=0):
        return canonical({'txType': kind, 'mint': '1'*31+'2', 'signature': '2'*88,
                          'initialBuy': 0, 'fixture_sequence': index}).encode()

    def abort(self):
        self.closed = True

    async def wait_closed(self):
        pass

    async def send(self, raw):
        row = strict_json(raw.encode())
        self.sent.append(row)
        if row['method'] == 'subscribeTokenTrade':
            if self.mode == 'send-failure':
                raise RuntimeError(SECRET)
            if self.mode == 'provider-failure':
                self.frames.put_nowait(canonical({'error': SECRET}).encode())
            elif self.mode == 'watch-expiry':
                self.frames.put_nowait(self.event('buy', 1))
            elif self.mode not in ('operator-stop', 'idle'):
                for n in range(self.messages - 1):
                    self.frames.put_nowait(self.event('buy' if n % 2 == 0 else 'sell', n+1))
        if row['method'] == 'unsubscribeTokenTrade' and self.mode == 'cleanup-failure':
            raise RuntimeError(SECRET)
        if row['method'] == 'unsubscribeTokenTrade' and self.mode == 'watch-expiry':
            for index in (2, 3):
                self.frames.put_nowait(self.event('buy', index))

    async def recv_streaming(self, decode=False):
        yield await self.frames.get()


class TestServer:
    """Unit-test endpoint only; receipts explicitly deny peer UID verification."""
    def __init__(self, owner, directory):
        self.owner, self.directory = owner, directory
        self.path = directory/'discovery.sock'
        self.connected = asyncio.Event()
        self.accepted = False
        self.progress = {'frames_sent': 0}
        self.task = None

    async def start(self):
        self.accepted = True
        self.connected.set()
        async def drain():
            try:
                while True:
                    await self.owner.discovery.recv()
                    self.progress['frames_sent'] += 1
            except CaptureError:
                pass
        self.task = asyncio.create_task(drain())

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)


async def exercise(root, mode='normal', messages=4, *, node=False, simulated=True):
    if mode not in MODES:
        raise CaptureError('session-fixture-mode')
    root = Path(root); root.mkdir(mode=0o700)
    peer = Peer(mode, messages)
    attempts = 0
    stop = asyncio.Event()
    async def factory():
        nonlocal attempts
        attempts += 1
        # Deliberately queue the first event before Owner.start returns. The
        # production-shaped coordinator, not a delayed fixture, must retain it.
        if mode != 'idle':
            peer.frames.put_nowait(peer.event('create'))
        return Wire(peer, secret_variants(SECRET))
    async def consume(reader):
        frames = []
        while True:
            raw = await reader.readline()
            if not raw:
                return frames
            if len(raw) > 66000 or len(frames) >= 64:
                raise CaptureError('session-fixture-consumer-bound')
            row = strict_json(raw)
            if row['seq'] != len(frames)+1:
                raise CaptureError('session-fixture-sequence')
            frames.append(row)
    worker = consumer = child = writer = None
    if simulated and node:
        raise CaptureError('session-fixture-node-requires-unix')
    with tempfile.TemporaryDirectory(prefix='r1-ipc-') as tmp, (patch.object(s, 'Server', TestServer) if simulated else nullcontext()):
        ipc = Path(tmp)
        try:
            worker = asyncio.create_task(s.run(root/'control', ipc, factory,
                Limits(messages=messages, seconds=1 if mode == 'idle' else 3,
                       sample_modulus=1, watch_seconds=1 if mode == 'watch-expiry' else 600), stop=stop))
            if not simulated:
                async with asyncio.timeout(3):
                    while not (ipc/'discovery.sock').exists():
                        if worker.done():
                            await worker
                        await asyncio.sleep(0.002)
            if simulated:
                pass
            elif node:
                executable = shutil.which('node')
                if not executable:
                    raise CaptureError('session-fixture-node-required')
                child = await asyncio.create_subprocess_exec(executable,
                    str(s.REPO/'r1-data/shared_scanner_fixture.mjs'), 'unix', str(ipc/'discovery.sock'),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    stdin=asyncio.subprocess.DEVNULL, env=ENVIRONMENT, limit=8192)
                if await asyncio.wait_for(child.stdout.readline(), 3) != b'ready\n':
                    raise CaptureError('session-fixture-node-start')
            else:
                reader, writer = await asyncio.open_unix_connection(str(ipc/'discovery.sock'), limit=66001)
                consumer = asyncio.create_task(consume(reader))
            if mode == 'operator-stop':
                async with asyncio.timeout(2):
                    while len(peer.sent) < 3:
                        await asyncio.sleep(0.002)
                stop.set()
            receipt = await asyncio.wait_for(asyncio.shield(worker), 8)
            if simulated:
                discovery = {'frames': receipt['discovery_frames'], 'sequence_verified': False}
            elif node:
                raw = await asyncio.wait_for(child.stdout.read(8193), 3)
                await asyncio.wait_for(child.wait(), 2)
                if len(raw) > 8192 or child.returncode:
                    raise CaptureError('session-fixture-node-result')
                discovery = strict_json(raw)
                validate_node(discovery)
            else:
                frames = await asyncio.wait_for(consumer, 2)
                discovery = {'frames': len(frames), 'sequence_verified': True}
            if attempts != 1 or not peer.closed:
                raise CaptureError('session-fixture-owner-boundary')
            return {'receipt': receipt, 'discovery': discovery, 'upstream_attempts': attempts,
                    'in_memory_upstream': True, 'real_unix_ipc': not simulated,
                    'node_adapter_exercised': node, 'provider_connection_opened': False}
        finally:
            if worker and not worker.done():
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
            if consumer:
                consumer.cancel()
                await asyncio.gather(consumer, return_exceptions=True)
            if writer:
                writer.close()
                await writer.wait_closed()
            if child and child.returncode is None:
                child.kill()
                await child.wait()
