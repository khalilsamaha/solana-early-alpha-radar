import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import manifest as m
import storage as s
from test_manifest import inputs


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paths = {k: str(self.root/k) for k in s.ROLES}
        for p in self.paths.values():
            Path(p).mkdir(mode=0o700)
        config, policy = inputs()
        config.update(capture_path=self.paths['capture'], registry_path=str(self.root/'registry'),
                      endpoint_path=str(self.root/'registry'/'discovery.sock'))
        policy.update(raw_bytes=100, database_bytes=200, journal_bytes=300, receipt_bytes=400,
                      retained_runs=1, quarantined_runs=1, headroom_bytes=1000)
        self.row = m.build(config, policy)
        self.plan = self.root/'plan'
        self.sha = m.freeze(self.plan, self.row)

    def run_observation(self):
        return s.observe(self.plan, self.sha, self.paths)

    def test_real_filesystem_no_writes_and_no_authority(self):
        before = {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = self.run_observation()
        self.assertEqual(result['required_bytes'], self.row['capacity']['required_free_bytes'])
        self.assertEqual(result['remaining_blockers'], self.row['blockers'])
        for key in ('space_reserved','retention_verified','writes_performed','activation_authorized','automatic_resume_allowed'):
            self.assertFalse(result[key])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_space_drop_is_retained_not_repaired(self):
        original = s.sample; calls = []
        def sample(fd):
            calls.append(fd)
            row = original(fd)
            row['available_bytes'] = 10**9 if len(calls) <= 6 else 0
            return row
        with patch.object(s,'sample',side_effect=sample):
            row = self.run_observation()
        self.assertEqual(len(calls),12)
        self.assertEqual(row['available_bytes'],0)
        self.assertEqual(row['status'],'storage-insufficient-activation-blocked')

    def test_cross_filesystem_and_alias_refuse(self):
        original = s.sample
        for mode in ('device','alias'):
            count = [0];first = {}
            def sample(fd):
                row = original(fd);count[0]+=1
                if count[0]==1:first.update(row)
                if count[0]==2:
                    if mode=='device':row['device']+=1
                    else:row['inode']=first['inode']
                return row
            with patch.object(s,'sample',side_effect=sample):
                with self.assertRaisesRegex(ValueError,'storage-multiple-filesystems|storage-directory-alias'):
                    self.run_observation()

    def test_path_replacement_detected(self):
        original = s.open_directory;count=[0]
        def opened(path):
            count[0]+=1
            if count[0]==7:
                p=Path(self.paths['capture']);p.rename(self.root/'old-capture');p.mkdir(mode=0o700)
            return original(path)
        with patch.object(s,'open_directory',side_effect=opened):
            with self.assertRaisesRegex(ValueError,'storage-path-replaced'):self.run_observation()

    def test_missing_budget_stops_before_path_access(self):
        c,p=inputs();row=m.build(c,p);other=self.root/'incomplete';sha=m.freeze(other,row)
        with patch.object(s,'open_directory',side_effect=AssertionError('unexpected observation')):
            with self.assertRaisesRegex(ValueError,'storage-budget-missing'):s.observe(other,sha,self.paths)

    def test_capture_substitution_and_overlaps_refuse(self):
        saved=dict(self.paths)
        for role,value,code in [('capture',str(self.root/'other'),'storage-capture-binding'),
                                ('upload',self.paths['download'],'storage-path-overlap'),
                                ('export',str(self.root/'registry'),'storage-path-overlap')]:
            self.paths=dict(saved);self.paths[role]=value
            with self.assertRaisesRegex(ValueError,code):self.run_observation()

    def test_symlink_in_parent_and_leaf_refuse(self):
        alias=self.root/'alias';alias.symlink_to(self.root, target_is_directory=True)
        for path in (alias,alias/'capture'):
            with self.assertRaises(OSError):s.open_directory(path)

    def test_unavailable_or_public_paths_not_created_or_chmodded(self):
        path=Path(self.paths['upload']);path.rmdir()
        with self.assertRaises(FileNotFoundError):self.run_observation()
        self.assertFalse(path.exists())
        path.mkdir(mode=0o700)
        path.chmod(0o755)  # Explicit adverse fixture, independent of runner umask.
        with self.assertRaisesRegex(ValueError,'storage-private-directory'):self.run_observation()
        self.assertEqual(path.stat().st_mode & 0o777,0o755)

    def test_readonly_filesystem_refuses(self):
        with patch.object(s.os,'fstatvfs',return_value=SimpleNamespace(f_flag=os.ST_RDONLY,f_bavail=1000,f_frsize=4096)):
            with self.assertRaisesRegex(ValueError,'storage-readonly-filesystem'):self.run_observation()

    def test_source_and_manifest_replacement_refuse(self):
        original=s.pins;count=[0]
        def pins():
            count[0]+=1
            return original() if count[0]==1 else {'changed':'0'*64}
        with patch.object(s,'pins',side_effect=pins):
            with self.assertRaisesRegex(ValueError,'storage-source-or-manifest-changed'):self.run_observation()
        with patch.object(m,'inspect',side_effect=[self.row,{**self.row,'activation_authorized':True}]):
            with self.assertRaisesRegex(ValueError,'storage-source-or-manifest-changed'):self.run_observation()

    def test_descriptors_closed_after_failure(self):
        original=s.open_directory;opened=[]
        def open_directory(path):
            if len(opened)==3:raise OSError('fixture')
            fd=original(path);opened.append(fd);return fd
        with patch.object(s,'open_directory',side_effect=open_directory):
            with self.assertRaises(OSError):self.run_observation()
        for fd in opened:
            with self.assertRaises(OSError):os.fstat(fd)


if __name__=='__main__':unittest.main()
