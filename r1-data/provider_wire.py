"""Bounded PumpPortal wire. Library only: no launcher or credential-file reader.

Creating the factory performs no I/O. Calling it opens one provider connection;
that call is reserved for a separately accepted launch/coexistence decision.
Offline tests inject in-memory protocol peers, never a provider or funded key.
"""
import asyncio
import json
import logging
import ssl
from urllib.parse import quote

import websockets
from websockets.asyncio.client import connect

from capture import CaptureError, canonical, strict_json
from rpc_probe import identifier

VERSION = "17.4"
ENDPOINT = "wss://pumpportal.fun/api/data"
FRAME_BYTES = 65536
MAX_FRAGMENTS = 64
FRAGMENT_SECONDS = 2.0
MAX_COMMANDS = 1024


def dependency():
    if websockets.__version__ != VERSION:
        raise CaptureError("wire-dependency-version")
    return {"websockets": VERSION}


def silent_logger():
    logger = logging.Logger("r1-wire-silent")
    logger.disabled = True
    logger.propagate = False
    logger.addHandler(logging.NullHandler())
    return logger


class NoRedirect(connect):
    def process_redirect(self, exc):
        return exc


def secret_variants(secret):
    if (not isinstance(secret, str) or not 16 <= len(secret) <= 4096
            or any(not 33 <= ord(char) <= 126 for char in secret)):
        raise CaptureError("invalid-provider-credential")
    return tuple(s.encode() for s in {secret, quote(secret, safe=""), json.dumps(secret)[1:-1]})


class Wire:
    def __init__(self, connection, variants):
        self._connection = connection
        self._variants = variants
        self._pending = None
        self._closed = False
        self._receiving = False
        self._sending = False
        self._commands = 0

    def __repr__(self):
        return "<R1 provider wire>"

    def abort(self):
        self._closed = True
        if self._pending is not None and not self._pending.done():
            self._pending.cancel()
        self._connection.transport.abort()

    async def close(self):
        self.abort()
        if self._pending is not None:
            await asyncio.gather(self._pending, return_exceptions=True)
            self._pending = None
        try:
            await asyncio.wait_for(self._connection.wait_closed(), 0.5)
        except Exception:
            raise CaptureError("wire-close-failed") from None

    def _check_secret(self, raw):
        if any(value in raw for value in self._variants):
            raise CaptureError("credential-in-wire-data")

    async def send(self, payload):
        try:
            if self._closed or self._sending or self._commands >= MAX_COMMANDS:
                raise CaptureError("wire-send-state")
            if not isinstance(payload, str) or len(payload.encode()) > 4096:
                raise CaptureError("wire-command-size")
            raw = payload.encode(); self._check_secret(raw)
            row = strict_json(raw)
            method = row.get("method")
            if method in ("subscribeNewToken", "subscribeMigration"):
                if set(row) != {"method"}: raise CaptureError("wire-command-keys")
            elif method in ("subscribeTokenTrade", "unsubscribeTokenTrade"):
                keys = row.get("keys")
                if (set(row) != {"method", "keys"} or not isinstance(keys, list)
                        or not 1 <= len(keys) <= 32 or any(not identifier(k, 32) for k in keys)
                        or len(set(keys)) != len(keys)):
                    raise CaptureError("wire-command-keys")
            else:
                raise CaptureError("wire-command-forbidden")
            self._sending = True
            self._commands += 1
            await asyncio.wait_for(self._connection.send(canonical(row)), 1.0)
        except asyncio.CancelledError:
            self.abort()
            raise
        except Exception:
            self.abort()
            raise CaptureError("wire-send-failed") from None
        finally:
            self._sending = False

    async def _read_message(self):
        # Streaming avoids unbounded fragment accumulation. A single reader task
        # survives polling cancellation so a partial message is never restarted.
        stream = self._connection.recv_streaming(decode=False)
        data = bytearray()
        count = 0
        def add(fragment):
            nonlocal count
            count += 1
            if (type(fragment) is not bytes or count > MAX_FRAGMENTS
                    or len(data)+len(fragment) > FRAME_BYTES):
                raise CaptureError("wire-message-bound")
            data.extend(fragment)
        try:
            add(await anext(stream))
            async with asyncio.timeout(FRAGMENT_SECONDS):
                async for fragment in stream:
                    add(fragment)
            raw = bytes(data)
            self._check_secret(raw)
            return raw
        except asyncio.CancelledError:
            raise
        except Exception:
            self._closed = True
            self._connection.transport.abort()
            raise CaptureError("wire-receive-failed") from None
        finally:
            await stream.aclose()

    async def recv(self):
        if self._closed or self._receiving:
            raise CaptureError("wire-receive-state")
        self._receiving = True
        try:
            if self._pending is None:
                self._pending = asyncio.create_task(self._read_message())
            raw = await asyncio.shield(self._pending)
            self._pending = None
            return raw
        finally:
            self._receiving = False


async def _open(secret, connector=NoRedirect):
    dependency()
    variants = secret_variants(secret)
    context = ssl.create_default_context()
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise CaptureError("wire-tls-verification")
    try:
        connection = await asyncio.wait_for(connector(
            ENDPOINT+"?api-key="+quote(secret, safe=""),
            ssl=context, proxy=None, compression=None, open_timeout=3,
            close_timeout=0.5, ping_interval=20, ping_timeout=10,
            max_size=FRAME_BYTES, max_queue=(2, 1), write_limit=4096,
            user_agent_header=None, logger=silent_logger()), 3.5)
        return Wire(connection, variants)
    except asyncio.CancelledError:
        raise
    except Exception:
        raise CaptureError("wire-connect-failed") from None


def provider_factory(secret):
    """One attempted connection per factory; no CLI or readiness bypass flag."""
    dependency()
    secret_variants(secret)
    attempted = False
    async def factory():
        nonlocal attempted
        if attempted: raise CaptureError("wire-reconnect-forbidden")
        attempted = True
        return await _open(secret)
    return factory
