"""Private snapshot and isolated restore tests with synthetic closed journals."""
import gzip
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
import evidence_backup as b
import test_readiness as fixture


class BackupCase(unittest.TestCase):
    setUpClass = classmethod(fixture.ReadinessCase.setUpClass.__func__)
    tearDownClass = classmethod(fixture.ReadinessCase.tearDownClass.__func__)
    tearDown = fixture.ReadinessCase.tearDown

    def setUp(self):
        fixture.ReadinessCase.setUp(self)
        self.parent = Path(self.tmp.name) / 'private-snapshots'; self.parent.mkdir(mode=0o700)
        self.snapshot = self.parent / 'snapshot-1'

    def capture(self): return b.capture(self.home, self.wallet, self.pool, self.snapshot)
    def verify(self): return b.verify(self.snapshot, self.wallet, self.pool)
    def source_bytes(self): return fixture.ReadinessCase.files(self)

    def test_capture_and_restore_exact_without_key_network_or_source_mutation(self):
        key = self.home / b.KEY; key.write_bytes(b'private synthetic key sentinel'); key.chmod(0o600)
        lifecycle = self.home / 'token-lifecycle-v1'; lifecycle.mkdir(mode=0o700)
        for name in ('source', 'destination'):
            key = lifecycle / (name + '.pk8'); key.write_bytes(b'private synthetic key sentinel'); key.chmod(0o600)
        before = self.source_bytes()
        original = b.private_file
        def read(path, cap):
            self.assertNotEqual(Path(path).suffix, '.pk8')
            return original(path, cap)
        with (patch.object(b, 'private_file', side_effect=read), patch('core.signer', side_effect=AssertionError('sign')),
              patch('urllib.request.urlopen', side_effect=AssertionError('network'))):
            first = self.capture(); second = self.verify()
        self.assertEqual(first['state'], 'isolated-restore-verified')
        self.assertEqual(first['manifestSha256'], second['manifestSha256'])
        self.assertEqual(before, self.source_bytes())
        self.assertEqual(b.inventory(self.snapshot / 'evidence'), b.inventory(self.home, source=True))
        self.assertFalse((self.snapshot / 'evidence' / b.KEY).exists())
        self.assertEqual(list((self.snapshot / 'evidence').rglob('*.pk8')), [])
        self.assertEqual(list(self.parent.glob('.restore-check-*')), [])

    def test_snapshot_is_private_and_repeat_capture_never_overwrites(self):
        self.capture(); before = (self.snapshot / b.MANIFEST).read_bytes()
        for p in self.snapshot.rglob('*'):
            self.assertEqual(p.stat().st_mode & 0o777, 0o700 if p.is_dir() else 0o600)
        with self.assertRaises(ValueError): self.capture()
        self.assertEqual(before, (self.snapshot / b.MANIFEST).read_bytes())

    def test_stop_is_preserved_but_does_not_authorize_execution(self):
        p = self.home / 'STOP'; p.write_bytes(b'operator stop'); p.chmod(0o600)
        result = self.capture()
        self.assertEqual((self.snapshot / 'evidence' / 'STOP').read_bytes(), b'operator stop')
        self.assertFalse(result['executionApproved']); self.assertTrue(result['restoredCopyStopped'])

    def test_source_lock_refuses_concurrent_capture(self):
        with b.r.cycles.c.source_lock(self.home, self.wallet):
            with self.assertRaises(BlockingIOError): self.capture()
        self.assertFalse(self.snapshot.exists())

    def test_unresolved_receipt_refuses_completed_snapshot(self):
        from test_cycle_execution import binding, s
        (self.home / binding.CYCLE / s.REVERSE_CHILD / 'receipt-evidence.json').unlink()
        with self.assertRaises(ValueError): self.capture()
        self.assertFalse(self.snapshot.exists())

    def test_recovery_sidecars_are_preserved_and_refused(self):
        p = self.home / 'controlled.positions.sqlite-wal'; p.write_bytes(b'keep'); p.chmod(0o600)
        with self.assertRaises(ValueError): self.capture()
        self.assertEqual(p.read_bytes(), b'keep'); self.assertFalse(self.snapshot.exists())

    def test_unsafe_symlink_hardlink_and_permissions_refused(self):
        p = self.home / 'extra.json'; target = self.home / 'wallet.json'
        p.symlink_to(target)
        with self.assertRaises(ValueError): self.capture()
        p.unlink(); os.link(target, p)
        with self.assertRaises(ValueError): self.capture()
        p.unlink(); target.chmod(0o644)
        with self.assertRaises(ValueError): self.capture()

    def test_unknown_file_and_nested_key_refused(self):
        p = self.home / 'extra.pem'; p.write_bytes(b'no'); p.chmod(0o600)
        with self.assertRaises(ValueError): self.capture()
        p.unlink(); d = self.home / 'extra'; d.mkdir(mode=0o700)
        p = d / b.KEY; p.write_bytes(b'no'); p.chmod(0o600)
        with self.assertRaises(ValueError): self.capture()

    def test_source_overlap_and_unsafe_parent_refused(self):
        with self.assertRaises(ValueError): b.capture(self.home, self.wallet, self.pool, self.home / 'backup')
        self.parent.chmod(0o755)
        with self.assertRaises(ValueError): self.capture()
        self.parent.chmod(0o700)

    def test_tampering_missing_and_extra_files_refused(self):
        self.capture(); p = self.snapshot / 'evidence' / 'wallet.json'; original = p.read_bytes()
        p.write_bytes(original + b' ')
        with self.assertRaises(ValueError): self.verify()
        p.unlink()
        with self.assertRaises(ValueError): self.verify()
        p.write_bytes(original); p.chmod(0o600)
        extra = self.snapshot / 'extra.json'; extra.write_bytes(b'{}'); extra.chmod(0o600)
        with self.assertRaises(ValueError): self.verify()

    def test_manifest_path_traversal_and_wrong_identity_refused(self):
        self.capture()
        with self.assertRaises(ValueError): b.verify(self.snapshot, 'wrong-wallet', self.pool)
        p = self.snapshot / b.MANIFEST; value = json.loads(p.read_text())
        original = p.read_bytes(); value['createdAt'] = 'arbitrary private text must not be exported'
        p.write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.verify()
        p.write_bytes(original); value = json.loads(p.read_text())
        value['inventory']['files']['../../escape.json'] = dict(bytes=0, sha256=b.sha(b''))
        p.write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.verify()
        self.assertFalse((self.parent / 'escape.json').exists())

    def test_caps_fail_closed(self):
        with patch.object(b, 'MAX_FILES', 1):
            with self.assertRaises(ValueError): self.capture()
        with patch.object(b, 'MAX_TOTAL', 1):
            with self.assertRaises(ValueError): self.capture()
        with patch.object(b, 'MAX_FILE', 1):
            with self.assertRaises(ValueError): self.capture()

    def test_failed_copy_keeps_incomplete_snapshot_without_seal(self):
        with patch.object(b, 'copy_inventory', side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError): self.capture()
        self.assertTrue(self.snapshot.exists()); self.assertFalse((self.snapshot / b.MANIFEST).exists())
        with self.assertRaises(ValueError): self.verify()
        with self.assertRaises(ValueError): self.capture()

    def test_source_change_during_copy_prevents_completion(self):
        original = b.copy_inventory
        def changed(source, target, inv):
            original(source, target, inv)
            p = self.home / 'wallet.json'; p.write_bytes(p.read_bytes() + b' ')
        with patch.object(b, 'copy_inventory', side_effect=changed):
            with self.assertRaises(ValueError): self.capture()
        self.assertFalse((self.snapshot / b.MANIFEST).exists())

    def test_nonaccounting_database_integrity_is_checked_without_repair(self):
        p = self.home / 'extra.sqlite'; p.write_bytes(b'invalid db'); p.chmod(0o600)
        before = self.source_bytes()
        with self.assertRaises(sqlite3.DatabaseError): self.capture()
        self.assertEqual(before, self.source_bytes()); self.assertFalse((self.snapshot / b.MANIFEST).exists())
        self.assertEqual(list(self.snapshot.glob('.restore-check-*')), [])

    def test_semantic_replay_rejects_modified_receipt_even_with_updated_manifest(self):
        self.capture()
        from test_cycle_execution import binding, s
        p = self.snapshot / 'evidence' / binding.CYCLE / s.REVERSE_CHILD / 'observation-000.json'
        value = json.loads(p.read_text()); value['receipt']['outputAtomic'] = '123456'
        p.write_text(json.dumps(value))
        manifest = self.snapshot / b.MANIFEST; value = json.loads(manifest.read_text())
        value['inventory'] = b.inventory(self.snapshot / 'evidence'); manifest.write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.verify()
        self.assertEqual(list(self.parent.glob('.restore-check-*')), [])

    def test_public_report_sanitized_and_cli_verifies_existing_snapshot(self):
        result = self.capture(); text = json.dumps(result)
        for excluded in (self.wallet, self.pool, str(self.home), 'private synthetic key sentinel'):
            self.assertNotIn(excluded, text)
        out = Path(self.tmp.name) / 'public.json.gz'
        cli = Path(__file__).with_name('evidence_backup_cli.py')
        self.home.rename(self.home.with_name('original-unavailable'))
        args = [sys.executable, '-E', '-s', str(cli), '--action', 'verify', '--snapshot', str(self.snapshot),
                '--wallet', self.wallet, '--pool', self.pool]
        run = subprocess.run(args + ['--output', str(out)], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        with gzip.open(out, 'rt') as f: self.assertEqual(json.load(f)['state'], 'isolated-restore-verified')
        run = subprocess.run(args + ['--output', str(self.snapshot / 'bad.json.gz')], capture_output=True, timeout=30)
        self.assertNotEqual(run.returncode, 0)


if __name__ == '__main__': unittest.main()
