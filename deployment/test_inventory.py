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

    def test_release_manifest_matches_scanner_and_observer_tree(self):
        import json
        m = json.loads(inventory.MANIFEST.read_text())
        root = inventory.ROOT
        self.assertEqual(inventory.disk_inventory(root / 'scanner', m)['matched'], len(m['scannerFiles']))
        for name, sha in m['observerFiles'].items():
            self.assertEqual(inventory.file_hash(root / 'quote-observer', name), sha)
        self.assertNotIn('.env', m['scannerFiles'])


if __name__ == '__main__':
    unittest.main()
