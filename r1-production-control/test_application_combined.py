"""Controller integration models; native combined acceptance is separate."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile
from unittest.mock import patch
import check_combined as combined
import test_combined as control_fixtures
import test_application_scanner as application_fixtures
shared=combined.shared;c=combined.c;v=combined.v;app=v.native_scanner.application
ApplicationTests=application_fixtures.ApplicationTests


class ApplicationGateTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.registry=self.root/'registry';self.registry.mkdir(mode=0o700)
        self.backend,self.model,*_=control_fixtures.fixture_backend(self.registry)
        self.plan,self.sha,self.paths=combined.prepare(self.root,self.registry,self.backend,False,application=True)
        self.guard=shared.SharedPrepared(self.backend,self.plan,self.sha,self.paths,mode=app.MODE)
        self.db=application_fixtures.database(self.registry);self.proof=app.storage_proof(self.registry)
        self.result={'outcome':v.SUCCESS,'model_only':True}

    def run_model(self,*args,**kwargs):
        self.assertEqual(kwargs,{'mode':app.MODE,'native_development':False})
        self.assertFalse(self.model.row['running']);self.assertTrue((self.registry/shared.INTENT).exists())
        c.write_new(self.registry/v.CLAIM,c.raw({'created_utc':c.now()}))
        return self.result

    def inspect_model(self,*args):
        c.check(app.storage_proof(self.registry)==self.proof,'application-storage-evidence')
        return self.result

    def test_same_original_restores_only_after_closed_application_evidence(self):
        with self.guard.open() as ctrl,patch.object(v,'run',side_effect=self.run_model),patch.object(v,'inspect',side_effect=self.inspect_model):
            ctrl.step('disable_restart');ctrl.step('stop');self.guard.run_shared()
            ctrl.step('start_original');state=ctrl.step('restore_restart')
        self.assertTrue(state['original_restored']);self.assertEqual(self.model.calls,['disable_restart','stop','start_original','restore_restart'])

    def test_changed_application_bytes_block_restore_despite_same_counts(self):
        with self.guard.open() as ctrl,patch.object(v,'run',side_effect=self.run_model),patch.object(v,'inspect',side_effect=self.inspect_model):
            ctrl.step('disable_restart');ctrl.step('stop');self.guard.run_shared()
            with closing(sqlite3.connect(self.db)) as db:db.execute('PRAGMA user_version=17');db.commit()
            self.assertEqual(app.storage_proof(self.registry)['counts'],self.proof['counts'])
            with self.assertRaisesRegex(ValueError,'application-storage-evidence'):ctrl.step('start_original')
        self.assertEqual(self.model.calls,['disable_restart','stop'])
        self.assertEqual(combined.pc.inspect(self.registry)['pending_action'],'start_original')

    def test_lost_application_confirmation_blocks_restore_and_retry(self):
        with self.guard.open() as ctrl,patch.object(v,'run',return_value={'outcome':'worker-failed'}):
            ctrl.step('disable_restart');ctrl.step('stop')
            with self.assertRaisesRegex(ValueError,'shared-shutdown-unconfirmed'):self.guard.run_shared()
            with self.assertRaises(ValueError):ctrl.step('start_original')
            with self.assertRaises(ValueError):self.guard.run_shared()
        self.assertIsNone(self.guard.completed);self.assertEqual(self.model.calls,['disable_restart','stop'])

    def test_lost_shared_receipt_blocks_restore_even_after_application_confirmation(self):
        write=c.write_new
        def lost(path,data):
            if path.name==shared.RESULT:raise OSError('lost-bridge-confirmation')
            return write(path,data)
        with self.guard.open() as ctrl,patch.object(v,'run',side_effect=self.run_model),patch.object(v,'inspect',side_effect=self.inspect_model):
            ctrl.step('disable_restart');ctrl.step('stop')
            with patch.object(c,'write_new',side_effect=lost):
                with self.assertRaisesRegex(OSError,'lost-bridge-confirmation'):self.guard.run_shared()
            with self.assertRaises(ValueError):ctrl.step('start_original')
        self.assertIsNone(self.guard.completed);self.assertEqual(self.model.calls,['disable_restart','stop'])

    def test_application_refuses_development_substitution_before_control(self):
        with self.assertRaisesRegex(ValueError,'application-native-only'):
            shared.SharedPrepared(self.backend,self.plan,self.sha,self.paths,mode=app.MODE,native_development=True)
        self.assertEqual(self.model.calls,[]);self.assertFalse((self.registry/shared.CLAIM).exists())

    def test_bundle_preserves_failure_receipts_without_copying_unconfirmed_database(self):
        for removed in (False,True):
            out=self.root/('confirmed' if removed else 'uncertain');out.mkdir(mode=0o700)
            root=out/'normal';root.mkdir(mode=0o700)
            c.write_new(root/'registry-path.json',c.raw({'registry':str(self.registry)}))
            receipt=self.registry/'native-scanner-disposal.json'
            if receipt.exists():receipt.unlink()
            c.write_new(receipt,c.raw({'removed':removed,'reaped':True}))
            before=self.db.read_bytes();combined.bundle(out,application=True)
            with zipfile.ZipFile(out/'acceptance.zip') as archive:
                index=c.parse(archive.read('members.json'));name='normal/application/radar.sqlite'
                self.assertIn('normal/registry/native-scanner-disposal.json',index['members'])
                self.assertEqual(name in index['members'],removed)
                if removed:
                    self.assertEqual(archive.read(name),before)
                    self.assertEqual(index['members'][name]['sha256'],c.digest(before))
                else:self.assertEqual(index['application_snapshots']['normal'],
                                     'unavailable-retain-originals-no-quiescence-claim')
            self.assertEqual(self.db.read_bytes(),before)


if __name__=='__main__':unittest.main()
