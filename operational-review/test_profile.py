import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

class ProfileLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('stats_profiler',Path(__file__).with_name('profile-stats.py'))
        cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)
    def test_fixed_container_command_only_one_bounded_replay(self):
        calls=[]
        def run(args,**kw):
            calls.append((args,kw))
            return subprocess.CompletedProcess(args,0,json.dumps({'format':'statistics-profile-1','state':'completed'}).encode())
        r=self.module.collect(Path('/example/project'),run)
        self.assertEqual(r['state'],'completed');self.assertEqual(len(calls),1)
        args,kw=calls[0]
        self.assertEqual(args[:7],['sudo','-n','docker','compose','--project-directory','/example/project','exec'])
        self.assertNotIn('--interactive=false',args);self.assertIn('-T',args)
        self.assertEqual(kw['timeout'],20);self.assertEqual(kw['stderr'],subprocess.DEVNULL)
        self.assertIn('src/core/stats-worker.js',json.loads(args[-1]));self.assertNotIn('.env',args)
        self.assertLess(len(kw['input']),65536)
    def test_failure_and_oversized_output_remain_sanitized(self):
        for r in (subprocess.CompletedProcess([],1,b'private detail'),subprocess.CompletedProcess([],0,b'x'*65537),subprocess.CompletedProcess([],0,b'[]')):
            result=self.module.collect(Path('/example'),lambda *a,**k:r)
            self.assertEqual(result['state'],'unavailable');self.assertNotIn('private detail',json.dumps(result))
