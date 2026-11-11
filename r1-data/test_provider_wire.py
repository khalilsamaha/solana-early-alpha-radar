import asyncio
import contextlib
import json
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import quote

from websockets.server import ServerProtocol
from websockets.http11 import Request
from websockets.frames import Frame, Opcode
from http import HTTPStatus

import provider_wire as w
from capture import Capture, Limits, verify
from test_capture import frame
from transport import run_session

SECRET = 'synthetic/test"credential-value'


class Connection:
    def __init__(self, parts=()):
        self.parts = parts; self.sent = []; self.aborts = 0; self.transport = self
    def abort(self): self.aborts += 1
    async def wait_closed(self): pass
    async def send(self, payload): self.sent.append(payload)
    async def recv_streaming(self, *, decode):
        for part in self.parts:
            if isinstance(part, Exception): raise part
            yield part


class WireTests(unittest.IsolatedAsyncioTestCase):
    def wire(self, parts=()):
        connection = Connection(parts)
        return w.Wire(connection, w.secret_variants(SECRET)), connection

    async def test_fixed_tls_endpoint_queue_limits_no_proxy_compression_or_logs(self):
        captured = {}
        async def connector(uri, **kw):
            captured.update(uri=uri, **kw)
            return Connection()
        wire = await w._open(SECRET, connector)
        try:
            self.assertEqual(captured['uri'], w.ENDPOINT+'?api-key='+quote(SECRET, safe=''))
            self.assertIs(captured['proxy'], None); self.assertIs(captured['compression'], None)
            self.assertTrue(captured['ssl'].check_hostname)
            self.assertEqual(captured['ssl'].verify_mode, ssl.CERT_REQUIRED)
            self.assertEqual(captured['max_size'], 65536)
            self.assertEqual(captured['max_queue'], (2,1))
            self.assertEqual(captured['write_limit'], 4096)
            self.assertEqual(captured['open_timeout'], 3)
            self.assertEqual(captured['close_timeout'], 0.5)
            self.assertTrue(captured['logger'].disabled)
            self.assertFalse(captured['logger'].propagate)
            self.assertNotIn(SECRET, repr(wire))
        finally: await wire.close()

    async def test_invalid_secret_version_and_tls_fail_before_connector(self):
        connector = AsyncMock()
        for secret in ('short', 'x'*4097, 'x'*20+'\n', 'é'*20):
            with self.assertRaises(w.CaptureError): await w._open(secret, connector)
        with patch.object(w.websockets, '__version__', '16.0'):
            with self.assertRaises(w.CaptureError): await w._open(SECRET, connector)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT); context.check_hostname = False
        with patch.object(w.ssl, 'create_default_context', return_value=context):
            with self.assertRaises(w.CaptureError): await w._open(SECRET, connector)
        connector.assert_not_called()

    async def test_factory_constructs_without_io_and_never_retries_after_failure(self):
        with patch.object(w, '_open', new=AsyncMock(side_effect=w.CaptureError('failed'))) as opened:
            factory = w.provider_factory(SECRET)
            opened.assert_not_called()
            with self.assertRaises(w.CaptureError): await factory()
            with self.assertRaises(w.CaptureError): await factory()
            self.assertEqual(opened.await_count, 1)

    async def test_connection_exception_never_exposes_url_key_or_provider_body(self):
        async def connector(*args, **kw): raise RuntimeError(SECRET+' SENSITIVE-PROVIDER')
        with self.assertRaises(w.CaptureError) as cm: await w._open(SECRET, connector)
        self.assertEqual(str(cm.exception), 'wire-connect-failed')

    async def test_outgoing_methods_keys_and_command_budget(self):
        wire, connection = self.wire()
        try:
            for row in ({'method':'subscribeNewToken'}, {'method':'subscribeMigration'},
                        {'method':'subscribeTokenTrade','keys':['1'*31+'2']},
                        {'method':'unsubscribeTokenTrade','keys':['1'*31+'2']}):
                await wire.send(json.dumps(row))
            self.assertEqual(len(connection.sent), 4)
            wire._commands = w.MAX_COMMANDS
            with self.assertRaises(w.CaptureError): await wire.send('{"method":"subscribeNewToken"}')
            self.assertEqual(len(connection.sent), 4)
        finally: await wire.close()

    async def test_forbidden_commands_extra_fields_invalid_keys_and_duplicates_stop(self):
        for row in ({'method':'trade'}, {'method':'subscribeAccountTrade','keys':['1'*32]},
                    {'method':'subscribeNewToken','api-key':SECRET},
                    {'method':'subscribeTokenTrade','keys':[]},
                    {'method':'subscribeTokenTrade','keys':['bad']},
                    {'method':'subscribeTokenTrade','keys':['1'*32]*2}):
            wire, connection = self.wire()
            try:
                with self.assertRaises(w.CaptureError): await wire.send(json.dumps(row))
                self.assertEqual(connection.sent, [])
                self.assertGreater(connection.aborts, 0)
            finally: await wire.close()

    async def test_send_cancellation_aborts_before_any_further_command(self):
        wire, connection = self.wire()
        entered = asyncio.Event()
        async def hang(payload): entered.set(); await asyncio.Future()
        connection.send = hang
        task = asyncio.create_task(wire.send('{"method":"subscribeNewToken"}'))
        await entered.wait(); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertGreater(connection.aborts, 0)
        with self.assertRaises(w.CaptureError): await wire.send('{"method":"subscribeMigration"}')
        await wire.close()

    async def test_receive_byte_fragment_and_secret_bounds_fail_without_payload(self):
        variants = [(b'x'*(w.FRAME_BYTES+1),), tuple(b'' for _ in range(w.MAX_FRAGMENTS+1))]
        variants += [(secret[:5], secret[5:]) for secret in w.secret_variants(SECRET)]
        variants += [(RuntimeError('SENSITIVE-PROVIDER'),)]
        for parts in variants:
            wire, connection = self.wire(parts)
            try:
                with self.assertRaises(w.CaptureError) as cm: await wire.recv()
                self.assertEqual(str(cm.exception), 'wire-receive-failed')
                self.assertGreater(connection.aborts, 0)
            finally: await wire.close()

    async def test_fragment_stall_aborts_and_records_no_partial_message(self):
        wire, connection = self.wire()
        async def stall(**kw):
            yield b'{'
            await asyncio.Future()
        connection.recv_streaming = stall
        with patch.object(w, 'FRAGMENT_SECONDS', 0.01):
            with self.assertRaises(w.CaptureError): await wire.recv()
        self.assertGreater(connection.aborts, 0)
        await wire.close()

    async def test_abort_cancels_silent_reader_and_collects_task(self):
        wire, connection = self.wire()
        async def silence(**kw):
            await asyncio.Future()
            yield b'never'
        connection.recv_streaming = silence
        with self.assertRaises(TimeoutError): await asyncio.wait_for(wire.recv(), 0.01)
        self.assertIsNotNone(wire._pending)
        await wire.close()
        self.assertIsNone(wire._pending)
        with self.assertRaises(w.CaptureError): await wire.recv()


