import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import candidate as c
import check_image as h

class ImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.expected=c.stage(self.root/'context',clean=False)
    def node(self):
        return subprocess.run(['node',str(self.root/'context/app/verify.mjs')],capture_output=True,timeout=5)
    def test_exact_runtime_source_inventory_and_default_verification(self):
        r=self.node();self.assertEqual(r.returncode,0,r.stderr);c.verify_result(json.loads(r.stdout),self.expected)
        files=self.expected['manifest']['files']
        self.assertIn('scanner/src/index.js',files);self.assertIn('scanner/src/adapters/pumpportal-shared.js',files)
        self.assertFalse(any('/test/' in n or '.env' in n or '/data/' in n for n in files))
        recipe=(self.root/'context/Dockerfile').read_text()
        self.assertIn('FROM '+c.BASE,recipe);self.assertIn('USER 1000:1000',recipe)
        self.assertTrue(recipe.endswith('CMD ["/app/verify.mjs"]\n'))
    def test_modified_source_refuses(self):
        (self.root/'context/app/scanner/src/index.js').write_text('// changed')
        self.assertNotEqual(self.node().returncode,0)
    def test_unlisted_file_refuses(self):
        (self.root/'context/app/secret').write_text('synthetic')
        self.assertNotEqual(self.node().returncode,0)
    def test_missing_member_refuses(self):
        (self.root/'context/app/scanner/src/index.js').unlink()
        self.assertNotEqual(self.node().returncode,0)
    def test_symlink_refuses(self):
        p=self.root/'context/app/scanner/src/index.js';p.unlink();p.symlink_to('/dev/null')
        self.assertNotEqual(self.node().returncode,0)
    def test_changed_manifest_rejected_by_independent_expected_identity(self):
        p=self.root/'context/app/manifest.json';m=json.loads(p.read_bytes());m['source_tree']='f'*40;p.write_bytes(c.raw(m))
        r=self.node();self.assertEqual(r.returncode,0)
        with self.assertRaises(ValueError):c.verify_result(json.loads(r.stdout),self.expected)
    def test_activation_flag_refuses(self):
        p=self.root/'context/app/manifest.json';m=json.loads(p.read_bytes());m['activation_authorized']=True;p.write_bytes(c.raw(m))
        self.assertNotEqual(self.node().returncode,0)
    def test_staging_reuse_and_dirty_source_refuse(self):
        with self.assertRaises(ValueError):c.stage(self.root/'context',clean=False)
        with patch.object(c,'git',return_value=b' M source'):
            with self.assertRaisesRegex(ValueError,'source-not-clean'):c.stage(self.root/'new')
        self.assertFalse((self.root/'new').exists())
    def test_runtime_dependencies_require_separate_review(self):
        original=(c.REPO/'scanner/package.json').read_bytes()
        read=Path.read_bytes
        def modified(p):
            if p==c.REPO/'scanner/package.json':return c.raw({**json.loads(original),'dependencies':{'unreviewed':'1'}})
            return read(p)
        with patch.object(Path,'read_bytes',modified):
            with self.assertRaisesRegex(ValueError,'unreviewed-runtime-dependency'):c.source_bytes(c.sources())
    def test_endpoint_guard_does_not_fall_back(self):
        r=subprocess.run(['node',str(self.root/'context/app/probe.mjs'),'https://invalid.invalid'],capture_output=True,timeout=5)
        self.assertEqual(r.returncode,0,r.stderr);c.verify_probe(json.loads(r.stdout),self.expected,'missing-endpoint')
    def test_probe_identity_and_upstream_attempt_must_match(self):
        identity=json.loads(self.node().stdout)
        good={'identity':identity,'outcome':'gap','tokens':['pumpportal:create','pumpportal:migration','pumpportal:create'],
            'creations':2,'upstream_attempts':0,'fetch_attempts':0}
        c.verify_probe(good,self.expected,'normal')
        for field,value in [('upstream_attempts',1),('fetch_attempts',1),('creations',1),('tokens',[]),('outcome','deadline')]:
            with self.subTest(field=field),self.assertRaises(ValueError):c.verify_probe({**good,field:value},self.expected,'normal')
    def test_source_links_refused_before_staging(self):
        with patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaisesRegex(ValueError,'source-link'):c.source_bytes(c.sources())

