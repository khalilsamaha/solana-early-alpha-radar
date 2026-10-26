import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
spec=importlib.util.spec_from_file_location('compact_launcher',Path(__file__).with_name('run-compact.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class LauncherTests(unittest.TestCase):
    def test_fixed_one_run_command_and_bounds(self):
        calls=[]
        def run(args,**kwargs):
            calls.append((args,kwargs))
            return subprocess.CompletedProcess(args,0,b'{"format":"statistics-compact-benchmark-1","state":"completed"}')
        self.assertEqual(m.collect(Path('/example'),run)['state'],'completed')
        self.assertEqual(len(calls),1)
        args,kw=calls[0]
        self.assertEqual(args[:7],['sudo','-n','docker','compose','--project-directory','/example','exec'])
        self.assertIn('-T',args);self.assertNotIn('--interactive=false',args)
        self.assertEqual(kw['timeout'],145);self.assertEqual(kw['stderr'],subprocess.DEVNULL)
        self.assertIn('src/core/storage.js',json.loads(args[-2]));self.assertNotIn('.env',args)
    def test_timeout_bad_format_and_oversized_output_are_sanitized(self):
        def timeout(*a,**kw):raise subprocess.TimeoutExpired('private detail',145)
        for runner in [timeout,lambda *a,**kw:subprocess.CompletedProcess([],1,b'private detail'),lambda *a,**kw:subprocess.CompletedProcess([],0,b'x'*65537)]:
            r=m.collect(Path('/example'),runner);self.assertEqual(r['state'],'unavailable');self.assertNotIn('private detail',json.dumps(r))
