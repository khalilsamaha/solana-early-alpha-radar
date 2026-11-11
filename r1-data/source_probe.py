"""Bounded metadata-only probe of existing launch_registry creation records.

Never opens a provider connection, reads .env, requests RPC data or evaluates
outcomes. Observed field presence is not proof of source truth or completeness.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

from capture import CaptureError, canonical, exclusive_file, strict_json, sync_dir

FIELDS = ("signature", "creatorReported", "traderReported", "bondingCurveKey",
          "slotReported", "decimalsReported", "initialBuyReported", "solAmountReported",
          "virtualSolReservesReported", "virtualTokenReservesReported")
MAX_ROWS = 128


def discover_database(project, runner=subprocess.run):
    """Inspect only local Docker labels and the matching data mount; no .env."""
    project = Path(project).absolute()
    if project.resolve() != project or not project.is_dir():
        raise CaptureError("project-path")
    prefix = ["docker", "--host", "unix:///var/run/docker.sock"]
    def run(args):
        result = runner(prefix + args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        timeout=5, check=False)
        if result.returncode or len(result.stdout) > 8192:
            raise CaptureError("docker-discovery")
        return result.stdout.decode("utf-8").strip()
    cid = run(["ps", "--no-trunc", "--filter", "label=com.docker.compose.service=radar",
               "--filter", "label=com.docker.compose.project.working_dir=" + str(project),
               "--format", "{{.ID}}"])
    if not re.fullmatch(r"[0-9a-f]{64}", cid):
        raise CaptureError("container-not-unique")
    template = ('{"running":{{json .State.Running}},"sources":['
                '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{json .Source}}{{end}}{{end}}]}')
    data = strict_json(run(["inspect", "--format", template, cid]).encode())
    sources = data.get("sources")
    if data.get("running") is not True or not isinstance(sources, list) or len(sources) != 1:
        raise CaptureError("data-mount-unavailable")
    if not isinstance(sources[0], str) or not Path(sources[0]).is_absolute():
        raise CaptureError("invalid-data-mount")
    return Path(sources[0]) / "radar.sqlite"


def collect(database, *, now_ms=None, seconds=3.0):
    if not 0 < seconds <= 5:
        raise CaptureError("invalid-probe-deadline")
    started = time.monotonic()
    deadline = started + seconds
    now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    db = None
    result = {"status": "source-metadata-unavailable", "captured_at_ms": now, "rows_sampled": 0,
              "valid_records": 0, "invalid_records": 0,
              "oversized_records": 0, "field_nonnull": {k: 0 for k in FIELDS},
              "field_absent_or_null": {k: 0 for k in FIELDS},
              "latest_creation_age_ms": None, "network_requests": 0,
              "credentials_read": False, "outcomes_read": False,
              "source_complete": False, "live_activation_allowed": False,
              "scope": "latest-at-most-128-retained-creations-within-24h",
              "limitations": ["creation metadata only, no token trade stream",
                              "retained provider fields, not raw original numeric lexemes",
                              "no verified ledger order, finality or initial curve state",
                              "no connection-policy or billing verification"]}
    try:
        path = Path(database).absolute()
        identity = path.lstat()
        if path.resolve() != path or not stat.S_ISREG(identity.st_mode):
            raise CaptureError("database-path")
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=min(seconds, 1))
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA temp_store=MEMORY")
        db.execute("PRAGMA cache_size=-2048")
        db.execute("PRAGMA mmap_size=0")
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 16_384)
        db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 100)
        db.execute("BEGIN")
        schema = db.execute("SELECT type FROM sqlite_master WHERE name='launch_registry'").fetchone()
        if schema != ("table",):
            raise CaptureError("missing-registry")
        # Pin the existing received_at index; never fall back to a full scan/sort.
        indexes = db.execute("PRAGMA index_list('launch_registry')").fetchall()
        if not any(row[1] == "launch_registry_received" for row in indexes):
            raise CaptureError("missing-index")
        columns = db.execute("PRAGMA index_info('launch_registry_received')").fetchall()
        if len(columns) != 1 or columns[0][2] != "received_at":
            raise CaptureError("wrong-index")

        def authorize(action, arg1, arg2, dbname, trigger):
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_READ and arg1 == "launch_registry" and arg2 in {"received_at", "data"}:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_FUNCTION and arg2 in {"length", "typeof"}:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        db.set_authorizer(authorize)
        newest = db.execute("SELECT received_at FROM launch_registry INDEXED BY launch_registry_received ORDER BY received_at DESC LIMIT 1").fetchone()
        if newest:
            if type(newest[0]) is not int or newest[0] > now or newest[0] < 0:
                raise CaptureError("invalid-receive-clock")
            result["latest_creation_age_ms"] = now - newest[0]
        rows = db.execute("""SELECT received_at,
          CASE WHEN typeof(data)='text' AND length(CAST(data AS BLOB))<=4096 THEN data END,
          length(CAST(data AS BLOB))
          FROM launch_registry INDEXED BY launch_registry_received
          WHERE received_at>=? AND received_at<=? ORDER BY received_at DESC LIMIT ?""",
          (now - 86_400_000, now, MAX_ROWS))
        for at, raw, size in rows:
            if time.monotonic() >= deadline:
                raise CaptureError("read-deadline")
            result["rows_sampled"] += 1
            if raw is None:
                result["oversized_records"] += int(isinstance(size, int) and size > 4096)
                result["invalid_records"] += 1
                continue
            try:
                row = strict_json(raw.encode())
                if (row.get("version") != "launch-registry-1" or row.get("source") != "pumpportal:create"
                        or row.get("receivedAt") != at or row.get("availableAt") != at
                        or not isinstance(row.get("fields"), dict)):
                    raise ValueError("record")
                result["valid_records"] += 1
                for key in FIELDS:
                    if row["fields"].get(key) is None:
                        result["field_absent_or_null"][key] += 1
                    else:
                        result["field_nonnull"][key] += 1
            except (ValueError, TypeError, RecursionError):
                result["invalid_records"] += 1
        after = path.lstat()
        if (after.st_dev, after.st_ino) != (identity.st_dev, identity.st_ino) or time.monotonic() >= deadline:
            raise CaptureError("source-changed-or-deadline")
        result["status"] = "creation-metadata-observed" if result["valid_records"] else "creation-metadata-insufficient"
    except Exception:
        # Partial counts are diagnostic only. Never promote a timed-out read.
        result["status"] = "source-metadata-unavailable"
    finally:
        if db is not None:
            db.close()
    result["elapsed_seconds"] = round(time.monotonic() - started, 6)
    return result


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CaptureError("invalid-arguments")


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument("--database")
        source.add_argument("--project")
        parser.add_argument("--output", required=True)
        args = parser.parse_args(argv)
        output = Path(args.output)
        if output.exists() or output.is_symlink():
            raise CaptureError("output-exists")
        database = args.database
        discovery = "not-requested"
        if args.project:
            try:
                database = discover_database(args.project)
                discovery = "local-data-mount-found"
            except Exception:
                database = None
                discovery = "local-data-mount-unavailable"
        result = collect(database)
        result["discovery_status"] = discovery
        # Bind metadata-probe evidence to all code imported by this CLI.
        root = Path(__file__).resolve().parent
        result["source_sha256"] = {n: hashlib.sha256((root / n).read_bytes()).hexdigest()
                                   for n in ("source_probe.py", "capture.py")}
        with tempfile.TemporaryDirectory(prefix=".r1-probe-", dir=output.parent) as tmp:
            prepared = Path(tmp) / "report.json"
            exclusive_file(prepared, (canonical(result) + "\n").encode())
            if os.geteuid() == 0 and os.environ.get("SUDO_UID", "").isdigit() and os.environ.get("SUDO_GID", "").isdigit():
                os.chown(prepared, int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"]))
            os.link(prepared, output, follow_symlinks=False)
        sync_dir(output.parent)
        print("R1 source probe:", result["status"], "— live collection remains blocked.")
        # An unavailable-source report is useful evidence, not an acceptance.
        return 0
    except Exception:
        print("R1 source probe stopped; no source acceptance is granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
