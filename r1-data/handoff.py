"""Offline capture export and restore handoff; no remote storage or credentials."""
import argparse
import io
import os
from pathlib import Path
import re
import stat
import struct
import sys
import tempfile
import zipfile

import capture as c

ROOT = Path(__file__).resolve().parent
SOURCES = ("handoff.py", "capture.py")
MAX_MANIFEST = 16_384
MAX_PACKAGE = c.MAX_DB + MAX_MANIFEST + 4096
MEMBERS = {"ticks.db": c.MAX_DB, "manifest.json": MAX_MANIFEST}


def path_without_links(value):
    path = Path(value).absolute()
    if path.resolve() != path:
        raise c.CaptureError("path-alias")
    return path


def read_private(path, cap):
    path = path_without_links(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.getuid() or before.st_mode & 0o077 or before.st_size > cap):
            raise c.CaptureError("unsafe-input")
        raw = handle.read(cap + 1)
        after = os.fstat(handle.fileno())
    identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    if len(raw) > cap or identity(before) != identity(after) or identity(after) != identity(path.lstat()):
        raise c.CaptureError("input-changed")
    return raw


def source_pins():
    return {name: c.digest((ROOT/name).read_bytes()) for name in SOURCES}


def report_fields(status, raw, capture_report, pins):
    return {"schema_version": 1, "status": status, "bundle_file": "capture.zip",
            "bundle_sha256": c.digest(raw), "bundle_bytes": len(raw),
            "capture": capture_report, "source_sha256": pins,
            "network_used": False, "credentials_loaded": False,
            "remote_upload_performed": False, "remote_download_verified": False,
            "off_machine_restore_verified": False, "paid_collection_enabled": False,
            "profitability_evaluated": False}


def finish(out, report, pins):
    if source_pins() != pins:
        raise c.CaptureError("source-changed")
    c.exclusive_file(out/"report.json", (c.canonical(report)+"\n").encode())
    c.sync_dir(out)
    c.sync_dir(out.parent)
    return report


def unpack(raw, destination):
    """Read only two fixed stored members; never extract caller-supplied paths."""
    if len(raw) > MAX_PACKAGE:
        raise c.CaptureError("package-cap")
    # Bound directory metadata before ZipFile allocates an entry for each member.
    # The writer emits ordinary single-disk ZIP with two entries and no comments.
    if len(raw) < 22 or not raw.startswith(b"PK\x03\x04"):
        raise c.CaptureError("package-envelope")
    end = struct.unpack("<4s4H2LH", raw[-22:])
    if (end[:5] != (b"PK\x05\x06", 0, 0, 2, 2) or end[7] != 0
            or not 1 <= end[5] <= 512 or end[6] + end[5] != len(raw)-22):
        raise c.CaptureError("package-directory")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if (len(entries) != 2 or {e.filename for e in entries} != set(MEMBERS)
                or archive.comment):
            raise c.CaptureError("package-members")
        for entry in entries:
            if (entry.compress_type != zipfile.ZIP_STORED or entry.flag_bits != 0
                    or entry.extra or entry.comment or entry.create_system != 3
                    or entry.external_attr >> 16 != (stat.S_IFREG | 0o600)
                    or not 1 <= entry.file_size <= MEMBERS[entry.filename]
                    or entry.compress_size != entry.file_size):
                raise c.CaptureError("package-format")
        contents = {entry.filename: archive.read(entry) for entry in entries}
    manifest = c.strict_json(contents["manifest.json"])
    if (set(manifest) != {"version", "database_sha256", "report"}
            or type(manifest["version"]) is not int or manifest["version"] != c.VERSION
            or manifest["database_sha256"] != c.digest(contents["ticks.db"])):
        raise c.CaptureError("manifest-binding")
    destination.mkdir(mode=0o700)
    for name, data in contents.items():
        c.exclusive_file(destination/name, data)
    return manifest


def package(archive):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as target:
        for name, cap in MEMBERS.items():
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o600) << 16
            target.writestr(entry, read_private(archive/name, cap))
    raw = stream.getvalue()
    if len(raw) > MAX_PACKAGE:
        raise c.CaptureError("package-cap")
    return raw