class BoundaryTests(unittest.TestCase):
    def row(self):return {'id':'a'*64,'image':c.BASE,'label':'token','user':'1000:1000','network':'none',
        'readonly':True,'privileged':False,'restart':'no','memory':128*1024**2,'swap':128*1024**2,
        'pids':32,'cpus':1000000000,'init':True,'logging':'none','caps':['ALL'],
        'security':['no-new-privileges:true'],'mounts':[]}
    def test_isolation_rejects_changed_identity_or_authority(self):
        row=self.row();h.isolation(row,'token',c.BASE,None)
        for key,value in [('id','wrong'),('image','sha256:'+'f'*64),('label','foreign'),('user','root'),
            ('network','host'),('readonly',False),('privileged',True),('restart','always'),('memory',0),
            ('swap',-1),('pids',0),('cpus',0),('init',False),('logging','json-file'),('caps',[]),('security',[])]:
            with self.subTest(key=key),self.assertRaises(ValueError):h.isolation({**row,key:value},'token',c.BASE,None)
    def test_no_source_overlay_or_writable_ipc(self):
        row=self.row();ipc=Path('/tmp/test-private')
        row['mounts']=[{'Type':'bind','Source':str(ipc),'Destination':'/r1-ipc','RW':False}]
        h.isolation(row,'token',c.BASE,ipc)
        for field,value in [('Type','volume'),('Source','/other'),('Destination','/app'),('RW',True)]:
            wrong=copy.deepcopy(row);wrong['mounts'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):h.isolation(wrong,'token',c.BASE,ipc)
        row['mounts'].append({'Destination':'/app'})
        with self.assertRaises(ValueError):h.isolation(row,'token',c.BASE,ipc)
    def test_command_output_and_deadline_are_bounded(self):
        with self.assertRaisesRegex(ValueError,'command-output-limit'):
            h.bounded([sys.executable,'-c','print("x"*2048)'],cap=100)
        with self.assertRaisesRegex(ValueError,'command-timeout'):
            h.bounded([sys.executable,'-c','import time;time.sleep(10)'],seconds=.05)
    def test_zero_exit_diagnostic_refuses(self):
        with self.assertRaisesRegex(ValueError,'command-diagnostic'):
            h.bounded([sys.executable,'-c','print("ResourceWarning: fixture")'])
    def test_nonzero_and_valid_command(self):
        self.assertEqual(h.bounded([sys.executable,'-c','print("ok")']),b'ok\n')
        with self.assertRaisesRegex(ValueError,'command-failed'):h.bounded([sys.executable,'-c','raise SystemExit(2)'])


class LifecycleTests(unittest.TestCase):
    def run_fixture(self,*,bad_label=False,lost_create=False,bad_result=False,bad_removal=False):
        expected={'manifest_sha256':'b'*64,'manifest':{'files':{'one':'c'*64},'source_tree':'d'*40}}
        identity={'status':'image-bytes-verified','manifest_sha256':'b'*64,'files':1,'source_tree':'d'*40,'activation_authorized':False}
        calls=[];state={'running':False,'exit_code':0};receipts=[];token=''
        def fake(command,**kwargs):
            nonlocal token
            action=command[0];calls.append(action)
            if action=='create':
                token=command[command.index('--label')+1].split('=',1)[1]
                if lost_create:raise ValueError('create-response-lost')
                return ('a'*64+'\n').encode()
            if action=='inspect':
                row=BoundaryTests().row();row.update(state,label='foreign' if bad_label else token)
                return c.raw(row)
            if action=='start':return c.raw({**identity,'files':2} if bad_result else identity)
            if action=='rm':return b'wrong\n' if bad_removal else ('a'*64+'\n').encode()
            raise AssertionError(action)
        with patch.object(h,'bounded',side_effect=fake):
            if any((bad_label,lost_create,bad_result,bad_removal)):
                with self.assertRaises(ValueError):h.run_case([],c.BASE,expected,'verify',receipts)
            else:h.run_case([],c.BASE,expected,'verify',receipts)
        return calls,receipts
    def test_success_requires_removal_receipt(self):
        calls,receipts=self.run_fixture();self.assertEqual(calls,['create','inspect','start','inspect','inspect','rm'])
        self.assertTrue(receipts[0]['removed'])
    def test_foreign_identity_never_starts_or_removes(self):
        calls,receipts=self.run_fixture(bad_label=True)
        self.assertNotIn('start',calls);self.assertNotIn('rm',calls);self.assertFalse(receipts[0]['removed'])
    def test_lost_create_reconciles_only_owned_name_without_starting(self):
        calls,receipts=self.run_fixture(lost_create=True)
        self.assertEqual(calls,['create','inspect','rm']);self.assertTrue(receipts[0]['removed'])
    def test_bad_result_stays_failed_but_owned_cleanup_occurs(self):
        calls,receipts=self.run_fixture(bad_result=True);self.assertEqual(calls[-1],'rm')
        self.assertTrue(receipts[0]['removed']);self.assertNotIn('result',receipts[0])
    def test_bad_removal_never_claims_cleanup(self):
        calls,receipts=self.run_fixture(bad_removal=True);self.assertFalse(receipts[0]['removed'])

if __name__=='__main__':unittest.main()
