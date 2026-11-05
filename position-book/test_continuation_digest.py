"""Continuation-only reuse, bounded diagnostics and fixed offline workload."""
import base64
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import fresh_exit as fresh
import canonical_replay as memo
import controlled_continuation as controlled
import continuation_exit_checks as checks

FLAGS = dict(expected_original_sha256='a'*64, expected_current_sha256='b'*64,
             allow_unsigned_continuation=True, allow_private_key_signing=True,
             allow_devnet_submit=True)


class ContinuationDigestTests(unittest.TestCase):
    def test_scope_reuses_exact_hash_only_inside_continuation_wrapper(self):
        def inner(*args, **kwargs):
            memo.digest({'n': 1});memo.digest({'n': 1})
            return dict(signerAcknowledgmentValidated=False)
        with patch.object(fresh, '_run', inner):
            result=fresh.continue_sign_submit('/unused','w','p',**FLAGS)
            self.assertEqual(result['canonicalDigestReplay']['hits'],1)
            ordinary=fresh.prepare_sign_submit('/unused','w','p',
                allow_private_key_signing=True,allow_devnet_submit=True)
            replacement=fresh.replace_sign_submit('/unused','w','p',
                expected_preparation_sha256='a'*64,allow_unsigned_replacement=True,
                allow_private_key_signing=True,allow_devnet_submit=True)
            self.assertNotIn('canonicalDigestReplay',ordinary)
            self.assertNotIn('canonicalDigestReplay',replacement)
        self.assertIsNone(memo._SCOPE.get())

    def test_failure_discards_scope_and_never_carries_cached_permission(self):
        snapshots=[]
        def fail(*args, **kwargs):
            memo.digest({'n': 1});memo.digest({'n': 1})
            snapshots.append(memo._SCOPE.get())
            raise OSError('test failure')
        with patch.object(fresh,'_run',fail):
            for _ in range(2):
                with self.assertRaises(OSError):fresh.continue_sign_submit('/unused','w','p',**FLAGS)
                self.assertIsNone(memo._SCOPE.get())
        self.assertTrue(all(not values and counts['retainedBytes']==0 and counts['hits']==1
                            for values,counts in snapshots))

    def test_projection_is_bounded_and_does_not_leak_input(self):
        with memo.scope() as stats:
            memo.digest({'PRIVATE_INPUT':'PRIVATE_VALUE'});value=stats()
        projected=memo.summary(dict(value,private='PRIVATE_VALUE'))
        self.assertEqual(projected,value)
        self.assertNotIn('PRIVATE',json.dumps(projected))
        for key,bad in (('calls',True),('hits',-1),('entries',129),('retainedBytes',memo.MAX_BYTES+1),
                        ('version','PRIVATE'),('rechecksFullInputContent',False)):
            with self.subTest(key=key):self.assertIsNone(memo.summary(dict(value,**{key:bad})))
        self.assertIsNone(memo.summary(None))
        with tempfile.TemporaryDirectory() as d:
            Path(d).chmod(0o700)
            with patch.object(controlled,'EXECUTE',return_value=dict(
                    state='fresh-exit-inspection-required',canonicalDigestReplay=dict(value,private='PRIVATE_VALUE'))):
                report=controlled.execute(d,'w','p',**FLAGS)
            self.assertEqual(report['canonicalDigestReplay'],value)
            self.assertNotIn('PRIVATE',json.dumps(report))

    def test_large_fixture_is_fixed_and_restores_generator_even_after_failure(self):
        from copy import deepcopy
        import pool_fixtures
        row=deepcopy(pool_fixtures.DEPLOY_ROW);baseline=deepcopy(pool_fixtures.BASE)
        shared=pool_fixtures.DEPLOY_ROW
        with self.assertRaisesRegex(ValueError,'test-stop'):
            with checks.fixture_size(True):
                self.assertIs(shared,pool_fixtures.DEPLOY_ROW)
                raw=base64.b64decode(shared['data'][0])
                self.assertEqual(len(raw),1024*1024)
                self.assertEqual(raw[45:52],b'\x7fELF\x02\x01\x01')
                self.assertEqual(pool_fixtures.BASE['identity']['accountDataBytes'],1024*1024)
                raise ValueError('test-stop')
        self.assertEqual(pool_fixtures.DEPLOY_ROW,row)
        self.assertEqual(pool_fixtures.BASE,baseline)
        for value in (1,'yes',None):
            with self.assertRaises(ValueError):
                with checks.fixture_size(value):pass

    def test_large_mode_is_offline_cli_option_and_reported_failure_is_nonzero(self):
        import continuation_exit_cli as cli
        result=dict(state='review-required',casesPassed=0,integrationElapsedMs=None,
                    diagnosticPhases=[],programFixtureBytes=1024*1024)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz'
            with patch.object(cli,'run',return_value=result) as run,patch('builtins.print'),\
                 patch('sys.argv',['check','--large-fixture','--output',str(out)]):
                with self.assertRaises(SystemExit) as exc:cli.main()
            self.assertEqual(exc.exception.code,2)
            run.assert_called_once_with(large_fixture=True)
            self.assertEqual(json.load(gzip.open(out))['programFixtureBytes'],1024*1024)

    def test_requested_large_fixture_cannot_pass_with_small_captured_account(self):
        import test_fresh_exit
        class SmallFixture:
            @classmethod
            def setUpClass(cls):pass
            @classmethod
            def tearDownClass(cls):pass
            def setUp(self):
                self.home=Path(tempfile.mkdtemp())
                self.e={'costInputs':{'capture':{'evidence':{'accounts':{'result':{'value':[
                    {'data':[base64.b64encode(b'small').decode(),'base64']}
                ]}}}}}}
            def tearDown(self):self.home.rmdir()
        with patch.object(test_fresh_exit,'ActualBackendTests',SmallFixture),\
             patch.object(checks,'connected',side_effect=AssertionError('must not run')):
            result=checks._run(large_fixture=True,faults={})
        self.assertEqual(result['state'],'review-required')
        self.assertEqual(result['programFixtureBytes'],5)
        self.assertEqual(result['failedPhase'],'fixture-instance-setup')
        self.assertTrue(result['temporaryLedgersRemoved'])
        rows=[r for r in result['diagnosticPhases'] if r['phase']=='fixture-instance-setup']
        self.assertEqual(rows[0]['diagnosticCode'],'synthetic-program-size')


if __name__=='__main__':unittest.main()
