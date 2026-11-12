"""Combined owner, threaded real capture and Node discovery rehearsal; synthetic only."""
import asyncio
import os
from pathlib import Path
import shutil
import threading
import tempfile

from capture import Capture, CaptureError, Limits, canonical, digest, exclusive_file, verify
from measurement import Journal, replay
from session_bundle import export_session, restore_session
from shared_owner import Owner
from shared_discovery import Server, deliver
import shared_session

ROOT = Path(__file__).resolve().parent
ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


class SyntheticWire:
    def __init__(self, fail_cleanup):
        self.incoming = asyncio.Queue()
        self.sent, self.closed, self.fail_cleanup = [], False, fail_cleanup

    async def send(self, raw):
        from capture import strict_json
        row = strict_json(raw.encode())
        self.sent.append(row)
        if self.fail_cleanup and row["method"] == "unsubscribeTokenTrade":
            raise RuntimeError("synthetic cleanup failure")

    async def recv(self):
        return await self.incoming.get()

    def abort(self):
        self.closed = True

    async def close(self):
        self.abort()


async def until(predicate):
    async with asyncio.timeout(5):
        while not predicate():
            await asyncio.sleep(0.002)


async def exercise(directory, *, transport="unix", fail_cleanup=False, launcher=None):
    if transport not in {"unix", "pipe"} or launcher is not None and transport != "unix":
        raise CaptureError("shared-rehearsal-transport")
    directory = Path(directory)
    directory.mkdir(mode=0o700)
    node = shutil.which("node")
    if node is None and launcher is None:
        raise CaptureError("shared-node-required")
    wire = SyntheticWire(fail_cleanup)
    attempts = 0
    async def factory():
        nonlocal attempts
        attempts += 1
        return wire
    owner = Owner(factory)
    server = child = delivery = worker = None
    progress = {"frames_sent": 0}
    lease = None
    ipc_temp = None
    try:
        args = [node, str(ROOT / "shared_scanner_fixture.mjs"), transport]
        if transport == "unix":
            ipc_temp = tempfile.TemporaryDirectory(prefix="r1-ipc-")
            ipc = Path(ipc_temp.name)
            server = Server(owner, ipc)
            await server.start()
            args.append(str(server.path))
            progress = server.progress
        if launcher is None:
            child = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                env=ENV, cwd=directory, limit=8192, start_new_session=True)
        else:
            child = await launcher.start(server.path, directory)
        if await asyncio.wait_for(child.stdout.readline(), 5) != b"ready\n":
            raise CaptureError("shared-scanner-start")
        if server:
            await asyncio.wait_for(server.connected.wait(), 3)
        else:
            delivery = asyncio.create_task(deliver(owner, child.stdin, progress))
        await owner.start()
        lease = owner.attach(5)
        ready = threading.Event()
        def capture_worker():
            with Journal(directory / "session.jsonl") as journal:
                with Capture(directory / "capture", Limits(messages=4, seconds=5, sample_modulus=1)) as capture:
                    ready.set()
                    return asyncio.run(shared_session.run(capture, lease, journal))
        worker = asyncio.create_task(asyncio.to_thread(capture_worker))
        await until(ready.is_set)
        def raw(kind, mint="1" * 31 + "2"):
            return canonical({"txType": kind, "mint": mint, "signature": "2" * 88, "initialBuy": 0}).encode()
        await wire.incoming.put(raw("create"))
        await until(lambda: any(x["method"] == "subscribeTokenTrade" for x in wire.sent))
        for kind in ("buy", "sell", "migration"):
            await wire.incoming.put(raw(kind))
        # Ensure discovery has been drained before research retirement can close
        # the socket in the failure scenario; a later post-stop frame is distinct.
        result = await asyncio.wait_for(asyncio.shield(worker), 7)
        if not fail_cleanup:
            if owner.closed:
                raise CaptureError("shared-discovery-stopped-with-research")
            await wire.incoming.put(raw("create", "1" * 31 + "3"))
            await until(lambda: progress["frames_sent"] == 3)
        await owner.close()
        if delivery:
            await asyncio.gather(delivery, return_exceptions=True)
        if server:
            await server.close()
            server = None
        child.stdin.close()
        data = await asyncio.wait_for(child.stdout.read(8193), 5)
        await asyncio.wait_for(child.wait(), 2)
        from capture import strict_json
        if child.returncode or len(data) > 8192:
            raise CaptureError("shared-scanner-result")
        scanner = strict_json(data)
        expected = "transport-cleanup-failed" if fail_cleanup else "capture-stopped"
        if (attempts != 1 or result["outcome"] != expected
                or scanner["upstream_connections_opened"] != 0 or scanner["discovery_gaps"] != 1
                or not fail_cleanup and (scanner["tokens"] != 3 or scanner["creations"] != 2)
                or [x["method"] for x in wire.sent] != ["subscribeNewToken", "subscribeMigration",
                    "subscribeTokenTrade", "unsubscribeTokenTrade"]):
            raise CaptureError("shared-integrated-expectation")
        measured = replay(directory / "capture", directory / "session.jsonl")
        capture_report = verify(directory / "capture")
        exported = export_session(directory / "capture", directory / "session.jsonl", directory / "export")
        restored = restore_session(directory / "export/session.zip", exported["bundle_sha256"], directory / "restore")
        if (restored["measurement"] != measured or restored["capture"] != capture_report
                or measured["local_sends_completed"] != 1 or measured["session_outcome"] != expected):
            raise CaptureError("shared-replay")
        report = {"scenario": "cleanup-failure" if fail_cleanup else "normal-stop",
                  "transport": transport, "node": scanner, "owner": owner.receipt(),
                  "research": result, "measurement": measured, "capture": capture_report,
                  "session_bundle_sha256": exported["bundle_sha256"],
                  "session_bundle_bytes": exported["bundle_bytes"], "complete_session_replayed": True,
                  "discovery_after_research_stop_verified": not fail_cleanup,
                  "real_local_socket_tested": transport == "unix", "provider_connection_opened": False}
        exclusive_file(directory / "report.json", (canonical(report) + "\n").encode())
        return report
    finally:
        await owner.close()
        if server:
            await server.close()
        if delivery:
            delivery.cancel()
            await asyncio.gather(delivery, return_exceptions=True)
        if child and child.returncode is None:
            child.kill()
            await child.wait()
        if worker and not worker.done():
            # Revoking the lease releases receive waiters. The outer acceptance
            # command also has a process deadline; no unbounded live worker here.
            try:
                await asyncio.wait_for(asyncio.shield(worker), 2)
            except Exception:
                pass
        if launcher is not None:
            await launcher.cleanup()
        if ipc_temp:
            ipc_temp.cleanup()
