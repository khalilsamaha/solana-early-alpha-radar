"""One explicit B2 round trip of the already accepted synthetic handoff only."""
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

import handoff as h

ROOT = Path(__file__).resolve().parent
SOURCES = ("backup_roundtrip.py", *h.SOURCES)
EXPECTED_BUNDLE = "461fb7ad53f77879bbc6cf5554002e5578b5a75fc40de418f7c8216b03ab0ff4"
EXPECTED_REPORT = "68d7ef0a660bfb3e0a38400c7dd44c83f6512e87fb9877c4675defe66ba0528e"
BUNDLE_BYTES = 21328
PREFIX = "radar-b2:solana-radar-backups-redeye-2026/r1-rehearsal/"
CONFIG = "/etc/solana-radar/rclone.conf"
SUDO, TIMEOUT, RCLONE = "/usr/bin/sudo", "/usr/bin/timeout", "/usr/local/bin/rclone"
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"}


def pins():
    return {name: h.c.digest((ROOT/name).read_bytes()) for name in SOURCES}


def trusted_programs():
    for value in (SUDO, TIMEOUT, RCLONE):
        path = Path(value).resolve(strict=True)
        if not path.is_file(): raise h.c.CaptureError("missing-executable")
        for member in (path, *path.parents):
            st = member.stat()
            if st.st_uid != 0 or st.st_mode & 0o022:
                raise h.c.CaptureError("unsafe-executable")


class Transfer:
    """No user-controlled shell, endpoint, config, local filename or environment."""
    def __init__(self):
        self.calls = []
        self.deadline = time.monotonic() + 135
        self.remote = None
        self.stopped = False

    def run(self, operation, remote=None, payload=None):
        if self.stopped or len(self.calls) >= 3 or time.monotonic() >= self.deadline:
            raise h.c.CaptureError("transfer-budget")
        if operation != ("backend", "upload", "download")[len(self.calls)]:
            raise h.c.CaptureError("transfer-order")
        if operation == "backend":
            if remote is not None or payload is not None: raise h.c.CaptureError("backend-params")
            args = ["listremotes", "--long"]
        else:
            if (not isinstance(remote, str) or not remote.startswith(PREFIX)
                    or not re.fullmatch(r"handoff-[0-9a-f]{32}-"+EXPECTED_BUNDLE[:12]+r"\.zip", remote[len(PREFIX):])):
                raise h.c.CaptureError("remote-scope")
            if operation == "upload":
                if type(payload) is not bytes or len(payload) != BUNDLE_BYTES or h.c.digest(payload) != EXPECTED_BUNDLE:
                    raise h.c.CaptureError("upload-scope")
                self.remote = remote
                args = ["rcat", remote, "--size", str(BUNDLE_BYTES)]
            else:
                if remote != self.remote or payload is not None: raise h.c.CaptureError("download-scope")
                args = ["cat", remote, "--count", str(BUNDLE_BYTES+1)]
        remaining = min(40, max(1, int(self.deadline-time.monotonic())-3))
        command = [SUDO, "-n", TIMEOUT, "--signal=TERM", "--kill-after=2s", str(remaining)+"s", RCLONE,
                   "--config", CONFIG, "--transfers", "1", "--checkers", "1", "--buffer-size", "64Ki",
                   "--b2-chunk-size", "8Mi", "--b2-upload-concurrency", "1",
                   "--retries", "1", "--low-level-retries", "1", "--contimeout", "10s", "--timeout", "20s",
                   "--max-transfer", "64Ki", "--log-level", "ERROR", *args]
        call = {"operation": operation, "state": "attempted"}
        self.calls.append(call)
        try:
            response = subprocess.run(command, input=payload if payload is not None else b"",
                                      stdout=subprocess.DEVNULL if operation == "upload" else subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, env=ENV, timeout=remaining+4, check=False)
            if response.returncode != 0:
                raise h.c.CaptureError("subprocess-failed")
            raw = response.stdout or b""
            cap = 4096 if operation == "backend" else BUNDLE_BYTES+1
            if len(raw) > cap: raise h.c.CaptureError("subprocess-output-cap")
            call["state"] = "completed"
            return raw
        except Exception:
            call["state"] = "failed"
            self.stopped = True
            raise h.c.CaptureError("transfer-failed") from None


