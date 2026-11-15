from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import bridge as b
from check_prepared import fixture
m=b.m;p=b.p;s=b.s;n=b.n;c=b.c


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.registry=self.root/'registry';self.registry.mkdir(mode=0o700)
        self.directory,self.sha,self.paths=fixture(self.root,self.registry)
        p.prepare(self.directory,self.sha,self.paths)
        self.backend=n.Backend(self.root,self.registry,[],'unsubscribed',True)
        self.guard=b.Guard(self.backend,self.directory,self.sha,self.paths)

    def prime(self):
        with patch.object(n.Backend,'prepare',return_value='fixture-proof') as dispatch:
            self.assertEqual(self.guard.prepare(),'fixture-proof');self.assertEqual(dispatch.call_count,1)

    def test_gate_persisted_before_fixture_dispatch(self):
        def prepare(_):
            self.assertTrue((self.registry/'bridge-claim.json').is_file())
            self.assertTrue((self.root/'gate-00.json').is_file())
            return 'proof'
        with patch.object(n.Backend,'prepare',prepare):self.assertEqual(self.guard.prepare(),'proof')

    def test_second_output_cannot_rearm(self):
        self.prime();other=self.root/'other';other.mkdir(mode=0o700)
        backend=n.Backend(other,self.registry,[],'unsubscribed',True)
        guard=b.Guard(backend,self.directory,self.sha,self.paths)
        with patch.object(n.Backend,'prepare',side_effect=AssertionError('retry')):
            with self.assertRaises(FileExistsError):guard.prepare()

    def test_low_space_refuses_dispatch_and_consumes_bridge(self):
        original=s.sample
        with patch.object(s,'sample',side_effect=lambda fd:{**original(fd),'available_bytes':0}), \
             patch.object(n.Backend,'prepare',side_effect=AssertionError('dispatch')):
            with self.assertRaisesRegex(ValueError,'storage-no-start-headroom'):self.guard.prepare()
        self.assertTrue((self.registry/'bridge-claim.json').exists())

    def test_directory_replacement_refuses_even_with_space(self):
        self.prime();path=Path(self.paths['capture']);path.rename(self.root/'old');path.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError,'storage-generation-changed'):self.guard.gate('start_owner')

    def test_missing_preparation_and_nonfixture_backend_refuse(self):
        with self.assertRaisesRegex(ValueError,'isolated-backend-required'):b.Guard(object(),self.directory,self.sha,self.paths)
        (self.registry/p.RESULT).unlink()
        with patch.object(n.Backend,'prepare',side_effect=AssertionError('dispatch')):
            with self.assertRaisesRegex(ValueError,'preparation-not-complete'):self.guard.prepare()

    def test_changed_source_and_gate_publication_failure_refuse(self):
        self.prime()
        with patch.object(b,'pins',return_value={'changed':'0'*64}):
            with self.assertRaisesRegex(ValueError,'bridge-claim-changed'):self.guard.gate('start_owner')
        with patch.object(c,'write_new',side_effect=OSError('durability')):
            with self.assertRaises(OSError):self.guard.gate('start_owner')
        self.assertEqual(len(self.guard.checks),1)

    def test_missing_coordinator_intent_never_observes_or_dispatches(self):
        self.prime()
        with patch.object(b.h,'inspect',return_value={'pending_action':None,'known':{},'records':0}), \
             patch.object(c,'read',return_value=m.raw({})), \
             patch.object(s,'observe',side_effect=AssertionError('observation before intent')), \
             patch.object(n.Backend,'perform',side_effect=AssertionError('dispatch before intent')):
            with self.assertRaisesRegex(ValueError,'bridge-intent-required'):
                self.guard.perform('start_owner','0'*64,{})

    def test_wrong_owner_manifest_refuses_before_actor(self):
        row=m.inspect(self.directory,self.sha);row['config']['owner_source_sha256']='0'*64
        altered=m.build(row['config'],row['policy']);other=self.root/'wrong-owner'
        sha=m.freeze(other,altered)
        guard=b.Guard(self.backend,other,sha,self.paths)
        with patch.object(n.Backend,'prepare',side_effect=AssertionError('dispatch')):
            with self.assertRaisesRegex(ValueError,'isolated-manifest-binding'):guard.prepare()


if __name__=='__main__':unittest.main()
