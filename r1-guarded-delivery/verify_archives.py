"""Recover the six accepted guarded fixtures from two previously delivered archives."""
import argparse
from dataclasses import dataclass
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import zipfile

import local_transfer as transfer


@dataclass(frozen=True)
class Batch:
    revision: str
    size: int
    sha256: str
    index_sha256: str


BATCHES = (
    Batch(transfer.FIRST, 1514293,
          "8f9e6b570f534366fe93bc85c44b250c6d02cdaaf10b6bf0d26eb2f2b1e68d12",
          "4912aa509ca635c3f89b845087d11293d964187481a2fa2004e95b2d690a9c94"),
    Batch(transfer.REMAINING, 2505562,
          "e9976b068f7c91c2fab51020d2a8659ad18fbaba1741cc8a51820e7bfa766d27",
          "a05df2ea97001e22b248c23bce927e4cc0c4daa1abaffb149f1924c92b71dbb1"),
)


def recover_batch(path, batch):
    raw = transfer.read_private(path, batch.size)
    if len(raw) != batch.size or transfer.digest(raw) != batch.sha256:
        raise transfer.CaptureError("archive-length-or-digest")

    cases = {k: f for k, f in transfer.FIXTURES.items() if f.revision == batch.revision}
    results = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        index = archive.read("members.json")
        if transfer.digest(index) != batch.index_sha256:
            raise transfer.CaptureError("member-index-digest")
        members = json.loads(index)["members"]
        with transfer.pinned_reader(next(iter(cases.values()))) as reader:
            for name, fixture in cases.items():
                member = name + "/handoff/evidence.zip"
                if members[member] != {"bytes": fixture.size, "sha256": fixture.sha256}:
                    raise transfer.CaptureError("indexed-package-identity")
                with tempfile.TemporaryDirectory(prefix="r1b-received-") as scratch:
                    package = Path(scratch) / "package.zip"
                    transfer.exclusive_file(package, archive.read(member))
                    _, report_digest = transfer.review(package, fixture, reader)
                results[name] = {"bytes": fixture.size, "sha256": fixture.sha256,
                                 "verdict": fixture.verdict, "reader_report_sha256": report_digest}

    return {"archive_sha256": batch.sha256, "archive_bytes": batch.size,
            "member_index_sha256": batch.index_sha256, "producer_revision": batch.revision,
            "reader_tree": transfer.READER_TREES[batch.revision], "cases": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_archive", type=Path)
    parser.add_argument("remaining_archive", type=Path)
    args = parser.parse_args(argv)
    try:
        batches = [recover_batch(path, batch)
                   for path, batch in zip((args.first_archive, args.remaining_archive), BATCHES, strict=True)]
    except (transfer.CaptureError, OSError, ValueError, KeyError, tarfile.TarError,
            zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        reason = str(exc) if isinstance(exc, transfer.CaptureError) else type(exc).__name__
        print(transfer.canonical({"status": "restore-unverified", "reason": reason}))
        return 1
    # Storage provenance comes from the retrieval record, never from the input path.
    print(transfer.canonical({"schema": 1, "status": "six-fixture-restore-verified",
                              "batches": batches, "retention_verified": False,
                              "storage_policy_verified": False, "activation_authorized": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
