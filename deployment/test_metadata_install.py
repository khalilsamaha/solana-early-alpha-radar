import hashlib, importlib.util, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('metadata_install',Path(__file__).with_name('install-metadata-provenance.py'))
x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
class MetadataInstallTests(unittest.TestCase):
    def files(self,root):
        host=root/'host';repo=root/'repo'
        for p in [host/'src',host/'public',repo/'scanner/src',repo/'scanner/test',repo/'scanner/scripts',repo/'scanner/fixtures']:p.mkdir(parents=True)
        (host/'src/a.js').write_text('before');(repo/'scanner/src/a.js').write_text('after');(repo/'scanner/src/new.js').write_text('new')
        (host/'package.json').write_text('{}');(host/'.env').write_text('sentinel');(host/'compose.yaml').write_text('preserve')
        h=lambda s:hashlib.sha256(s.encode()).hexdigest()
        manifest=repo/'manifest.json';manifest.write_text(json.dumps({'changed':{'src/a.js':{'before':[h('before'),h('previous')],'after':h('after')},'src/new.js':{'before':[None],'after':h('new')}},'dependencies':{'package.json':h('{}')}}))
        return host,repo,manifest
    def test_install_both_bases_idempotency_rollback_and_preserved_config(self):
        for base in ['before','previous']:
            with self.subTest(base=base),tempfile.TemporaryDirectory() as d:
                host,repo,manifest=self.files(Path(d));(host/'src/a.js').write_text(base)
                with patch.object(x,'ROOT',repo),patch.object(x,'MANIFEST',manifest),patch.object(x.subprocess,'run'):
                    x.install(host);x.install(host)
                    backups=list((host/'source-backups').iterdir());self.assertEqual(len(backups),1)
                    self.assertTrue((host/'src/new.js').exists());x.install(host,backups[0]);self.assertFalse((host/'src/new.js').exists())
                    self.assertEqual((host/'src/a.js').read_text(),base)
                self.assertEqual((host/'.env').read_text(),'sentinel');self.assertEqual((host/'compose.yaml').read_text(),'preserve')
    def test_partial_failure_restores_old_and_removes_added_files(self):
        with tempfile.TemporaryDirectory() as d:
            host,repo,m=self.files(Path(d));original=x.atomic
            def fail(p,data):
                if p==host/'src/new.js':raise OSError('write failed')
                return original(p,data)
            with patch.object(x,'ROOT',repo),patch.object(x,'MANIFEST',m),patch.object(x.subprocess,'run'),patch.object(x,'atomic',side_effect=fail):
                with self.assertRaises(OSError):x.install(host)
            self.assertEqual((host/'src/a.js').read_text(),'before');self.assertFalse((host/'src/new.js').exists())
    def test_modified_source_or_failed_tests_stop_before_writes(self):
        with tempfile.TemporaryDirectory() as d:
            host,repo,m=self.files(Path(d));(host/'src/a.js').write_text('manual')
            with patch.object(x,'ROOT',repo),patch.object(x,'MANIFEST',m):
                with self.assertRaisesRegex(ValueError,'Unexpected installed'):x.install(host)
                (host/'src/a.js').write_text('before')
                with patch.object(x.subprocess,'run',side_effect=RuntimeError('test failed')):
                    with self.assertRaisesRegex(RuntimeError,'test failed'):x.install(host)
            self.assertFalse((host/'source-backups').exists());self.assertEqual((host/'src/a.js').read_text(),'before')
    def test_symlink_source_and_modified_rollback_refused(self):
        with tempfile.TemporaryDirectory() as d:
            host,repo,m=self.files(Path(d));(host/'src/new.js').symlink_to(repo/'scanner/src/new.js')
            with patch.object(x,'ROOT',repo),patch.object(x,'MANIFEST',m),patch.object(x.subprocess,'run'):
                with self.assertRaisesRegex(ValueError,'Symlink'):x.install(host)
                (host/'src/new.js').unlink();x.install(host);(host/'src/new.js').write_text('manual')
                with self.assertRaisesRegex(ValueError,'rollback refused'):x.install(host,next((host/'source-backups').iterdir()))
if __name__=='__main__':unittest.main()
