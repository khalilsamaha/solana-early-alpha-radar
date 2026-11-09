import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import inventory


class InventoryTests(unittest.TestCase):
    def test_exact_files_mismatch_and_missing_remain_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'app.js').write_text('a')
            expected = {'app.js': hashlib.sha256(b'a').hexdigest(), 'absent.js': 'missing'}
            r = inventory.disk_inventory(root, {'scannerFiles': expected})
            self.assertEqual(r['matched'], 1)
            self.assertEqual(r['unavailable'], ['absent.js'])
            (root / 'app.js').write_text('b')
            self.assertEqual(inventory.disk_inventory(root, {'scannerFiles': expected})['mismatched'], ['app.js'])

    def test_symlinks_and_escape_not_read(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'real').write_text('content'); (root / 'link').symlink_to(root / 'real')
            self.assertIsNone(inventory.file_hash(root, 'link'))
            with self.assertRaises(ValueError): inventory.file_hash(root, '../outside')

    def test_no_docker_access_is_unavailable_not_success(self):
        with patch.object(inventory, 'command', return_value=None):
            self.assertEqual(inventory.container_inventory(Path('/unused'), {})['state'], 'unavailable')

    def test_release_inventory_remains_pinned_while_source_helpers_evolve(self):
        import json
        # Keep accepted deployment identity immutable; development cleanup is not a release.
        self.assertEqual(hashlib.sha256(inventory.MANIFEST.read_bytes()).hexdigest(),
                         '6c14de29ad608342116107ed7aa575fd35fa4047f271d0fbefe84cbf5ccdfbcd')
        m = json.loads(inventory.MANIFEST.read_text())
        root = inventory.ROOT
        scanner = inventory.disk_inventory(root / 'scanner', m)
        self.assertEqual(scanner['matched'], len(m['scannerFiles']) - 1)
        self.assertEqual(scanner['mismatched'], ['scripts/evidence-check.py'])
        self.assertEqual(scanner['unavailable'], [])
        self.assertEqual(inventory.file_hash(root / 'scanner', 'scripts/evidence-check.py'),
                         'ab07ae1cc77c798324415e71deae0412cff92da6503243af21112872c530f575')
        source = json.loads((root / 'quote-observer' / 'manifest.json').read_text())
        self.assertEqual(set(source['files']), set(m['observerFiles']))
        differences = set()
        for name, sha in m['observerFiles'].items():
            actual = inventory.file_hash(root / 'quote-observer', name)
            self.assertEqual(actual, source['files'][name])
            if actual != sha: differences.add(name)
        self.assertEqual(differences, {'install.py', 'manage.py', 'test_install.py', 'test_manage.py'})
        self.assertNotIn('.env', m['scannerFiles'])


if __name__ == '__main__':
    unittest.main()