def export_capture(capture, output):
    capture, out = path_without_links(capture), path_without_links(output)
    if out == capture or capture in out.parents:
        raise c.CaptureError("output-inside-source")
    pins = source_pins()
    before = read_private(capture/"ticks.db", c.MAX_DB)
    # Exclusive output. Only a closed capture accepted by the core can export.
    out.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".handoff-", dir=out) as tmp:
        archive = Path(tmp)/"archive"
        manifest = c.export_capture(capture, archive)
        raw = package(archive)
        unpack(raw, Path(tmp)/"unpacked")
        actual = c.restore_capture(Path(tmp)/"unpacked", Path(tmp)/"restored")
        if actual != manifest["report"]:
            raise c.CaptureError("local-replay")
    if before != read_private(capture/"ticks.db", c.MAX_DB):
        raise c.CaptureError("source-capture-changed")
    c.exclusive_file(out/"capture.zip", raw)
    if read_private(out/"capture.zip", MAX_PACKAGE) != raw:
        raise c.CaptureError("retained-package-changed")
    report = report_fields("capture-export-ready-live-blocked", raw, actual, pins)
    report.update(source_database_preserved=True, local_restore_replay_verified=True)
    return finish(out, report, pins)


def restore_capture(bundle, expected_sha256, output):
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise c.CaptureError("expected-digest-required")
    pins = source_pins()
    raw = read_private(bundle, MAX_PACKAGE)
    if c.digest(raw) != expected_sha256:
        raise c.CaptureError("transfer-checksum")
    out = path_without_links(output)
    out.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".handoff-", dir=out) as tmp:
        archive = Path(tmp)/"archive"
        manifest = unpack(raw, archive)
        actual = c.restore_capture(archive, out/"restored")
        if c.digest(read_private(out/"restored/ticks.db", c.MAX_DB)) != manifest["database_sha256"]:
            raise c.CaptureError("restored-database-changed")
    if raw != read_private(bundle, MAX_PACKAGE):
        raise c.CaptureError("source-bundle-changed")
    report = report_fields("capture-restore-replayed-live-blocked", raw, actual, pins)
    # The restore doesn't copy or pretend to create the input bundle here.
    report.pop("bundle_file")
    report.update(expected_bundle_sha256=expected_sha256, transfer_bytes_match=True,
                  restored_database_sha256=manifest["database_sha256"],
                  local_restore_replay_verified=True, source_bundle_preserved=True)
    return finish(out, report, pins)


def rehearse(output):
    out = path_without_links(output)
    pins = source_pins()
    out.mkdir(mode=0o700)
    def frame(kind):
        return c.canonical({"txType": kind, "mint": "1"*31+"2", "signature": "2"*88}).encode()
    limits = c.Limits(messages=4, sample_modulus=1)
    with c.Capture(out/"source", limits) as source:
        source.receive(frame("create"))
        source.receive(frame("buy"))
    with c.Capture(out/"source", limits) as source:
        source.receive(frame("sell"))
        source.receive(frame("migration"))
    exported = export_capture(out/"source", out/"export")
    restored = restore_capture(out/"export/capture.zip", exported["bundle_sha256"], out/"restore")
    if (exported["capture"] != restored["capture"] or restored["capture"]["gaps"] != 1
            or restored["capture"]["messages"] != 4 or restored["capture"]["stop_reason"] != "message-limit"):
        raise c.CaptureError("rehearsal-disagrees")
    report = dict(exported)
    report.update(status="offline-handoff-rehearsal-passed-live-blocked", synthetic_only=True,
                  bundle_file="export/capture.zip", packaged_bytes_replayed_locally=True,
                  remote_round_trip_pending=True)
    return finish(out, report, pins)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise c.CaptureError("invalid-arguments")


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        modes = parser.add_subparsers(dest="mode", required=True, parser_class=Parser)
        export = modes.add_parser("export")
        export.add_argument("--capture", required=True)
        restore = modes.add_parser("restore")
        restore.add_argument("--bundle", required=True)
        restore.add_argument("--expected-sha256", required=True)
        rehearsal = modes.add_parser("rehearse")
        for mode in (export, restore, rehearsal):
            mode.add_argument("--output-directory", required=True)
        args = parser.parse_args(argv)
        if args.mode == "export":
            report = export_capture(args.capture, args.output_directory)
        elif args.mode == "restore":
            report = restore_capture(args.bundle, args.expected_sha256, args.output_directory)
        else:
            report = rehearse(args.output_directory)
        print("R1 capture handoff:", report["status"], "— remote preservation remains unverified.")
        return 0
    except Exception:
        print("R1 capture handoff stopped; no acceptance granted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
