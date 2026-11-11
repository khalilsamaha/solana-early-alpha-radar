"""Offline Kali acceptance runner: synthetic evidence only, no credentials."""
import argparse
import io
import json
import os
from pathlib import Path
import platform
import sqlite3
import socket
import sys
import tempfile
import time
import unittest

from capture import (Capture, CaptureError, Limits, canonical, digest,
                     exclusive_file, export_capture, restore_capture, sync_dir, verify)

ROOT = Path(__file__).resolve().parent
SOURCES = ("capture.py", "check.py", "test_capture.py", "test_check.py", "README.md",
           "transport.py", "test_transport.py", "source_probe.py", "test_source_probe.py",
           "rpc_probe.py", "test_rpc_probe.py", "event_inspect.py", "test_event_inspect.py", "pump_schema.json",
           "schema_compare.py", "test_schema_compare.py", "trade_profile_0_5_0.json",
           "accounting_inspect.py", "test_accounting_inspect.py",
           "deployment_probe.py", "test_deployment_probe.py",
           "ordering_probe.py", "test_ordering_probe.py",
           "handoff.py", "test_handoff.py",
           "backup_roundtrip.py", "test_backup_roundtrip.py",
           "provider_wire.py", "test_provider_wire.py", "requirements-wire.txt",
           "supervisor.py", "supervisor_worker.py", "test_supervisor.py",
           "measurement.py", "test_measurement.py")


def block_internet():
    def guard(event, args):
        if (event == "socket.__new__" and args[1] in (socket.AF_INET, socket.AF_INET6)
                or event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo"}
                or event in {"socket.connect", "socket.sendto"} and args[0].family in (socket.AF_INET, socket.AF_INET6)):
            raise CaptureError("offline-runner-network-forbidden")
    sys.addaudithook(guard)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CaptureError("invalid-arguments")


def rehearsal():
    """Demonstrate capture -> pause -> restart -> limit -> export -> restore."""
    with tempfile.TemporaryDirectory(prefix="radar-r1-offline-") as tmp:
        root = Path(tmp)
        path = root / "capture"
        limits = Limits(messages=4, sample_modulus=1)
        mint, signature = "1" * 31 + "2", "2" * 88
        def raw(kind):
            return canonical(dict(txType=kind, mint=mint, signature=signature)).encode()
        with Capture(path, limits) as c:
            c.receive(raw("create"))
            c.receive(raw("buy"))
        with Capture(path, limits) as c:
            c.receive(raw("sell"))
            c.receive(raw("migration"))
        original = verify(path)
        original_hash = digest((path / "ticks.db").read_bytes())
        manifest = export_capture(path, root / "archive")
        restored = restore_capture(root / "archive", root / "restored")
        if (restored != original or manifest["report"] != original
                or digest((path / "ticks.db").read_bytes()) != original_hash
                or original["messages"] != 4 or original["stop_reason"] != "message-limit"
                or original["gaps"] != 1 or original["restarts"] != 1):
            raise CaptureError("rehearsal-failed")
        return {"capture": original, "local_restore_replay_passed": True,
                "source_preserved": True, "off_machine_restore_verified": False}


def supervision_rehearsal():
    from supervisor import rehearse
    with tempfile.TemporaryDirectory(prefix="radar-r1-supervisor-") as tmp:
        _, report = rehearse(tmp)
        if report["status"] != "offline-supervisor-passed-live-blocked":
            raise CaptureError("supervision-rehearsal-failed")
        # The runner removes its synthetic temporary artifacts; the standalone
        # supervisor CLI instead retains the private run directory.
        report["raw_artifacts_retained"] = False
        report["artifacts_scope"] = "temporary-offline-acceptance-fixture"
        return report


def run_checks():
    suite = unittest.defaultTestLoader.discover(str(ROOT), pattern="test_*.py")
    # Test traces contain only synthetic fixtures, but never export tracebacks
    # or arbitrary exception strings into the user-facing report.
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=2).run(suite)
    if not result.wasSuccessful() or result.testsRun == 0 or result.skipped:
        raise CaptureError("regression-failed")
    return {"run": result.testsRun, "failures": len(result.failures),
            "errors": len(result.errors), "skipped": len(result.skipped)}


def main(argv=None):
    try:
        if sys.version_info < (3, 11):
            raise CaptureError("python-version")
        parser = Parser(description="R1 offline acceptance only; no live collection is available.")
        parser.add_argument("--output", required=True)
        args = parser.parse_args(argv)
        output = Path(args.output)
        if output.exists() or output.is_symlink():
            raise CaptureError("output-exists")
        block_internet()
        from provider_wire import dependency
        dependencies = dependency()
        before = {name: digest((ROOT / name).read_bytes()) for name in SOURCES}
        started = time.monotonic()
        tests = run_checks()
        evidence = rehearsal()
        supervision = supervision_rehearsal()
        after = {name: digest((ROOT / name).read_bytes()) for name in SOURCES}
        if before != after:
            raise CaptureError("source-changed")
        report = {"schema_version": 1, "status": "offline-measurement-passed-live-blocked",
                  "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                  "tests": tests, "source_sha256": after,
                  "elapsed_seconds": round(time.monotonic() - started, 6),
                  "synthetic_only": True, "network_used": False, "credentials_loaded": False,
                  "paid_collection_enabled": False, "evidence": evidence,
                  "dependencies": dependencies, "supervision": supervision,
                  "internet_socket_creation_and_dns_blocked": True,
                  "wire_validation": {"protocol_peer": "in-memory", "provider_connection_opened": False,
                                      "tls_handshake_tested": False, "coexistence_accepted": False},
                  "remaining": ["Kali measurement; historical configuration and executable pricing validation", "provider connection coexistence",
                                "source ordering, initial state and finality validation",
                                "gap recovery source", "billing and explicit pilot budget",
                                "live-launch credential/budget controls and real provider TLS/session validation",
                                "preservation coverage and retention for actual live captures"]}
        # Build in a private sibling then link exclusively: readers never see a
        # partial report and an existing path (including symlink) is not replaced.
        with tempfile.TemporaryDirectory(prefix=".r1-report-", dir=output.parent) as tmp:
            prepared = Path(tmp) / "report.json"
            exclusive_file(prepared, (canonical(report) + "\n").encode())
            os.link(prepared, output, follow_symlinks=False)
        sync_dir(output.parent)
        print("R1 offline checks including local measurement evidence passed; live collection remains blocked. Report created.")
        return 0
    except Exception:
        print("R1 offline check stopped; no acceptance is granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
