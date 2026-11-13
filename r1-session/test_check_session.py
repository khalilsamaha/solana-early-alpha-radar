import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import check_session as check


class CheckSessionTests(unittest.TestCase):
    def test_successful_test_result_with_async_diagnostic_is_rejected(self):
        for diagnostic in ('TimeoutError exception in shielded future',
                           'Future exception was never retrieved',
                           'Task was destroyed but it is pending!',
                           'ResourceWarning: unclosed transport'):
            with self.subTest(diagnostic=diagnostic):
                def emits():
                    print(diagnostic, file=sys.stderr)
                suite = unittest.TestSuite([unittest.FunctionTestCase(emits)])
                log = io.StringIO()
                accepted, counts = check.tests(log, suite)
                self.assertEqual(counts, {'run': 1, 'errors': 0, 'failures': 0, 'skipped': 0})
                self.assertFalse(accepted)
                self.assertIn(diagnostic, log.getvalue())

    def test_retained_scenario_worker_diagnostic_prevents_acceptance(self):
        diagnostic = 'TimeoutError exception in shielded future'
        async def scenario(*args, **kwargs):
            worker = threading.Thread(target=lambda: print(diagnostic, file=sys.stderr))
            worker.start(); worker.join()
            return {}
        assessment = {'local_session_outcome': 'capture-stopped'}
        saved = {'archive_sha256': '0'*64, 'assessment': assessment}
        with tempfile.TemporaryDirectory(prefix='r1-check-diagnostic-') as t:
            output = Path(t)/'results'
            with patch.object(check, 'tests', return_value=(True, {'run': 1, 'errors': 0, 'failures': 0, 'skipped': 0})), \
                 patch.object(check.core, 'block_internet'), \
                 patch.object(check.fixtures, 'MODES', ('normal',)), \
                 patch.object(check.fixtures, 'exercise', side_effect=scenario), \
                 patch.object(check.a, 'export', return_value=saved), \
                 patch.object(check.a, 'restore', return_value=saved), \
                 patch.object(check, 'read_private', return_value=b'synthetic archive'), \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = check.main(['--development', '--output-directory', str(output)])
            self.assertEqual(result, 1)
            report = json.loads((output/'report.json').read_text())
            self.assertEqual(report['status'], 'candidate-session-check-failed-live-blocked')
            self.assertEqual(report['failure_stage'], 'normal')
            self.assertFalse((output/'acceptance.zip').exists())
            self.assertIn(diagnostic, (output/'validation.log').read_text())


if __name__ == '__main__':
    unittest.main()
