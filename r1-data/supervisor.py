"""Offline process supervision rehearsal. No live mode or credential interface.

The ownership lock covers only cooperating runs using the SAME private owner
folder. It is not a machine-wide scanner/provider connection lock.
"""
from contextlib import contextmanager
from dataclasses import asdict
import argparse
import fcntl
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import uuid

from capture import (CaptureError, Limits, canonical, digest, exclusive_file,
                     private_directory, strict_json, sync_dir)
from handoff import MAX_PACKAGE, path_without_links, read_private

ROOT = Path(__file__).resolve().parent
SOURCES = ("supervisor.py", "supervisor_worker.py", "capture.py", "transport.py", "handoff.py")
LIMITS = Limits(messages=4, seconds=5, sample_modulus=1)
RESOURCES = {"address_space_bytes": 256 * 1024 * 1024, "cpu_seconds": 5,
             "file_bytes": 36 * 1024 * 1024, "open_files": 32,
             "core_bytes": 0, "worker_alarm_seconds": 10}
WALL_SECONDS = 12
TERM_SECONDS = 0.25
REAP_SECONDS = 1
ENVIRONMENT = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": os.defpath}


def source_pins():
    return {name: digest((ROOT / name).read_bytes()) for name in SOURCES}


@contextmanager
def owner_lock(directory):
    directory = path_without_links(directory)
    private_directory(directory)
    path = directory / "r1-supervisor.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        st = os.fstat(fd)
        current = path.lstat()
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                or st.st_mode & 0o077 or st.st_nlink != 1
                or (st.st_dev, st.st_ino) != (current.st_dev, current.st_ino)):
            raise CaptureError("unsafe-owner-lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise CaptureError("owner-busy") from None
        yield directory
    finally:
        # Never unlink the lock: replacing its inode could admit a second owner.
        os.close(fd)


class Interrupted(BaseException):
    pass


@contextmanager
def termination_handlers():
    previous = {}
    def stop(signum, frame):
        raise Interrupted()
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, stop)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def kill_group(process, signum):
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def supervise(command, directory, *, wall_seconds=WALL_SECONDS, term_seconds=TERM_SECONDS):
    """Internal primitive, not an arbitrary-command CLI. Never retry a worker."""
    if not (0 < wall_seconds <= WALL_SECONDS and 0 < term_seconds <= TERM_SECONDS):
        raise CaptureError("invalid-supervision-limits")
    started = time.monotonic()
    process = None
    outcome = "worker-start-failed"
    escalated = False
    with termination_handlers():
        try:
            process = subprocess.Popen(command, cwd=directory, env=ENVIRONMENT,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                close_fds=True, start_new_session=True)
            try:
                code = process.wait(timeout=max(0.001, wall_seconds - (time.monotonic() - started)))
                outcome = "worker-exited" if code == 0 else "worker-failed"
            except subprocess.TimeoutExpired:
                outcome = "worker-deadline"
        except (Interrupted, KeyboardInterrupt):
            outcome = "worker-interrupted"
        except Exception:
            outcome = "worker-failed"
        finally:
            if process is not None:
                # Mask repeat operator interrupts during bounded cleanup only.
                saved = {s: signal.signal(s, signal.SIG_IGN) for s in (signal.SIGINT, signal.SIGTERM)}
                try:
                    kill_group(process, signal.SIGTERM)
                    try:
                        process.wait(timeout=term_seconds)
                    except subprocess.TimeoutExpired:
                        escalated = True
                    finally:
                        # Also terminate any remaining members after leader exit.
                        kill_group(process, signal.SIGKILL)
                    try:
                        process.wait(timeout=REAP_SECONDS)
                    except subprocess.TimeoutExpired:
                        outcome = "worker-cleanup-unconfirmed"
                finally:
                    for signum, handler in saved.items():
                        signal.signal(signum, handler)
    return {"outcome": outcome, "workers_started": int(process is not None),
            "forced_kill_needed": escalated,
            "worker_reaped": process is not None and process.returncode is not None,
            "elapsed_seconds": round(time.monotonic() - started, 6)}


