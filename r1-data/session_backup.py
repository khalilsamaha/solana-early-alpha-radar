"""One explicit B2 round trip of the accepted synthetic complete-session archive."""
from pathlib import Path
import sys
import uuid

import backup_roundtrip as transfer
import capture as c
import handoff as h
import session_bundle as bundle_format

ROOT = Path(__file__).resolve().parent
SOURCES = ("session_backup.py", "backup_roundtrip.py", *bundle_format.SOURCES)
EXPECTED_BUNDLE = "f055648fdd804d29c1dfb25087c32314667b27fddb3adbf48db27e6617eb023d"
EXPECTED_REPORT = "2fe0273ec7850d5ceec9091f76bd57d6e72adddb5355558b4ef300ee81ed3196"
BUNDLE_BYTES = 27148


def pins():
    return {name: c.digest((ROOT / name).read_bytes()) for name in SOURCES}


class SessionTransfer(transfer.Transfer):
    """Reuse the bounded command runner with a fixed distinct artifact identity."""
    def __init__(self):
        super().__init__()
        self.expected_bundle = EXPECTED_BUNDLE
        self.bundle_bytes = BUNDLE_BYTES
        self.object_label = "session"


def run(bundle, report_path, output):
    source_pins = pins()
    raw = h.read_private(bundle, BUNDLE_BYTES)
    report_raw = h.read_private(report_path, 16384)
    if (len(raw) != BUNDLE_BYTES or c.digest(raw) != EXPECTED_BUNDLE
            or c.digest(report_raw) != EXPECTED_REPORT):
        raise c.CaptureError("accepted-synthetic-session-required")
    original = c.strict_json(report_raw)
    receipt = original["supervision"]["worker_receipt"]
    if (original["status"] != "offline-session-bundle-passed-live-blocked"
            or original["tests"] != {"run": 275, "failures": 0, "errors": 0, "skipped": 0}
            or original["synthetic_only"] is not True
            or receipt["session_bundle_sha256"] != EXPECTED_BUNDLE
            or receipt["complete_session_replayed"] is not True
            or any(original["source_sha256"][k] != v for k, v in bundle_format.source_pins().items())):
        raise c.CaptureError("session-receipt-binding")
    out = h.path_without_links(output)
    out.mkdir(mode=0o700)
    c.exclusive_file(out / "source.zip", raw)
    # All bytes pass complete capture AND measurement replay before rclone can
    # access backup credentials. The privileged process never gets local paths.
    preflight = bundle_format.restore_session(out / "source.zip", EXPECTED_BUNDLE, out / "preflight")
    if preflight["measurement"] != receipt["measurement"]:
        raise c.CaptureError("session-preflight-mismatch")
    remote = transfer.PREFIX + "session-" + uuid.uuid4().hex + "-" + EXPECTED_BUNDLE[:12] + ".zip"
    client = SessionTransfer()
    result = {"schema_version": 1, "status": "synthetic-session-backup-unavailable",
              "source_sha256": source_pins, "source_report_sha256": EXPECTED_REPORT,
              "bundle_sha256": EXPECTED_BUNDLE, "bundle_bytes": BUNDLE_BYTES,
              "synthetic_only": True, "preservation_scope": "one-accepted-synthetic-complete-session",
              "remote_object": remote, "configured_backend_b2": False,
              "backup_credentials_access_attempted": False, "credentials_loaded_by_python": False,
              "remote_upload_completed": False, "remote_download_verified": False,
              "downloaded_capture_replayed": False, "downloaded_measurement_replayed": False,
              "production_backup_coverage_verified": False, "ongoing_retention_verified": False,
              "remote_deletions": 0, "paid_feed_activated": False, "transactions_sent": 0,
              "capture": preflight["capture"], "measurement": preflight["measurement"],
              "calls": client.calls}
    try:
        transfer.trusted_programs()
        result["backup_credentials_access_attempted"] = True
        metadata = client.run("backend")
        rows = [line.split() for line in metadata.decode("utf-8").splitlines()]
        matches = [row for row in rows if row and row[0] == "radar-b2:"]
        if len(matches) != 1 or len(matches[0]) < 2 or matches[0][1] != "b2":
            raise c.CaptureError("session-backend-not-b2")
        result["configured_backend_b2"] = True
        client.run("upload", remote, raw)
        result["remote_upload_completed"] = True
        downloaded = client.run("download", remote)
        if downloaded != raw:
            raise c.CaptureError("session-download-differs")
        c.exclusive_file(out / "downloaded.zip", downloaded)
        restored = bundle_format.restore_session(out / "downloaded.zip", EXPECTED_BUNDLE, out / "restored")
        if (restored["capture"] != preflight["capture"]
                or restored["measurement"] != receipt["measurement"]):
            raise c.CaptureError("session-download-replay")
        result.update(remote_download_verified=True, downloaded_capture_replayed=True,
                      downloaded_measurement_replayed=True,
                      status="synthetic-session-backup-passed-live-blocked")
    except Exception:
        # The object may exist after an uncertain upload. Retain the diagnostic;
        # never retry, overwrite, delete or silently fall back to another remote.
        pass
    result["remote_object_may_exist"] = any(call["operation"] == "upload" for call in client.calls)
    if (pins() != source_pins or h.read_private(bundle, BUNDLE_BYTES) != raw
            or h.read_private(report_path, 16384) != report_raw):
        raise c.CaptureError("session-backup-source-changed")
    c.exclusive_file(out / "report.json", (c.canonical(result) + "\n").encode())
    c.sync_dir(out)
    c.sync_dir(out.parent)
    return result


def main(argv=None):
    try:
        parser = h.Parser(description=__doc__)
        for name in ("bundle", "acceptance-report", "output-directory"):
            parser.add_argument("--" + name, required=True)
        parser.add_argument("--round-trip-b2", action="store_true", required=True)
        args = parser.parse_args(argv)
        result = run(args.bundle, args.acceptance_report, args.output_directory)
        print("R1 complete-session backup:", result["status"], "— full R1 remains blocked.")
        # As with the earlier probe, zero means a diagnostic was retained.
        # Only the explicit passed status grants this narrow round-trip result.
        return 0
    except Exception:
        print("R1 complete-session backup stopped; no acceptance granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
