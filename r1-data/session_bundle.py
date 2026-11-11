"""Offline complete-session handoff: capture package plus measurement journal."""
import argparse
import io
from pathlib import Path
import re
import stat
import struct
import sys
import tempfile
import zipfile

import capture as c
import handoff as h
import measurement as m

ROOT = Path(__file__).resolve().parent
SOURCES = ("session_bundle.py", "capture.py", "handoff.py", "measurement.py", "rpc_probe.py", "source_probe.py")
MEMBERS = {"capture.zip": h.MAX_PACKAGE, "session.jsonl": m.MAX_BYTES, "binding.json": 65_536}
MAX_PACKAGE = sum(MEMBERS.values()) + 4096
KIND = "r1-capture-measurement-pair-v1"


def source_pins():
    return {name: c.digest((ROOT / name).read_bytes()) for name in SOURCES}


def pack(contents):
    if (set(contents) != set(MEMBERS)
            or any(type(raw) is not bytes or not 1 <= len(raw) <= MEMBERS[name] for name, raw in contents.items())):
        raise c.CaptureError("session-members")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in MEMBERS:
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(entry, contents[name])
    raw = stream.getvalue()
    if len(raw) > MAX_PACKAGE:
        raise c.CaptureError("session-package-limit")
    return raw


def unpack(raw):
    # Check the bounded ordinary-ZIP directory before ZipFile allocates entries.
    if not 22 <= len(raw) <= MAX_PACKAGE or not raw.startswith(b"PK\x03\x04"):
        raise c.CaptureError("session-envelope")
    end = struct.unpack("<4s4H2LH", raw[-22:])
    if (end[:5] != (b"PK\x05\x06", 0, 0, 3, 3) or end[7] != 0
            or not 1 <= end[5] <= 1024 or end[6] + end[5] != len(raw) - 22):
        raise c.CaptureError("session-directory")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) != 3 or {e.filename for e in entries} != set(MEMBERS) or archive.comment:
            raise c.CaptureError("session-members")
        for entry in entries:
            if (entry.compress_type != zipfile.ZIP_STORED or entry.flag_bits != 0
                    or entry.extra or entry.comment or entry.create_system != 3
                    or entry.external_attr >> 16 != stat.S_IFREG | 0o600
                    or not 1 <= entry.file_size <= MEMBERS[entry.filename]
                    or entry.compress_size != entry.file_size):
                raise c.CaptureError("session-member-format")
        contents = {e.filename: archive.read(e) for e in entries}
    # Reject ignored prefixes/trailers, overlapping/local-header aliases and
    # noncanonical metadata as well as ordinary CRC/member errors.
    if raw != pack(contents):
        raise c.CaptureError("session-noncanonical")
    binding = c.strict_json(contents["binding.json"])
    if (set(binding) != {"schema_version", "kind", "capture_bundle_sha256", "journal_sha256",
                         "capture", "measurement", "producer_source_sha256"}
            or type(binding["schema_version"]) is not int or binding["schema_version"] != 1
            or binding["kind"] != KIND or binding["producer_source_sha256"] != source_pins()
            or binding["capture_bundle_sha256"] != c.digest(contents["capture.zip"])
            or binding["journal_sha256"] != c.digest(contents["session.jsonl"])):
        raise c.CaptureError("session-binding")
    return contents, binding


def restore_bytes(raw, output):
    contents, binding = unpack(raw)
    out = h.path_without_links(output)
    out.mkdir(mode=0o700)
    # Only these fixed file names are written; no archive-path extraction API.
    c.exclusive_file(out / "capture.zip", contents["capture.zip"])
    c.exclusive_file(out / "session.jsonl", contents["session.jsonl"])
    c.exclusive_file(out / "binding.json", contents["binding.json"])
    restored = h.restore_capture(out / "capture.zip", binding["capture_bundle_sha256"], out / "capture-restore")
    measured = m.replay(out / "capture-restore" / "restored", out / "session.jsonl")
    if restored["capture"] != binding["capture"] or measured != binding["measurement"]:
        raise c.CaptureError("session-replay-mismatch")
    return binding