def worker_command(run):
    return [sys.executable, "-E", "-s", "-B", "-W", "error::ResourceWarning",
            str(ROOT / "supervisor_worker.py"), str(run), str(os.getpid())]


def validate_receipt(run, manifest_bytes):
    result = strict_json(read_private(run / "worker-result.json", 16_384))
    expected = {"schema_version", "manifest_sha256", "resources", "offline_guards",
                "session", "bundle_sha256", "bundle_bytes", "database_sha256",
                "source_preserved", "local_restore_replay_verified"}
    if (set(result) != expected or type(result["schema_version"]) is not int
            or result["schema_version"] != 1
            or result["manifest_sha256"] != digest(manifest_bytes)
            or result["resources"] != RESOURCES
            or result["offline_guards"] != {"internet_and_dns_blocked": True,
                                            "child_process_creation_blocked": True,
                                            "parent_death_sigkill": True,
                                            "environment_allowlist": True}
            or result["session"] != {"outcome": "capture-stopped", "commands_sent": 3,
                                     "connections_opened": 1, "subscription_acknowledged": False,
                                     "provider_billing_verified": False}
            or result["source_preserved"] is not True
            or result["local_restore_replay_verified"] is not True):
        raise CaptureError("invalid-worker-receipt")
    bundle = read_private(run / "export" / "capture.zip", MAX_PACKAGE)
    database = read_private(run / "capture" / "ticks.db", 32 * 1024 * 1024)
    if (result["bundle_sha256"] != digest(bundle) or type(result["bundle_bytes"]) is not int
            or result["bundle_bytes"] != len(bundle)
            or result["database_sha256"] != digest(database)
            or read_private(run / "manifest.json", 16_384) != manifest_bytes):
        raise CaptureError("receipt-content-mismatch")
    return result


def rehearse(directory):
    """Create one new run, retain all artifacts even on failure, never resume."""
    with owner_lock(directory) as owner:
        pins = source_pins()
        run = owner / ("run-" + uuid.uuid4().hex)
        run.mkdir(mode=0o700)
        manifest = {"schema_version": 1, "mode": "offline-rehearsal", "run_id": run.name,
                    "parent_pid": os.getpid(), "source_sha256": pins,
                    "limits": asdict(LIMITS), "resources": RESOURCES}
        raw = (canonical(manifest) + "\n").encode()
        exclusive_file(run / "manifest.json", raw)
        process = supervise(worker_command(run), run)
        receipt = None
        if process["outcome"] == "worker-exited" and process["worker_reaped"]:
            try:
                if source_pins() != pins:
                    raise CaptureError("source-changed")
                receipt = validate_receipt(run, raw)
            except Exception:
                process["outcome"] = "worker-evidence-rejected"
        report = {"schema_version": 1,
                  "status": ("offline-supervisor-passed-live-blocked" if receipt else
                             "offline-supervisor-failed-live-blocked"),
                  "process": process, "manifest_sha256": digest(raw), "source_sha256": pins,
                  "worker_receipt": receipt, "synthetic_only": True, "network_used": False,
                  "credentials_loaded": False, "paid_collection_enabled": False,
                  "provider_connection_opened": False, "coexistence_accepted": False,
                  "owner_lock_scope": "cooperating-runs-in-same-private-directory",
                  "automatic_restart": False, "automatic_repair": False,
                  "off_machine_restore_verified": False, "raw_artifacts_retained": True}
        exclusive_file(run / "report.json", (canonical(report) + "\n").encode())
        sync_dir(owner)
        return run, report


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CaptureError("invalid-arguments")


def main(argv=None):
    try:
        parser = Parser(description="Offline synthetic supervision only; no live mode.")
        parser.add_argument("--owner-directory", required=True)
        parser.add_argument("--rehearse", action="store_true", required=True)
        args = parser.parse_args(argv)
        _, report = rehearse(args.owner_directory)
        if report["status"] != "offline-supervisor-passed-live-blocked":
            raise CaptureError("rehearsal-failed")
        print("Offline supervisor rehearsal passed; private artifacts retained; live blocked.")
        return 0
    except BaseException:
        print("Offline supervisor stopped; no acceptance granted; retain any run artifacts.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
