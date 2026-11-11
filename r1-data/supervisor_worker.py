"""Fixed synthetic worker for the offline supervisor; never dials a provider."""
import ctypes
import os
from pathlib import Path
import resource
import signal
import socket
import sys


def bootstrap(parent_pid):
    # Linux PR_SET_PDEATHSIG closes the orphan window; the parent PID check also
    # rejects a parent which disappeared before prctl was installed.
    if sys.platform != "linux" or type(parent_pid) is not int or parent_pid <= 1:
        raise RuntimeError("worker-platform")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent_pid:
        raise RuntimeError("worker-parent")
    os.umask(0o077)
    limits = ((resource.RLIMIT_CORE, 0), (resource.RLIMIT_AS, 256 * 1024 * 1024),
              (resource.RLIMIT_CPU, 5), (resource.RLIMIT_FSIZE, 36 * 1024 * 1024),
              (resource.RLIMIT_NOFILE, 32))
    for key, value in limits:
        resource.setrlimit(key, (value, value))
        if resource.getrlimit(key) != (value, value):
            raise RuntimeError("worker-resource-limit")
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, 10)
    def guard(event, args):
        if (event in {"subprocess.Popen", "os.fork", "os.forkpty", "os.posix_spawn", "os.exec"}
                or event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo"}
                or event == "socket.__new__" and args[1] in (socket.AF_INET, socket.AF_INET6)
                or event in {"socket.connect", "socket.sendto"} and args[0].family in (socket.AF_INET, socket.AF_INET6)):
            raise RuntimeError("offline-worker-forbidden")
    sys.addaudithook(guard)


def run(directory, parent_pid):
    bootstrap(parent_pid)
    # The parent does not pass through HOME, provider credentials, proxies,
    # PYTHONPATH or user-supplied interpreter settings.
    import asyncio
    from dataclasses import asdict
    import supervisor as s
    from capture import Capture, canonical, digest, exclusive_file, strict_json, verify
    import handoff
    from transport import run_session

    if (dict(os.environ) != s.ENVIRONMENT or not sys.flags.ignore_environment
            or not sys.flags.no_user_site or not sys.dont_write_bytecode):
        raise RuntimeError("worker-environment")
    directory = handoff.path_without_links(directory)
    s.private_directory(directory)
    raw = handoff.read_private(directory / "manifest.json", 16_384)
    manifest = strict_json(raw)
    expected = {"schema_version": 1, "mode": "offline-rehearsal", "run_id": directory.name,
                "parent_pid": parent_pid, "source_sha256": s.source_pins(),
                "limits": asdict(s.LIMITS), "resources": s.RESOURCES}
    if (manifest != expected or type(manifest["schema_version"]) is not int
            or type(manifest["parent_pid"]) is not int
            or set(p.name for p in directory.iterdir()) != {"manifest.json"}):
        raise RuntimeError("worker-manifest")

    class SyntheticWire:
        def __init__(self):
            self.frames = iter(canonical({"txType": kind, "mint": "1" * 31 + "2",
                                         "signature": "2" * 88}).encode()
                               for kind in ("create", "buy", "sell", "migration"))
            self.closed = False
        async def send(self, command):
            if self.closed:
                raise RuntimeError("closed")
        async def recv(self):
            return next(self.frames)
        def abort(self):
            self.closed = True
        async def close(self):
            self.abort()

    wire = SyntheticWire()
    async def factory():
        return wire
    with Capture(directory / "capture", s.LIMITS) as capture:
        session = asyncio.run(run_session(capture, factory))
    capture_report = verify(directory / "capture")
    if (not wire.closed or capture_report["messages"] != 4
            or capture_report["raw_rows"] != 4 or capture_report["gaps"] != 0
            or capture_report["stop_reason"] != "message-limit"):
        raise RuntimeError("worker-capture")
    before = handoff.read_private(directory / "capture" / "ticks.db", 32 * 1024 * 1024)
    exported = handoff.export_capture(directory / "capture", directory / "export")
    restored = handoff.restore_capture(directory / "export" / "capture.zip",
                                       exported["bundle_sha256"], directory / "restore")
    if (restored["capture"] != capture_report
            or before != handoff.read_private(directory / "capture" / "ticks.db", 32 * 1024 * 1024)
            or s.source_pins() != manifest["source_sha256"]):
        raise RuntimeError("worker-preservation")
    receipt = {"schema_version": 1, "manifest_sha256": digest(raw), "resources": s.RESOURCES,
               "offline_guards": {"internet_and_dns_blocked": True,
                                  "child_process_creation_blocked": True,
                                  "parent_death_sigkill": True,
                                  "environment_allowlist": True},
               "session": session, "bundle_sha256": exported["bundle_sha256"],
               "bundle_bytes": exported["bundle_bytes"], "database_sha256": digest(before),
               "source_preserved": True, "local_restore_replay_verified": True}
    exclusive_file(directory / "worker-result.json", (canonical(receipt) + "\n").encode())


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise RuntimeError("worker-arguments")
        run(sys.argv[1], int(sys.argv[2]))
    except BaseException:
        # Parent records a fixed failure status. Never print raw exceptions.
        sys.exit(1)