def run(bundle, report_path, output):
    source_pins = pins()
    raw = h.read_private(bundle, BUNDLE_BYTES)
    report_raw = h.read_private(report_path, 16384)
    if (len(raw) != BUNDLE_BYTES or h.c.digest(raw) != EXPECTED_BUNDLE
            or h.c.digest(report_raw) != EXPECTED_REPORT):
        raise h.c.CaptureError("accepted-synthetic-inputs-required")
    original = h.c.strict_json(report_raw)
    if original["source_sha256"] != h.source_pins(): raise h.c.CaptureError("handoff-source-changed")
    out = h.path_without_links(output)
    out.mkdir(mode=0o700)
    # Validate a private frozen copy before invoking privileged rclone. Rclone
    # receives only these already-validated bytes on stdin, never a user path.
    h.c.exclusive_file(out/"source.zip", raw)
    preflight = h.restore_capture(out/"source.zip", EXPECTED_BUNDLE, out/"preflight")
    if preflight["capture"] != original["capture"]: raise h.c.CaptureError("preflight-replay")
    remote = PREFIX + "handoff-" + uuid.uuid4().hex + "-" + EXPECTED_BUNDLE[:12] + ".zip"
    transfer = Transfer()
    result = {"schema_version": 1, "status": "synthetic-backup-roundtrip-unavailable",
              "source_sha256": source_pins, "source_report_sha256": EXPECTED_REPORT,
              "bundle_sha256": EXPECTED_BUNDLE, "bundle_bytes": BUNDLE_BYTES, "synthetic_only": True,
              "remote_object": remote, "configured_backend_b2": False,
              "backup_credentials_access_attempted": False, "credentials_loaded_by_python": False,
              "remote_upload_completed": False, "remote_download_verified": False,
              "downloaded_capture_replayed": False, "production_backup_coverage_verified": False,
              "ongoing_retention_verified": False, "remote_deletions": 0,
              "paid_feed_activated": False, "transactions_sent": 0,
              "capture": preflight["capture"], "calls": transfer.calls}
    try:
        trusted_programs()
        result["backup_credentials_access_attempted"] = True
        metadata = transfer.run("backend")
        rows = [line.split() for line in metadata.decode("utf-8").splitlines()]
        matches = [row for row in rows if row and row[0] == "radar-b2:"]
        if len(matches) != 1 or len(matches[0]) < 2 or matches[0][1] != "b2":
            raise h.c.CaptureError("backend-not-b2")
        result["configured_backend_b2"] = True
        transfer.run("upload", remote, raw)
        result["remote_upload_completed"] = True
        downloaded = transfer.run("download", remote)
        if downloaded != raw: raise h.c.CaptureError("download-differs")
        h.c.exclusive_file(out/"downloaded.zip", downloaded)
        restored = h.restore_capture(out/"downloaded.zip", EXPECTED_BUNDLE, out/"restored")
        if restored["capture"] != original["capture"]: raise h.c.CaptureError("download-replay")
        result.update(remote_download_verified=True, downloaded_capture_replayed=True,
                      status="synthetic-backup-roundtrip-passed-live-blocked")
    except Exception:
        # Even failed uploads may have created an object; never retry/delete it.
        pass
    result["remote_object_may_exist"] = any(c["operation"] == "upload" for c in transfer.calls)
    if (pins() != source_pins or h.read_private(bundle, BUNDLE_BYTES) != raw
            or h.read_private(report_path, 16384) != report_raw):
        raise h.c.CaptureError("source-changed")
    h.c.exclusive_file(out/"report.json", (h.c.canonical(result)+"\n").encode())
    h.c.sync_dir(out); h.c.sync_dir(out.parent)
    return result


def main(argv=None):
    try:
        parser = h.Parser(description=__doc__)
        for name in ("bundle", "handoff-report", "output-directory"):
            parser.add_argument("--"+name, required=True)
        parser.add_argument("--round-trip-b2", action="store_true", required=True)
        args = parser.parse_args(argv)
        result = run(args.bundle, args.handoff_report, args.output_directory)
        print("R1 synthetic backup:", result["status"], "— full R1 remains blocked.")
        return 0
    except Exception:
        print("R1 synthetic backup stopped; no acceptance granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