class Peer(asyncio.Transport):
    """Real RFC6455 codecs on both sides; only socket/TLS transport is in memory."""
    def __init__(self, *, redirect=False):
        self.protocol = ServerProtocol(logger=w.silent_logger())
        self.loop = asyncio.get_running_loop()
        self.client = None
        self.events = asyncio.Queue()
        self.requests = []
        self.queue = []
        self.paused = False
        self.closed = False
        self.redirect = redirect
        self.opens = 0
        self.kwargs = None

    async def open(self, factory, **kwargs):
        self.opens += 1
        self.kwargs = kwargs
        self.client = factory()
        self.client.connection_made(self)
        return self, self.client

    def write(self, data):
        self.protocol.receive_data(data)
        for event in self.protocol.events_received():
            if isinstance(event, Request):
                self.requests.append(event)
                if self.redirect:
                    response = self.protocol.reject(HTTPStatus.FOUND, 'SENSITIVE-PROVIDER')
                    response.headers['Location'] = '/another?api-key=SENSITIVE'
                else:
                    response = self.protocol.accept(event)
                self.protocol.send_response(response)
            elif isinstance(event, Frame):
                self.events.put_nowait(event)
        self.flush()

    def flush(self):
        self.queue.extend(self.protocol.data_to_send())
        self.loop.call_soon(self.drain)

    def drain(self):
        if self.closed or self.paused or not self.queue: return
        data = self.queue.pop(0)
        if data: self.client.data_received(data)
        else: self.abort()
        self.loop.call_soon(self.drain)

    def emit(self, method, *args, **kwargs):
        getattr(self.protocol, method)(*args, **kwargs)
        self.flush()

    def abort(self):
        if not self.closed:
            self.closed = True
            self.loop.call_soon(self.client.connection_lost, None)
    close = abort
    def is_closing(self): return self.closed
    def set_write_buffer_limits(self, *args): pass
    def get_write_buffer_size(self): return 0
    def get_extra_info(self, name, default=None): return default
    def pause_reading(self): self.paused = True
    def resume_reading(self): self.paused = False; self.loop.call_soon(self.drain)
    def can_write_eof(self): return False


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()

    async def open_wire(self, peer):
        with patch.object(asyncio.get_running_loop(), 'create_connection', side_effect=peer.open):
            return await w._open(SECRET)

    async def test_real_protocol_fragmented_message_survives_poll_timeout_once(self):
        peer = Peer(); wire = await self.open_wire(peer)
        try:
            peer.emit('send_text', b'{"value":', fin=False)
            with self.assertRaises(TimeoutError): await asyncio.wait_for(wire.recv(), 0.01)
            pending = wire._pending
            peer.emit('send_continuation', b'1}', fin=True)
            peer.emit('send_text', b'{"value":2}')
            self.assertEqual(await asyncio.wait_for(wire.recv(), 1), b'{"value":1}')
            self.assertTrue(pending.done())
            self.assertEqual(await wire.recv(), b'{"value":2}')
            self.assertEqual(peer.opens, 1)
            self.assertEqual(peer.kwargs['host'], 'pumpportal.fun')
            self.assertEqual(peer.kwargs['port'], 443)
            self.assertEqual(peer.kwargs['server_hostname'], 'pumpportal.fun')
        finally: await wire.close()

    async def test_real_protocol_ping_pong_does_not_become_capture_data(self):
        peer = Peer(); wire = await self.open_wire(peer)
        try:
            peer.emit('send_ping', b'health')
            peer.emit('send_text', b'{}')
            self.assertEqual(await asyncio.wait_for(wire.recv(), 1), b'{}')
            event = await asyncio.wait_for(peer.events.get(), 1)
            self.assertEqual(event.opcode, Opcode.PONG)
            self.assertEqual(event.data, b'health')
        finally: await wire.close()

    async def test_real_protocol_oversized_message_and_fragment_flood_close(self):
        for mode in ('size', 'fragments'):
            peer = Peer(); wire = await self.open_wire(peer)
            try:
                if mode == 'size': peer.emit('send_binary', b'x'*(w.FRAME_BYTES+1))
                else:
                    peer.emit('send_text', b'', fin=False)
                    for _ in range(w.MAX_FRAGMENTS): peer.emit('send_continuation', b'', fin=False)
                    peer.emit('send_continuation', b'', fin=True)
                with self.assertRaises(w.CaptureError): await asyncio.wait_for(wire.recv(), 1)
            finally: await wire.close()

    async def test_real_protocol_redirect_is_not_followed_and_error_sanitized(self):
        peer = Peer(redirect=True)
        with self.assertRaises(w.CaptureError) as cm: await self.open_wire(peer)
        self.assertEqual(str(cm.exception), 'wire-connect-failed')
        self.assertEqual(len(peer.requests), 1)
        self.assertEqual(peer.opens, 1)
        self.assertTrue(peer.closed)

    async def test_real_protocol_capture_terminal_limit_closes_without_reconnect(self):
        peer = Peer(); ready = asyncio.Event(); commands = []
        async def factory():
            wire = await self.open_wire(peer)
            ready.set()
            return wire
        with Capture(self.root/'capture', Limits(messages=2, sample_modulus=1)) as capture:
            session = asyncio.create_task(run_session(capture, factory))
            try:
                await asyncio.wait_for(ready.wait(), 1)
                for _ in range(2):
                    event = await asyncio.wait_for(peer.events.get(), 1)
                    self.assertEqual(event.opcode, Opcode.TEXT)
                    commands.append(json.loads(event.data))
                peer.emit('send_text', frame())
                commands.append(json.loads((await asyncio.wait_for(peer.events.get(), 1)).data))
                peer.emit('send_text', frame('buy'))
                result = await asyncio.wait_for(session, 1)
            finally:
                if not session.done():
                    session.cancel()
                    with contextlib.suppress(asyncio.CancelledError): await session
        evidence = verify(self.root/'capture')
        self.assertEqual(peer.opens, 1)
        self.assertTrue(peer.closed)
        self.assertEqual([c['method'] for c in commands], ['subscribeNewToken','subscribeMigration','subscribeTokenTrade'])
        self.assertEqual(result['outcome'], 'capture-stopped')
        self.assertEqual(evidence['messages'], 2)
        self.assertEqual(evidence['raw_rows'], 2)
        self.assertEqual(evidence['stop_reason'], 'message-limit')
        self.assertFalse(result['provider_billing_verified'])

    async def test_real_protocol_disconnect_records_gap_without_close_reason_leak(self):
        peer = Peer(); ready = asyncio.Event()
        async def factory():
            wire = await self.open_wire(peer)
            ready.set()
            return wire
        with Capture(self.root/'capture', Limits(sample_modulus=1)) as capture:
            session = asyncio.create_task(run_session(capture, factory))
            try:
                await asyncio.wait_for(ready.wait(), 1)
                for _ in range(2): await asyncio.wait_for(peer.events.get(), 1)
                peer.emit('send_text', frame())
                await asyncio.wait_for(peer.events.get(), 1)
                peer.emit('send_close', 1011, 'SENSITIVE-PROVIDER')
                result = await asyncio.wait_for(session, 1)
            finally:
                if not session.done():
                    session.cancel()
                    with contextlib.suppress(asyncio.CancelledError): await session
        evidence = verify(self.root/'capture')
        self.assertEqual(evidence['stop_reason'], 'transport-gap')
        self.assertEqual(evidence['gaps'], 1)
        self.assertEqual(peer.opens, 1)
        self.assertEqual(result['outcome'], 'transport-failed')
        self.assertNotIn('SENSITIVE', str(result))
        self.assertNotIn(b'SENSITIVE', (self.root/'capture/ticks.db').read_bytes())
