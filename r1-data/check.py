"""Offline Kali acceptance runner: synthetic evidence only, no credentials."""
import argparse
import io
import json
import os
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile
import time
import unittest

from capture import (Capture, CaptureError, Limits, canonical, digest,
                     exclusive_file, export_capture, restore_capture, sync_dir, verify)

ROOT = Path(__file__).resolve().parent
SOURCES = ("capture.py", "check.py", "test_capture.py", "test_check.py", "README.md",
           "transport.py", "test_transport.py", "source_probe.py", "test_source_probe.py")


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
        before = {name: digest((ROOT / name).read_bytes()) for name in SOURCES}
        started = time.monotonic()
        tests = run_checks()
        evidence = rehearsal()
        after = {name: digest((ROOT / name).read_bytes()) for name in SOURCES}
        if before != after:
            raise CaptureError("source-changed")
        report = {"schema_version": 1, "status": "offline-transport-passed-live-blocked",
                  "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                  "tests": tests, "source_sha256": after,
                  "elapsed_seconds": round(time.monotonic() - started, 6),
                  "synthetic_only": True, "network_used": False, "credentials_loaded": False,
                  "paid_collection_enabled": False, "evidence": evidence,
                  "remaining": ["Kali transport and metadata-probe review", "provider connection coexistence",
                                "source ordering, initial state and finality validation",
                                "gap recovery source", "billing and explicit pilot budget",
                                "real network adapter implementation and validation",
                                "off-machine preservation and restore"]}
        # Build in a private sibling then link exclusively: readers never see a
        # partial report and an existing path (including symlink) is not replaced.
        with tempfile.TemporaryDirectory(prefix=".r1-report-", dir=output.parent) as tmp:
            prepared = Path(tmp) / "report.json"
            exclusive_file(prepared, (canonical(report) + "\n").encode())
            os.link(prepared, output, follow_symlinks=False)
        sync_dir(output.parent)
        print("R1 offline capture and transport checks passed; live collection remains blocked. Report created.")
        return 0
    except Exception:
        print("R1 offline check stopped; no acceptance is granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
