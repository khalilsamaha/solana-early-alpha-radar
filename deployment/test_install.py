import importlib.util
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('deploy',Path(__file__).with_name('install-fast-followup.py'))
deploy=importlib.util.module_from_spec(spec);spec.loader.exec_module(deploy)


class InstallTests(unittest.TestCase):
    def setup_files(self, base):
        project=base/'host';root=base/'checkout';project.mkdir();root.mkdir()
        for folder in ['src','public']:(project/folder).mkdir()
        for folder in ['test','scripts','fixtures']:(root/'scanner'/folder).mkdir(parents=True)
        (root/'scanner/src').mkdir()
        (project/'src/a.js').write_text('before');(root/'scanner/src/a.js').write_text('after')
        (project/'package.json').write_text('{}');(project/'.env').write_text('sentinel')
        (project/'compose.yaml').write_text('preserve');(project/'radar.sqlite').write_bytes(b'untouched')
        h=lambda s:hashlib.sha256(s.encode()).hexdigest()
        manifest=root/'manifest.json';manifest.write_text(json.dumps({'changed':{'src/a.js':{'before':h('before'),'after':h('after')}},'dependencies':{'package.json':h('{}')}}))
        return project,root,manifest

    def test_install_idempotency_rollback_preserve_config_and_data(self):
        with tempfile.TemporaryDirectory() as d:
            host,root,manifest=self.setup_files(Path(d))
            with patch.object(deploy,'ROOT',root),patch.object(deploy,'MANIFEST',manifest),patch.object(deploy.subprocess,'run'):
                deploy.install(host);deploy.install(host)
                backups=list((host/'source-backups').iterdir());self.assertEqual(len(backups),1)
                self.assertEqual((host/'src/a.js').read_text(),'after')
                deploy.install(host,backups[0]);self.assertEqual((host/'src/a.js').read_text(),'before')
            self.assertEqual((host/'.env').read_text(),'sentinel');self.assertEqual((host/'compose.yaml').read_text(),'preserve')
            self.assertEqual((host/'radar.sqlite').read_bytes(),b'untouched')

    def test_unexpected_source_and_failing_tests_stop_before_changes(self):
        with tempfile.TemporaryDirectory() as d:
            host,root,manifest=self.setup_files(Path(d))
            with patch.object(deploy,'ROOT',root),patch.object(deploy,'MANIFEST',manifest):
                (host/'src/a.js').write_text('edited')
                with self.assertRaisesRegex(RuntimeError,'Unexpected installed source'):deploy.install(host)
                (host/'src/a.js').write_text('before')
                with patch.object(deploy.subprocess,'run',side_effect=RuntimeError('tests failed')):
                    with self.assertRaisesRegex(RuntimeError,'tests failed'):deploy.install(host)
                self.assertEqual((host/'src/a.js').read_text(),'before');self.assertFalse((host/'source-backups').exists())

    def test_symlink_parent_refused(self):
        with tempfile.TemporaryDirectory() as d:
            host,root,manifest=self.setup_files(Path(d));outside=Path(d)/'other';(host/'src').rename(outside);(host/'src').symlink_to(outside)
            with patch.object(deploy,'ROOT',root),patch.object(deploy,'MANIFEST',manifest):
                with self.assertRaisesRegex(RuntimeError,'Symlink'):deploy.install(host)


if __name__=='__main__':unittest.main()
