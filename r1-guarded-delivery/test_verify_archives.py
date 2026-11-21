"""Wrong, partial and altered deliveries must never produce a batch success report."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import verify_archives as receiver

transfer = receiver.transfer


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "received.zip"
        self.package = b"small fixture"
        self.fixture = transfer.Fixture("revision", len(self.package), transfer.digest(self.package),
                                        transfer.QUARANTINE)
        self.member = "case/handoff/evidence.zip"

    def archive(self, indexed_size):
        index = transfer.receipt({"members": {self.member: {"bytes": indexed_size,
                                                            "sha256": self.fixture.sha256}}})
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("members.json", index)
            archive.writestr(self.member, self.package)
        raw = buffer.getvalue()
        transfer.exclusive_file(self.path, raw)
        return receiver.Batch("revision", len(raw), transfer.digest(raw), transfer.digest(index))

    def test_corrupt_archive_refused_before_reader(self):
        batch = self.archive(self.fixture.size)
        damaged = bytearray(self.path.read_bytes())
        damaged[-1] ^= 1
        self.path.write_bytes(damaged)
        with patch.object(transfer, "pinned_reader") as reader:
            with self.assertRaisesRegex(transfer.CaptureError, "archive-length-or-digest"):
                receiver.recover_batch(self.path, batch)
            reader.assert_not_called()

    def test_mismatched_member_identity_prevents_replay(self):
        batch = self.archive(self.fixture.size + 1)
        with (patch.dict(transfer.FIXTURES, {"case": self.fixture}, clear=True),
              patch.object(transfer, "pinned_reader"), patch.object(transfer, "review") as replay):
            with self.assertRaisesRegex(transfer.CaptureError, "indexed-package-identity"):
                receiver.recover_batch(self.path, batch)
            replay.assert_not_called()

    def test_second_archive_failure_has_no_partial_success_receipt(self):
        output = io.StringIO()
        with (patch.object(receiver, "recover_batch",
                           side_effect=[{"cases": {"first": {}}}, transfer.CaptureError("archive-length-or-digest")]),
              redirect_stdout(output)):
            self.assertEqual(receiver.main(["one.zip", "two.zip"]), 1)
        self.assertEqual(json.loads(output.getvalue()),
                         {"status": "restore-unverified", "reason": "archive-length-or-digest"})
