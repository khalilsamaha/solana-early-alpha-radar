"""Exercise the real shell wrapper with a fake exporter, without sudo or services."""
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_dataset import fixture, ROOT


class RunnerTests(unittest.TestCase):
    def invoke(self, args=(), fail=False):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for folder in ('src', 'scripts', 'bin'):
            (root / folder).mkdir()
        src = root / 'fixture.gz'
        with gzip.open(src, 'wt') as f:
            json.dump(fixture(), f)
        exporter = root / 'bin/sudo'
        exporter.write_text('#!/usr/bin/env python3\nimport os,sys,json,pathlib\n'
                            'pathlib.Path("called.json").write_text(json.dumps(sys.argv[1:]))\n'
                            'if os.environ.get("RADAR_TEST_FAIL") == "1":\n'
                            ' sys.stdout.buffer.write(b"partial"); sys.exit(1)\n'
                            'sys.stdout.buffer.write(pathlib.Path("fixture.gz").read_bytes())\n')
        exporter.chmod(0o700)
        env = dict(os.environ, PATH=str(root / 'bin') + os.pathsep + os.environ['PATH'], RADAR_TEST_FAIL='1' if fail else '0')
        result = subprocess.run(['bash', str(ROOT / 'research-dataset/run.sh'), *args], cwd=root,
                                env=env, capture_output=True, text=True, timeout=15)
        return root, result

    def test_default_window_is_24_and_produces_private_valid_report(self):
        root, result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((root / 'called.json').read_text())[-2:], ['--hours', '24'])
        report, = root.glob('radar-research-dataset-*.json.gz')
        self.assertEqual(report.stat().st_mode & 0o777, 0o600)
        with gzip.open(report, 'rt') as f:
            self.assertEqual(json.load(f)['summary']['admitted'], 1)

    def test_explicit_window_is_passed_without_narrowing(self):
        root, result = self.invoke(['--hours', '12'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((root / 'called.json').read_text())[-2:], ['--hours', '12'])
        self.assertIn('last 12 hours', result.stdout)

    def test_invalid_arguments_never_call_exporter(self):
        for args in (['--hours', '0'], ['--hours', '73'], ['--hours', '1;id'], ['--hours'], ['unknown']):
            root, result = self.invoke(args)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / 'called.json').exists())

    def test_failed_export_does_not_publish_partial_source_or_dataset(self):
        root, result = self.invoke(fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(list(root.glob('radar-*.json.gz')))
        self.assertFalse(list(root.glob('.research-dataset-*')))
        self.assertIn('explicitly smaller', result.stderr)


if __name__ == '__main__':
    unittest.main()
