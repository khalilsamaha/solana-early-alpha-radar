import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('baseline_runner', Path(__file__).with_name('check-baseline.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class BaselineRunnerTests(unittest.TestCase):
    def run_stages(self, source):
        log = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()):
            runner.run_all([('synthetic', [sys.executable, '-c', source])], log)
        return log.getvalue()

    def test_clean_child_gets_one_final_marker(self):
        self.assertEqual(self.run_stages('print("clean")').count(runner.SUCCESS), 1)

    def test_zero_exit_resource_warning_is_rejected(self):
        with self.assertRaises(runner.StageFailure):
            self.run_stages('import warnings; warnings.warn("unclosed fixture", ResourceWarning)')

    def test_zero_exit_unraisable_is_rejected(self):
        with self.assertRaises(runner.StageFailure):
            self.run_stages('class Bad:\n def __del__(self): raise RuntimeError("fixture")\nBad()')

    def test_nonzero_exit_is_rejected(self):
        with self.assertRaises(runner.StageFailure):
            self.run_stages('raise SystemExit(7)')

    def test_failure_stops_later_stage_and_has_no_success_marker(self):
        log = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(runner.StageFailure):
            runner.run_all([('first', [sys.executable, '-c', 'raise SystemExit(1)']),
                            ('must-not-run', [sys.executable, '-c', 'print("later")'])], log)
        self.assertNotIn(runner.SUCCESS, log.getvalue())
        self.assertNotIn('must-not-run', log.getvalue())

    def test_existing_log_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.log'
            path.write_text('original')
            result = subprocess.run([sys.executable, str(Path(runner.__file__)),
                                     '--research-python', sys.executable, '--log', str(path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(path.read_text(), 'original')
            self.assertNotIn(runner.SUCCESS, result.stdout)


if __name__ == '__main__':
    unittest.main()
