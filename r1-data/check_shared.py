"""Combined offline shared-owner acceptance. Default requires real LOCAL Unix IPC.

--pipe-only records a distinct development result and cannot pass host IPC.
No provider connection, credential, production data or B2 access is available.
"""
import argparse
import asyncio
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import time

import check
from capture import CaptureError, canonical, digest, exclusive_file
from handoff import path_without_links
from provider_wire import dependency
from shared_rehearsal import ENV, exercise

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


def source_pins():
    files = {(ROOT / name).resolve() for name in check.SOURCES}
    files.update(ROOT.glob("shared_*.py"))
    files.update(ROOT.glob("test_shared_*.py"))
    files.update({ROOT / "check_shared.py", ROOT / "shared_scanner_fixture.mjs",
                  REPO / "scanner/src/core/stats-compact-manifest.json"})
    for directory in (REPO / "scanner/src", REPO / "scanner/test"):
        files.update(directory.rglob("*.js"))
    return {str(p.resolve().relative_to(REPO)): digest(p.read_bytes()) for p in sorted(files)}


def node_checks():
    node = shutil.which("node")
    if node is None:
        raise CaptureError("node-required")
    version = subprocess.run([node, "--version"], env=ENV, check=True, timeout=5,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode().strip()
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", version)
    if not match or tuple(map(int, match.groups())) < (24, 10, 0):
        raise CaptureError("node-version")
    paths = sorted(str(p) for p in (REPO / "scanner/test").glob("*.test.js"))
    result = subprocess.run([node, "--test", "--test-reporter=tap", *paths], env=ENV,
        cwd=REPO / "scanner", stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=90)
    if len(result.stdout) > 1024 * 1024:
        raise CaptureError("node-test-output-bound")
    counts = {k: int(v) for k, v in re.findall(r"^# (tests|pass|fail|cancelled|skipped|todo) (\d+)$",
                                             result.stdout.decode(), re.M)}
    if (result.returncode or set(counts) != {"tests", "pass", "fail", "cancelled", "skipped", "todo"}
            or counts["tests"] <= 0 or counts["pass"] != counts["tests"]
            or any(counts[k] for k in ("fail", "cancelled", "skipped", "todo"))):
        raise CaptureError("node-regression-failed")
    return {"version": version, **counts}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CaptureError("shared-check-arguments")


def main(argv=None):
    output = None
    try:
        parser = Parser(description=__doc__)
        parser.add_argument("--output-directory", required=True)
        parser.add_argument("--pipe-only", action="store_true")
        args = parser.parse_args(argv)
        output = path_without_links(args.output_directory)
        output.mkdir(mode=0o700)
        os.umask(0o077)
        check.block_internet()
        before = source_pins()
        dependencies = dependency()
        started = time.monotonic()
        tests = check.run_checks()
        scanner = node_checks()
        transport = "pipe" if args.pipe_only else "unix"
        normal = asyncio.run(exercise(output / "normal", transport=transport))
        failure = asyncio.run(exercise(output / "failure", transport=transport, fail_cleanup=True))
        after = source_pins()
        if before != after:
            raise CaptureError("shared-sources-changed")
        status = ("offline-shared-pipe-passed-host-ipc-pending" if args.pipe_only
                  else "offline-shared-integration-passed-live-blocked")
        report = {"schema_version": 1, "status": status, "python": platform.python_version(),
                  "sqlite": sqlite3.sqlite_version, "dependencies": dependencies,
                  "tests": tests, "scanner_tests": scanner, "source_sha256": after,
                  "elapsed_seconds": round(time.monotonic() - started, 6),
                  "normal": normal, "cleanup_failure": failure,
                  "real_local_socket_tested": not args.pipe_only, "synthetic_only": True,
                  "provider_connection_opened": False, "credentials_loaded": False,
                  "internet_used": False, "paid_feed_activated": False, "transactions_sent": 0,
                  "production_modified": False, "full_gate_accepted": False,
                  "remaining": ["independent Kali evidence review", "production IPC identity and rollout validation",
                    "live-launch credential/exposure controls", "measurement registration and budget approval",
                    "actual provider TLS and subscription behavior", "live preservation and retention"]}
        exclusive_file(output / "session.zip", (output / "normal/export/session.zip").read_bytes())
        exclusive_file(output / "report.json", (canonical(report) + "\n").encode())
        print("Shared integration checks completed; live remains blocked. Upload report.json and session.zip from:")
        print(output)
        return 0
    except Exception:
        # Never export a traceback, private endpoint or arbitrary child output.
        print("Shared integration check failed; preserve its directory. No acceptance granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    # Use the supplied external timeout command. Existing RPC regressions own
    # SIGALRM and intentionally reject a competing in-process timer.
    sys.exit(main())
