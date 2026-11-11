"""One upstream, bounded discovery dispatch and one non-renewable research lease.

Library only. The caller supplies an already reviewed wire factory. This is not
a host/IP lock, credential loader, billing cap or live-launch authorization.
All owner methods run on one event loop; capture work belongs on another thread
or process so its synchronous SQLite/fsync work cannot block dispatch.
"""
import asyncio

from capture import CaptureError, canonical, strict_json
from measurement import command_valid
from rpc_probe import identifier

DISCOVERY_FIELDS = frozenset(("txType", "mint", "signature", "name", "symbol",
    "creator", "traderPublicKey", "bondingCurveKey", "slot", "decimals",
    "initialBuy", "solAmount", "vSolInBondingCurve", "vTokensInBondingCurve",
    "marketCapSol", "uri"))


class Channel:
    def __init__(self, frames=64, byte_limit=1024 * 1024):
        self.queue = asyncio.Queue(maxsize=frames)
        self.byte_limit, self.size, self.closed = byte_limit, 0, False

    def offer(self, raw):
        if self.closed or self.queue.full() or self.size + len(raw) > self.byte_limit:
            raise CaptureError("shared-queue-full")
        self.queue.put_nowait(raw)
        self.size += len(raw)

    async def recv(self):
        raw = await self.queue.get()
        if raw is None:
            self.queue.put_nowait(None)  # every later waiter sees termination
            raise CaptureError("shared-channel-closed")
        self.size -= len(raw)
        return raw

    def close(self):
        if self.closed:
            return
        self.closed = True
        while not self.queue.empty():
            self.queue.get_nowait()
        self.size = 0
        self.queue.put_nowait(None)


class Lease:
    def __init__(self, owner, seconds):
        self.owner, self.loop = owner, asyncio.get_running_loop()
        self.channel = Channel()
        self.active, self.reason, self.cleanup = True, None, None
        self.until = self.loop.time() + seconds
        self.timer = self.loop.call_later(seconds, self.revoke, "deadline")
        self.retirement = None
        self.heartbeat_timer = self.loop.call_later(2.0, self.revoke, "worker-unresponsive")

    def revoke(self, reason="research-stop"):
        if self.retirement is None:
            self.active, self.reason = False, reason
            self.timer.cancel()
            self.heartbeat_timer.cancel()
            self.channel.close()
            self.retirement = asyncio.create_task(self.owner._retire(self))
        return self.retirement

    async def heartbeat(self):
        if not self.active or self.loop.time() >= self.until:
            raise CaptureError("shared-lease-ended")
        self.heartbeat_timer.cancel()
        self.heartbeat_timer = self.loop.call_later(2.0, self.revoke, "worker-unresponsive")

    async def send(self, payload):
        await self.owner.trade(self, payload)

    async def recv(self):
        if not self.active:
            raise CaptureError("shared-lease-ended")
        raw = await self.channel.recv()
        if not self.active:
            raise CaptureError("shared-lease-ended")
        return raw

    async def finish(self):
        return await asyncio.shield(self.revoke())

    async def remote(self, operation, *args):
        """Bridge from the separate capture thread; no socket or new upstream."""
        if operation not in {"send", "recv", "finish", "heartbeat"}:
            raise CaptureError("shared-operation")
        if asyncio.get_running_loop() is self.loop:
            raise CaptureError("shared-capture-must-be-isolated")
        future = asyncio.run_coroutine_threadsafe(getattr(self, operation)(*args), self.loop)
        return await asyncio.wrap_future(future)


