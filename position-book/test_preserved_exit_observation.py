import unittest
from preserved_exit_checks import run


class PreservedExitTests(unittest.TestCase):
    def test_read_only_fault_matrix(self):
        r=run()
        self.assertEqual(r['state'],'offline-checks-passed')
        self.assertGreaterEqual(r['casesPassed'],23)


class CommandBoundaryTests(unittest.TestCase):
    def invoke(self,args):
        import sys
        from unittest.mock import patch
        import preserved_exit_observation_cli as cli
        with patch.object(sys,'argv',['observe']+args):return cli.main()

    def test_no_execute_retry_or_endpoint_flags(self):
        for args in (['--action','execute'],['--allow-devnet-submit'],['--endpoint','http://example.invalid']):
            with self.subTest(args=args),self.assertRaises(SystemExit):
                self.invoke(args+['--output','/tmp/unused-output.json.gz'])

    def test_no_operational_scope_for_offline_check(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            for args in (['--wallet','unused'],['--allow-devnet-observation']):
                with self.assertRaisesRegex(ValueError,'offline-has-no-scope'):
                    self.invoke(args+['--output',str(Path(tmp)/'report.json.gz')])

    def test_observe_requires_explicit_scope_and_output_outside_private_tree(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'private';root.mkdir()
            args=['--action','observe','--directory',str(root),'--wallet','w','--pool','p',
                '--expected-original-sha256','0'*64,'--expected-current-sha256','1'*64]
            with self.assertRaisesRegex(ValueError,'explicit-scope-required'):
                self.invoke(args+['--output',str(Path(tmp)/'report.json.gz')])
            with self.assertRaisesRegex(ValueError,'output-inside-private-source'):
                self.invoke(args+['--allow-devnet-observation','--output',str(root/'report.json.gz')])

    def test_collector_modes_cannot_be_combined(self):
        from unittest.mock import patch
        import admission_exit_capture as capture
        with patch.object(capture.view.cycles.c,'source_lock',side_effect=AssertionError('source')):
            for opts in ({'_replacement_expected':'0'*64},{'_evidence_sink':lambda x:None}):
                with self.assertRaisesRegex(ValueError,'exit-capture-mode-conflict'):
                    capture.collect('/missing','w','p',_preserved_expected=('0'*64,'1'*64),**opts)


class FinalBoundaryTests(unittest.TestCase):
    def test_snapshot_close_error_cannot_publish_success(self):
        from contextlib import contextmanager
        from unittest.mock import patch
        import sqlite3
        import admission_recovery
        from preserved_exit_checks import case
        original=admission_recovery.admission_read_lock
        @contextmanager
        def fail_after_close(path):
            with original(path):yield
            raise sqlite3.OperationalError('PRIVATE_CLOSE_ERROR')
        with case() as c:
            before=c.path.read_bytes()
            with patch.object(admission_recovery,'admission_read_lock',fail_after_close):r=c.observe()
            self.assertEqual(r['state'],'preserved-exit-observation-unavailable')
            self.assertIsNone(r['binding']);self.assertIsNone(r['provenance'])
            self.assertEqual(before,c.path.read_bytes())
            self.assertNotIn('PRIVATE_CLOSE_ERROR',str(r))

    def test_final_marker_check_time_counts_toward_deadline(self):
        from unittest.mock import patch
        import preserved_exit_observation as m
        from preserved_exit_checks import case
        original=m.os.path.lexists
        original_validate=m.validate
        def validation(*args):
            calls=[]
            def slow_marker(path):
                value=original(path)
                if str(path).endswith('exit-signer-ack.json'):
                    calls.append(True)
                    # One inside guard, one at the final marker check.
                    if len(calls)==2:c.timer.at+=10000
                return value
            with patch.object(m.os.path,'lexists',side_effect=slow_marker):return original_validate(*args)
        with case() as c:
            before=c.path.read_bytes()
            with patch.object(m,'validate',side_effect=validation):r=c.observe()
            self.assertEqual(r['state'],'preserved-exit-observation-unavailable')
            self.assertEqual(r['diagnosticCode'],'preserved-exit-validation-expired')
            self.assertIsNone(r['binding']);self.assertEqual(before,c.path.read_bytes())


if __name__=='__main__':unittest.main()
