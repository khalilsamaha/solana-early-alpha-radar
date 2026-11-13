import asyncio
import fcntl
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import archive as a
import fixtures
import session as s
from capture import CaptureError, digest, exclusive_file


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='r1-archive-test-')
        self.root = Path(self.tmp.name)
        asyncio.run(fixtures.exercise(self.root/'run'))
        self.control = self.root/'run/control'

    def tearDown(self):
        self.tmp.cleanup()

    def export(self):
        report = a.export(self.control, self.root/'archive')
        return report, (self.root/'archive/archive.zip').read_bytes()

    def rebind(self, contents):
        declared = a.row(contents['manifest.json'])
        declared['members'] = {k: {'bytes': len(v), 'sha256': digest(v)}
                               for k, v in contents.items() if k != 'manifest.json'}
        contents['manifest.json'] = s.json_bytes(declared)
        return a.pack(contents)

    def test_complete_roundtrip_binds_arbitrary_capture_and_receipts(self):
        originals = {str(p.relative_to(self.control)): p.read_bytes()
                     for p in self.control.rglob('*') if p.is_file()}
        report, raw = self.export()
        restored = a.restore(self.root/'archive/archive.zip', report['archive_sha256'], self.root/'restored')
        self.assertEqual(restored['assessment'], report['assessment'])
        self.assertEqual(report['archive_bytes'], len(raw))
        self.assertFalse(restored['assessment']['unix_peer_uid_verified'])
        for key in ('live_launch_authorized', 'retention_verified', 'remote_preservation_verified', 'provider_origin_attested'):
            self.assertFalse(restored['assessment'][key])
        self.assertEqual(originals, {str(p.relative_to(self.control)): p.read_bytes()
                                    for p in self.control.rglob('*') if p.is_file()})
        for p in (self.root/'restored').rglob('*'):
            self.assertEqual(p.stat().st_mode & 0o777, 0o700 if p.is_dir() else 0o600)

    def test_distinct_session_sizes_and_hashes_are_supported(self):
        first, _ = self.export()
        asyncio.run(fixtures.exercise(self.root/'second', messages=9))
        second = a.export(self.root/'second/control', self.root/'second-archive')
        self.assertNotEqual(first['archive_sha256'], second['archive_sha256'])
        self.assertNotEqual(first['archive_bytes'], second['archive_bytes'])
        a.restore(self.root/'second-archive/archive.zip', second['archive_sha256'], self.root/'second-restore')

    def test_watch_expiry_replays_subscribe_and_unsubscribe_as_distinct_counts(self):
        from dataclasses import asdict
        import contract
        from capture import Limits
        from measurement import replay
        asyncio.run(fixtures.exercise(self.root/'expiry', 'watch-expiry'))
        measured = replay(self.root/'expiry/control/capture', self.root/'expiry/control/session.jsonl')
        self.assertEqual(measured['local_sends_completed'], 2)
        self.assertEqual(measured['creation_receive_to_local_send_return_ns']['count'], 1)
        evaluation = contract.assess(measured, asdict(Limits(messages=4, seconds=3, sample_modulus=1, watch_seconds=1)), contract.proposal())
        self.assertEqual(evaluation['local_completion_fraction'], {'numerator': 1, 'denominator': 1})
        report = a.export(self.root/'expiry/control', self.root/'expiry-archive')
        a.restore(self.root/'expiry-archive/archive.zip', report['archive_sha256'], self.root/'expiry-restore')

    def test_failed_sessions_remain_failed_after_complete_evidence_restore(self):
        for mode in ('cleanup-failure', 'send-failure', 'provider-failure', 'operator-stop', 'idle'):
            with self.subTest(mode=mode):
                asyncio.run(fixtures.exercise(self.root/mode, mode))
                report = a.export(self.root/mode/'control', self.root/(mode+'-archive'))
                restored = a.restore(self.root/(mode+'-archive/archive.zip'), report['archive_sha256'], self.root/(mode+'-restore'))
                self.assertEqual(restored['assessment'], report['assessment'])
                self.assertEqual(restored['assessment']['local_session_outcome'] == 'capture-stopped', mode == 'idle')

    def test_missing_stop_receipt_is_not_repaired_or_promoted(self):
        (self.control/'stopped.json').unlink()
        with self.assertRaises(CaptureError):
            self.export()
        self.assertFalse((self.root/'archive').exists())
        self.assertFalse((self.control/'stopped.json').exists())

    def test_live_lock_or_sqlite_rollback_prevents_export(self):
        with (self.control/'capture.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(CaptureError): self.export()
        exclusive_file(self.control/'capture/ticks.db-journal', b'uncertain')
        with self.assertRaises(CaptureError): self.export()
        self.assertEqual((self.control/'capture/ticks.db-journal').read_bytes(), b'uncertain')
        self.assertFalse((self.root/'archive').exists())

    def test_false_shutdown_and_different_limits_are_rejected_even_rehashed(self):
        _, raw = self.export()
        for filename, field, value in (('stopped.json', 'capture_thread_joined', False),
                                       ('stopped.json', 'admission_sha256', '0'*64),
                                       ('admission.json', 'live_launch_authorized', True)):
            contents = a.unpack(raw)
            row = a.row(contents[filename]); row[field] = value
            contents[filename] = s.json_bytes(row)
            changed = self.rebind(contents)
            with self.assertRaises(CaptureError): a.verify(changed, digest(changed))
        contents = a.unpack(raw)
        admission = a.row(contents['admission.json']); admission['limits']['messages'] = 19
        contents['admission.json'] = s.json_bytes(admission)
        stopped = a.row(contents['stopped.json']); stopped['admission_sha256'] = digest(contents['admission.json'])
        contents['stopped.json'] = s.json_bytes(stopped)
        changed = self.rebind(contents)
        with self.assertRaises(CaptureError): a.verify(changed, digest(changed))

    def test_removed_owner_send_is_detected_against_durable_journal(self):
        _, raw = self.export()
        contents = a.unpack(raw)
        stopped = a.row(contents['stopped.json']); stopped['owner']['commands'].pop(2)
        contents['stopped.json'] = s.json_bytes(stopped)
        changed = self.rebind(contents)
        with self.assertRaises(CaptureError): a.verify(changed, digest(changed))

    def test_unrelated_cleanup_cannot_claim_remaining_watch_was_closed(self):
        _, raw = self.export()
        contents = a.unpack(raw)
        stopped = a.row(contents['stopped.json'])
        stopped['owner']['commands'][-1]['command']['keys'] = ['1'*31+'3']
        contents['stopped.json'] = s.json_bytes(stopped)
        changed = self.rebind(contents)
        with self.assertRaises(CaptureError): a.verify(changed, digest(changed))

    def test_source_mutation_during_copy_review_cannot_publish_archive(self):
        export_session = a.b.export_session
        def mutate(*args):
            result = export_session(*args)
            with (self.control/'stopped.json').open('ab') as handle: handle.write(b' ')
            return result
        with patch.object(a.b, 'export_session', side_effect=mutate):
            with self.assertRaises(CaptureError): self.export()
        self.assertFalse((self.root/'archive').exists())

    def test_external_checksum_source_drift_and_trailing_zip_bytes_rejected(self):
        _, raw = self.export()
        with self.assertRaises(CaptureError): a.verify(raw, '0'*64)
        with patch.object(s, 'pins', return_value={}):
            with self.assertRaises(CaptureError): a.verify(raw, digest(raw))
        with self.assertRaises(CaptureError): a.verify(raw+b'x', digest(raw+b'x'))

    def test_archive_lock_and_operator_wrapper_are_in_source_binding(self):
        pins = s.pins()
        for name in ('r1-preservation/preserve.py', 'scripts/r1-session-kali.sh',
                     'r1-data/session_bundle.py', 'r1-session/archive.py'):
            self.assertEqual(pins[name], digest((s.REPO/name).read_bytes()))

    def test_directory_bound_checked_before_zip_allocation(self):
        _, raw = self.export()
        end = list(struct.unpack('<4s4H2LH', raw[-22:])); end[3] = end[4] = 65535
        changed = raw[:-22] + struct.pack('<4s4H2LH', *end)
        with patch.object(a.zipfile, 'ZipFile', side_effect=AssertionError('must reject first')):
            with self.assertRaises(CaptureError): a.unpack(changed)

    def test_alias_nested_output_and_output_reuse_are_refused(self):
        alias = self.root/'alias'; alias.symlink_to(self.control)
        with self.assertRaises(CaptureError): a.export(alias, self.root/'export')
        with self.assertRaises(CaptureError): a.export(self.control, self.control/'nested')
        self.export()
        original = (self.root/'archive/archive.zip').read_bytes()
        with self.assertRaises(CaptureError): self.export()
        self.assertEqual((self.root/'archive/archive.zip').read_bytes(), original)

    def test_low_disk_or_final_receipt_failure_never_claims_completion(self):
        usage = a.shutil.disk_usage(self.root)
        with patch.object(a.shutil, 'disk_usage', return_value=usage._replace(free=0)):
            with self.assertRaises(CaptureError): self.export()
        write = a.exclusive_file
        def fail(path, raw):
            if path.name == 'report.json': raise OSError('synthetic')
            return write(path, raw)
        with patch.object(a, 'exclusive_file', side_effect=fail):
            with self.assertRaises(OSError): self.export()
        self.assertFalse((self.root/'archive/report.json').exists())
        self.assertTrue((self.root/'archive/archive.zip').exists())


if __name__ == '__main__':
    unittest.main()