class Owner:
    def __init__(self, factory):
        self.factory, self.wire = factory, None
        self.attempted = self.closed = self.attached = False
        self.lease, self.reader = None, None
        self.discovery = Channel()
        self.lock = asyncio.Lock()
        self.watches = set()
        self.commands = []
        self.reason = None
        self.sequence = 0
        self.next_send = 0.0

    async def start(self):
        if self.attempted:
            raise CaptureError("shared-reconnect-forbidden")
        self.attempted = True
        try:
            self.wire = await asyncio.wait_for(self.factory(), 5)
            async with self.lock:
                await self._send({"method": "subscribeNewToken"})
                await self._send({"method": "subscribeMigration"})
            self.reader = asyncio.create_task(self._read())
        except BaseException:
            self.abort("start-failed")
            raise CaptureError("shared-start-failed") from None

    def attach(self, seconds):
        if (self.closed or self.wire is None or self.attached or type(seconds) not in (int, float)
                or not 0.01 <= seconds <= 172800):
            raise CaptureError("shared-attachment-refused")
        self.attached = True  # never reset by detach, restart or expiry
        self.lease = Lease(self, seconds)
        return self.lease

    async def _send(self, payload, lease=None, cleanup=False):
        await asyncio.sleep(max(0, self.next_send - asyncio.get_running_loop().time()))
        if self.closed or len(self.commands) >= (1024 if cleanup else 1023):
            raise CaptureError("shared-command-limit-or-closed")
        if lease is not None and (not lease.active or asyncio.get_running_loop().time() >= lease.until):
            lease.revoke("deadline")
            raise CaptureError("shared-lease-ended")
        row = {"command": payload, "state": "attempted", "cleanup": cleanup}
        self.commands.append(row)
        if payload["method"] == "subscribeTokenTrade":
            self.watches.update(payload["keys"])  # possibly accepted even if send fails
        try:
            await asyncio.wait_for(self.wire.send(canonical(payload)), 0.5)
            row["state"] = "completed"
            if payload["method"] == "unsubscribeTokenTrade":
                self.watches.difference_update(payload["keys"])
        except BaseException:
            row["state"] = "uncertain"
            self.abort("send-uncertain")
            raise CaptureError("shared-send-failed") from None
        finally:
            self.next_send = asyncio.get_running_loop().time() + 0.01

    async def trade(self, lease, raw):
        try:
            if type(raw) is not str or len(raw.encode()) > 4096:
                raise CaptureError("shared-command-size")
            payload = strict_json(raw.encode())
            if (not command_valid(payload) or payload["method"] not in
                    {"subscribeTokenTrade", "unsubscribeTokenTrade"}):
                raise CaptureError("shared-command-forbidden")
            async with self.lock:
                if lease is not self.lease or not lease.active or self.closed:
                    raise CaptureError("shared-lease-ended")
                if payload["method"] == "subscribeTokenTrade":
                    if len(self.watches | set(payload["keys"])) > 32:
                        raise CaptureError("shared-watch-limit")
                elif not set(payload["keys"]) <= self.watches:
                    raise CaptureError("shared-unsubscribe-unowned")
                await self._send(payload, lease)
        except BaseException:
            lease.revoke("command-failed")
            raise CaptureError("shared-trade-failed") from None

    async def _retire(self, lease):
        outcome = "unsubscribed"
        try:
            # Includes time waiting for an in-flight command. Research admission
            # is already revoked; this path permits unsubscribe only.
            async with asyncio.timeout(1.0):
                async with self.lock:
                    if self.closed:
                        raise CaptureError("shared-owner-closed")
                    if self.watches:
                        await self._send({"method": "unsubscribeTokenTrade",
                                          "keys": sorted(self.watches)}, cleanup=True)
        except BaseException:
            outcome = "upstream-aborted"
            self.abort("cleanup-failed")
        lease.cleanup = {"outcome": outcome, "reason": lease.reason,
                         "discovery_continues": not self.closed,
                         "provider_unsubscribe_acknowledged": False,
                         "billing_cutoff_verified": False}
        return lease.cleanup

    async def _read(self):
        try:
            while not self.closed:
                raw = await self.wire.recv()
                if type(raw) is not bytes or len(raw) > 65536:
                    raise CaptureError("shared-frame-bound")
                row = strict_json(raw)
                if not isinstance(row, dict) or row.get("error") or row.get("errors"):
                    raise CaptureError("shared-provider-error")
                if row.get("txType") in {"create", "migration", "migrate"}:
                    if not identifier(row.get("mint"), 32):
                        raise CaptureError("shared-mint")
                    self.sequence += 1
                    event = {k: v for k, v in row.items() if k in DISCOVERY_FIELDS}
                    envelope = (canonical({"v": 1, "seq": self.sequence, "event": event}) + "\n").encode()
                    if len(envelope) > 66000:
                        raise CaptureError("shared-envelope-bound")
                    self.discovery.offer(envelope)
                lease = self.lease
                if lease is not None and lease.active:
                    if asyncio.get_running_loop().time() >= lease.until:
                        lease.revoke("deadline")
                    else:
                        try:
                            lease.channel.offer(raw)
                        except CaptureError:
                            lease.revoke("research-overflow")
                await asyncio.sleep(0)  # allow both bounded consumers to drain fairly
        except asyncio.CancelledError:
            pass
        except Exception:
            self.abort("receive-or-discovery-failed")

    def abort(self, reason="owner-stop"):
        if self.closed:
            return
        self.closed, self.reason = True, reason
        if self.wire is not None:
            try:
                self.wire.abort()
            except Exception:
                self.reason = "abort-failed"
        self.discovery.close()
        if self.reader is not None and self.reader is not asyncio.current_task():
            self.reader.cancel()
        if self.lease is not None:
            self.lease.revoke("owner-ended")

    async def close(self):
        self.abort()
        if self.reader is not None:
            await asyncio.gather(self.reader, return_exceptions=True)
        if self.lease is not None:
            await self.lease.finish()
        if self.wire is not None:
            try:
                await asyncio.wait_for(self.wire.close(), 1)
            except Exception:
                self.reason = "close-failed"

    def receipt(self):
        return {"upstream_attempts": int(self.attempted), "research_attachments": int(self.attached),
                "discovery_events_dispatched": self.sequence, "commands": list(self.commands),
                "closed": self.closed, "reason": self.reason,
                "cleanup": self.lease.cleanup if self.lease else None,
                "provider_acknowledgement_verified": False, "billing_cutoff_verified": False}
