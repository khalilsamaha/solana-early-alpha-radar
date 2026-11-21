"""Exercise local publication and recovery with disposable evidence and a stub reader."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import local_transfer as transfer


class TransferTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.raw = b"offline handoff fixture"
        self.package = self.root / "source.zip"
        transfer.exclusive_file(self.package, self.raw)
        self.reader = self.root / "reader.py"
        self.reader.write_text(
            "import hashlib, json, pathlib, sys\n"
            "raw = pathlib.Path(sys.argv[2]).read_bytes()\n"
            "print(json.dumps({'status':'verified-historical-offline-evidence',"
            "'sha256':hashlib.sha256(raw).hexdigest(),"
            "'assessment':{'classification':'quarantined-handoff-evidence'},"
            "'activation_authorized':False}))\n"
            "sys.exit(2)\n"
        )
        self.fixture = transfer.Fixture("test-source", len(self.raw), transfer.digest(self.raw), transfer.QUARANTINE)
        self.attempt, self.destination = transfer.locations(self.root, self.fixture)

    def rehearse(self):
        return transfer.rehearse(self.root, self.fixture, self.package, self.reader)

    def inspect(self):
        return transfer.inspect(self.root, self.fixture, self.reader)

    def snapshot(self):
        return {p.name: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def assert_consumed(self):
        before = self.snapshot()
        with self.assertRaises(FileExistsError):
            self.rehearse()
        self.assertEqual(self.snapshot(), before)

    def interrupt_after(self, name):
        write = transfer.exclusive_file
        def cut_power(path, data):
            write(path, data)
            if path.name == name:
                os._exit(73)
        child = os.fork()
        if child == 0:
            try:
                with patch.object(transfer, "exclusive_file", cut_power):
                    self.rehearse()
            finally:
                os._exit(74)
        self.assertEqual(os.waitstatus_to_exitcode(os.waitpid(child, 0)[1]), 73)
        self.assertFalse((self.attempt / "completion.json").exists())
        with self.assertRaisesRegex(transfer.CaptureError, "incomplete-attempt"):
            self.inspect()
        self.assert_consumed()

    def test_death_after_staging(self):
        self.interrupt_after(self.destination.name)
        self.assertEqual(self.destination.read_bytes(), self.raw)
        self.assertFalse((self.attempt / "retrieved.zip").exists())

    def test_death_after_retrieval(self):
        self.interrupt_after("retrieved.zip")
        self.assertEqual((self.attempt / "retrieved.zip").read_bytes(), self.raw)

    def test_existing_destination_is_preserved(self):
        transfer.exclusive_file(self.destination, b"previous object")
        with self.assertRaises(FileExistsError):
            self.rehearse()
        self.assertEqual(self.destination.read_bytes(), b"previous object")
        self.assertTrue((self.attempt / "intent.json").is_file())
        self.assert_consumed()

    def test_racing_publishers_only_one_can_finish(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(self.rehearse) for _ in range(2)]
        self.assertEqual(sum(job.exception() is None for job in jobs), 1)
        self.assertEqual(sum(isinstance(job.exception(), FileExistsError) for job in jobs), 1)
        result = self.inspect()
        self.assertEqual(result["handoff_verdict"], transfer.QUARANTINE)
        self.assertFalse(result["activation_authorized"])
        self.assertFalse(result["remote_preservation_verified"])

    def test_wrong_source_does_not_consume_attempt(self):
        self.package.write_bytes(self.raw[:-1])
        with self.assertRaisesRegex(transfer.CaptureError, "package-length-or-digest"):
            self.rehearse()
        self.assertFalse(self.attempt.exists())
        self.assertFalse(self.destination.exists())

    def test_damage_during_retrieval_cannot_publish_completion(self):
        write = transfer.exclusive_file
        def damage_copy(path, data):
            write(path, data[:-1] if path.name == "retrieved.zip" else data)
        with patch.object(transfer, "exclusive_file", damage_copy):
            with self.assertRaisesRegex(transfer.CaptureError, "package-length-or-digest"):
                self.rehearse()
        self.assertFalse((self.attempt / "completion.json").exists())
        self.assertEqual(self.destination.read_bytes(), self.raw)
        self.assert_consumed()

    def test_invalid_stored_state_cannot_verify(self):
        result = self.rehearse()
        self.assertEqual(self.inspect(), result)
        for path in (self.attempt / "intent.json", self.attempt / "retrieved.zip",
                     self.destination, self.attempt / "completion.json"):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original[:-1])
                with self.assertRaises(transfer.CaptureError):
                    self.inspect()
                self.assertEqual(path.read_bytes(), original[:-1])
                path.write_bytes(original)
        self.assert_consumed()


if __name__ == "__main__":
    unittest.main()
