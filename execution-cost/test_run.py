import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from examples import fixture
from run import read_packet, publish, build_report, MAX_BYTES


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_synthetic_cases_are_distinct_and_never_approve(self):
        r = build_report()
        self.assertEqual([c['result']['state'] for c in r['cases']], [
            'modeled-constraints-met', 'modeled-constraints-not-met',
            'unavailable', 'unavailable', 'modeled-constraints-not-met'])
        self.assertTrue(all(c['result']['executionApproved'] is False for c in r['cases']))

    def test_caller_report_does_not_export_raw_input(self):
        r = build_report(fixture(), now_ms=100000)
        self.assertNotIn('buy', r['result']); self.assertNotIn('sell', r['result'])
        self.assertNotIn(fixture()['buy']['outputMint'], json.dumps(r))

    def test_atomic_exclusive_private_report(self):
        path=self.root/'out.json.gz'; r=build_report()
        publish(path, r)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(gzip.decompress(path.read_bytes())), r)
        before=path.read_bytes()
        with self.assertRaises(FileExistsError): publish(path, {})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_existing_output_symlink_not_overwritten(self):
        target=self.root/'target'; target.write_text('keep')
        link=self.root/'out'; link.symlink_to(target)
        with self.assertRaises(FileExistsError): publish(link, {})
        self.assertEqual(target.read_text(), 'keep')

    def test_input_rejects_symlinks(self):
        path=self.root/'in'; path.write_text('{}')
        link=self.root/'link'; link.symlink_to(path)
        with self.assertRaises(OSError): read_packet(link)

    def test_input_size_and_duplicate_and_nonfinite_refused(self):
        path=self.root/'in'
        for value in (' '* (MAX_BYTES+1), '{"format":1,"format":2}', '{"x":NaN}'):
            path.write_text(value)
            with self.assertRaises(ValueError): read_packet(path)

    def test_input_and_output_are_bounded(self):
        path=self.root/'in'; path.write_text(json.dumps(fixture()))
        self.assertEqual(read_packet(path), fixture())
        with self.assertRaises(ValueError): publish(self.root/'out', {'data':'x'*MAX_BYTES})
        self.assertFalse((self.root/'out').exists())

    def test_cli_default_and_refusal_exit_status(self):
        runner=str(Path(__file__).with_name('run.py'))
        out=self.root/'examples.json.gz'
        p=subprocess.run([sys.executable, '-E', '-s', runner, '--output', str(out)], capture_output=True, timeout=5)
        self.assertEqual(p.returncode,0,p.stderr)
        raw=self.root/'input.json'; raw.write_text(json.dumps(fixture()))
        out2=self.root/'stale.json.gz'
        p=subprocess.run([sys.executable, '-E', '-s', runner, '--input', str(raw), '--output', str(out2)], capture_output=True, timeout=5)
        self.assertEqual(p.returncode,2,p.stderr)
        self.assertEqual(json.loads(gzip.decompress(out2.read_bytes()))['result']['state'],'unavailable')

    def test_null_input_does_not_select_examples(self):
        path=self.root/'in'; path.write_text('null'); out=self.root/'out'
        p=subprocess.run([sys.executable, str(Path(__file__).with_name('run.py')), '--input', str(path), '--output', str(out)], capture_output=True, timeout=5)
        self.assertNotEqual(p.returncode,0)
        self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
