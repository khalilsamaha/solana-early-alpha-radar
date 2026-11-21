from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import guarded_acceptance as runner
import test_combined as fixtures
import test_service_registry as service_tests
import test_handoff_budget as budget_tests
c=runner.c


class GuardedAcceptanceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)

    def case(self,name):
        root=self.root/name;root.mkdir(mode=0o700);registry=root/'registry';registry.mkdir(mode=0o700)
        backend,model,*_=fixtures.fixture_backend(registry)
        c.write_new(root/'registry-path.json',c.raw({'registry':str(registry)}))
        result=runner.exercise(root,registry,backend,name,development=True)
        self.assertEqual(result['status'],'guarded-case-passed-live-blocked')
        receipt=runner.preserve(root,registry)
        expected='closed-restored-offline-handoff-evidence' if name=='normal-service-exclusion' else 'quarantined-handoff-evidence'
        self.assertEqual(receipt['assessment']['classification'],expected)
        self.assertFalse(receipt['assessment']['components']['native_application_verified'])
        return root,registry,result,receipt

    def test_five_new_combined_paths_with_real_worker_node_and_portable_replay(self):
        for name in runner.CASES:
            if name=='changed-application-storage':continue
            with self.subTest(case=name):
                root,registry,result,receipt=self.case(name)
                if name=='normal-service-exclusion':
                    self.assertTrue(result['active_contender_refused']);self.assertTrue(result['consumed_attempt_refused'])
                if name=='lost-service-completion':
                    self.assertTrue(result['control_recovery']['original_restored'])
                    self.assertEqual(result['service_recovery']['status'],'attempt-consumed-completion-unconfirmed')
                if name=='service-lock-replaced':self.assertEqual(result['commands'],[])
                if name.startswith('deadline-'):self.assertTrue(result['clock_offset_injected'])
        runner.combined.bundle(self.root,application=True,cases=runner.CASES)
        import zipfile
        with zipfile.ZipFile(self.root/'acceptance.zip') as archive:
            index=c.parse(archive.read('members.json'))
            for name,meta in index['members'].items():
                raw=archive.read(name);self.assertEqual(meta,{'bytes':len(raw),'sha256':c.digest(raw)})
            self.assertIn('normal-service-exclusion/handoff/evidence.zip',index['members'])

    def test_partial_export_is_attempted_once_and_failure_is_explicit(self):
        root=self.root/'normal-service-exclusion';root.mkdir(mode=0o700)
        c.write_new(root/'service-path.json',c.raw({'directory':'/not-used','contract_sha256':'a'*64}))
        c.write_new(root/'registry-path.json',c.raw({'registry':'/not-used'}))
        with patch.object(runner,'preserve',side_effect=OSError('fixture')) as preserve:
            result=runner.preserve_partial(self.root)
        self.assertEqual(preserve.call_count,1)
        self.assertEqual(result[root.name]['status'],'portable-evidence-unavailable-retain-originals')
        (root/'handoff').mkdir(mode=0o700)
        with patch.object(runner,'preserve',side_effect=AssertionError('retry')):
            self.assertEqual(runner.preserve_partial(self.root),{})

    def test_native_storage_case_cannot_be_faked_by_development_mode(self):
        root=self.root/'unsupported';root.mkdir(mode=0o700);registry=root/'registry';registry.mkdir(mode=0o700)
        backend,model,*_=fixtures.fixture_backend(registry)
        with self.assertRaisesRegex(ValueError,'guarded-case'):
            runner.exercise(root,registry,backend,'changed-application-storage',development=True)
        self.assertEqual(model.calls,[]);self.assertFalse((root/'service').exists())

    def test_remaining_batch_excludes_the_two_accepted_cases(self):
        self.assertEqual(runner.REMAINING_CASES,('deadline-after-shared','service-lock-replaced',
            'lost-service-completion','changed-application-storage'))


def load_tests(loader,tests,pattern):
    return unittest.TestSuite((tests,loader.loadTestsFromTestCase(service_tests.RegistryTests),
                              loader.loadTestsFromTestCase(budget_tests.BudgetTests),
                              loader.loadTestsFromName('test_application_scanner.ApplicationTests.'
                                  'test_native_completion_accepts_reordered_mounts_but_no_identity_changes')))


if __name__=='__main__':unittest.main()