def finish(out, raw, binding, pins, *, operation):
    if source_pins() != pins:
        raise c.CaptureError("session-source-changed")
    report = {"schema_version": 1, "status": "session-" + operation + "-replayed-live-blocked",
              "bundle_sha256": c.digest(raw), "bundle_bytes": len(raw),
              "source_sha256": pins, "capture": binding["capture"], "measurement": binding["measurement"],
              "capture_and_journal_replayed": True, "source_preserved": True,
              "network_used": False, "credentials_loaded": False, "paid_collection_enabled": False,
              "remote_upload_performed": False, "remote_download_verified": False,
              "off_machine_restore_verified": False}
    c.exclusive_file(out / "report.json", (c.canonical(report) + "\n").encode())
    c.sync_dir(out)
    c.sync_dir(out.parent)
    return report


def export_session(capture, journal, output):
    capture, journal, out = map(h.path_without_links, (capture, journal, output))
    if out == capture or capture in out.parents:
        raise c.CaptureError("session-output-inside-capture")
    pins = source_pins()
    original_db = h.read_private(capture / "ticks.db", c.MAX_DB)
    original_journal = h.read_private(journal, m.MAX_BYTES)
    measured = m.replay(capture, journal)
    out.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".session-export-", dir=out) as tmp:
        root = Path(tmp)
        captured = h.export_capture(capture, root / "capture-export")
        captured_bytes = h.read_private(root / "capture-export" / "capture.zip", h.MAX_PACKAGE)
        binding = {"schema_version": 1, "kind": KIND, "capture_bundle_sha256": c.digest(captured_bytes),
                   "journal_sha256": c.digest(original_journal), "capture": captured["capture"],
                   "measurement": measured, "producer_source_sha256": pins}
        raw = pack({"capture.zip": captured_bytes, "session.jsonl": original_journal,
                    "binding.json": (c.canonical(binding) + "\n").encode()})
        if restore_bytes(raw, root / "replayed") != binding:
            raise c.CaptureError("session-replay-mismatch")
    if (h.read_private(capture / "ticks.db", c.MAX_DB) != original_db
            or h.read_private(journal, m.MAX_BYTES) != original_journal):
        raise c.CaptureError("session-input-changed")
    c.exclusive_file(out / "session.zip", raw)
    if h.read_private(out / "session.zip", MAX_PACKAGE) != raw:
        raise c.CaptureError("session-output-changed")
    return finish(out, raw, binding, pins, operation="export")


def restore_session(bundle, expected_sha256, output):
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise c.CaptureError("session-external-checksum-required")
    pins = source_pins()
    raw = h.read_private(bundle, MAX_PACKAGE)
    if c.digest(raw) != expected_sha256:
        raise c.CaptureError("session-transfer-checksum")
    out = h.path_without_links(output)
    binding = restore_bytes(raw, out)
    if h.read_private(bundle, MAX_PACKAGE) != raw:
        raise c.CaptureError("session-input-changed")
    return finish(out, raw, binding, pins, operation="restore")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise c.CaptureError("session-invalid-arguments")


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        modes = parser.add_subparsers(dest="mode", required=True, parser_class=Parser)
        export = modes.add_parser("export")
        export.add_argument("--capture", required=True)
        export.add_argument("--journal", required=True)
        restore = modes.add_parser("restore")
        restore.add_argument("--bundle", required=True)
        restore.add_argument("--expected-sha256", required=True)
        for mode in (export, restore):
            mode.add_argument("--output-directory", required=True)
        args = parser.parse_args(argv)
        if args.mode == "export":
            export_session(args.capture, args.journal, args.output_directory)
        else:
            restore_session(args.bundle, args.expected_sha256, args.output_directory)
        print("Complete session replay passed; remote preservation and live use remain unverified.")
        return 0
    except Exception:
        print("Complete session handoff stopped; no acceptance granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
