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


if __name__=='__main__':unittest.main()
