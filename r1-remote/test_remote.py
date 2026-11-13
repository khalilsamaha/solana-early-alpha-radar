"""Offline boundary tests using the accepted synthetic packages, no B2 requests."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import remote as r

INPUTS=None

class Boundary(unittest.TestCase):
    def setUp(self):
        if INPUTS is None:raise RuntimeError('Use check_remote.py with accepted input paths')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.control=self.root/'control';self.control.mkdir(mode=0o700)
        self.profile='normal';self.package=INPUTS/'normal-package.zip';self.report=INPUTS/'report.json'
        self.commands=[];self.payload=None

    def fake(self,command,payload,cap,seconds):
        self.commands.append(command)
        if 'listremotes' in command:return b'radar-b2: b2\n'
        if 'rcat' in command:self.payload=payload;return b''
        return self.payload

    def invoke(self,runner=None,profile=None):
        profile=profile or self.profile
        with patch.object(r.old,'trusted_programs'),patch.object(r,'bounded',side_effect=runner or self.fake):
            return r.transfer(self.control,INPUTS/(profile+'-package.zip'),self.report,profile,r.B2(profile))

    def assert_unresolved(self):
        self.assertFalse((self.control/'completion.json').exists())
        self.assertTrue((self.control/'package.zip').exists())
        failure=json.loads((self.control/'failure.json').read_text())
        self.assertTrue(failure['manual_reconciliation_required']);self.assertFalse(failure['automatic_retry_allowed'])
        with self.assertRaises(r.CaptureError):self.invoke()

    def test_complete_commands_and_bindings(self):
        result=self.invoke();self.assertEqual(len(self.commands),3)
        self.assertFalse(result['retention_verified']);self.assertFalse(result['live_launch_authorized'])
        self.assertEqual(result['package_sha256'],r.PROFILES['normal'][1])
        for cmd in self.commands:
            self.assertEqual(cmd[:4],[r.old.SUDO,'-n',r.old.TIMEOUT,'--signal=TERM'])
            self.assertEqual(cmd[cmd.index('--config')+1],r.old.CONFIG)
            self.assertEqual(cmd[cmd.index('--max-transfer')+1],'128Ki')
            self.assertEqual(cmd[cmd.index('--retries')+1],'1')
        self.assertEqual(self.commands[1][-4],'rcat');self.assertEqual(self.commands[2][-4],'cat')
        self.assertEqual(self.commands[1][-3],self.commands[2][-3])
        with self.assertRaises(r.CaptureError):self.invoke()

    def test_shutdown_quarantine_survives(self):
        result=self.invoke(profile='shutdown-interruption')
        self.assertEqual(result['classification'],'quarantined-incomplete-evidence')
        self.assertTrue(result['reconciliation_required'])

    def test_cleanup_failure_is_preserved(self):
        result=self.invoke(profile='cleanup-failure')
        self.assertEqual(result['classification'],'complete-replayed-evidence')
        restored=json.loads((self.control/'restored'/'restore-report.json').read_text())
        self.assertIsInstance(restored,dict)

    def test_wrong_package_before_credentials(self):
        with patch.object(r.old,'trusted_programs') as trusted:
            with self.assertRaises(r.CaptureError):
                r.transfer(self.control,INPUTS/'cleanup-failure-package.zip',self.report,'normal',r.B2('normal'))
            trusted.assert_not_called()

    def test_wrong_report_before_credentials(self):
        bad=self.root/'bad.json';r.exclusive_file(bad,b'{}\n')
        with patch.object(r.old,'trusted_programs') as trusted:
            with self.assertRaises(r.CaptureError):r.transfer(self.control,self.package,bad,'normal',r.B2('normal'))
            trusted.assert_not_called()

    def test_backend_rejection_consumes_intent(self):
        with self.assertRaises(r.CaptureError):self.invoke(lambda *a:b'radar-b2: s3\n')
        self.assert_unresolved()

    def test_duplicate_backend_rejected(self):
        with self.assertRaises(r.CaptureError):self.invoke(lambda *a:b'radar-b2: b2\nradar-b2: b2\n')
        self.assert_unresolved()

    def test_upload_uncertainty_retained(self):
        def runner(*args):
            if 'rcat' in args[0]:raise TimeoutError('sensitive diagnostic')
            return self.fake(*args)
        with self.assertRaisesRegex(r.CaptureError,'remote-transfer-unresolved'):self.invoke(runner)
        self.assert_unresolved()
        self.assertTrue(json.loads((self.control/'failure.json').read_text())['remote_object_may_exist'])
        self.assertNotIn('sensitive',(self.control/'failure.json').read_text())

    def test_download_corruption(self):
        def runner(*args):return b'wrong' if 'cat' in args[0] else self.fake(*args)
        with self.assertRaises(r.CaptureError):self.invoke(runner)
        self.assert_unresolved()

    def test_restore_failure(self):
        real=r.d.restore;calls=[]
        def restore(*args):
            calls.append(1)
            if len(calls)==2:raise OSError('restore failed')
            return real(*args)
        with patch.object(r.d,'restore',side_effect=restore):
            with self.assertRaises(r.CaptureError):self.invoke()
        self.assert_unresolved()

    def test_completion_write_failure(self):
        real=r.d.o.write
        def write(path,name,row):
            if name=='completion.json':raise OSError('disk full')
            return real(path,name,row)
        with patch.object(r.d.o,'write',side_effect=write):
            with self.assertRaises(r.CaptureError):self.invoke()
        self.assert_unresolved()

    def test_interruption_preserved(self):
        def runner(*args):
            if 'rcat' in args[0]:raise KeyboardInterrupt()
            return self.fake(*args)
        with self.assertRaises(r.CaptureError):self.invoke(runner)
        self.assert_unresolved()

    def test_client_identity_order_and_deadline(self):
        c=r.B2('normal')
        with self.assertRaises(r.CaptureError):c.run('download','../x')
        c.deadline=0
        with self.assertRaises(r.CaptureError):c.run('backend')
        with self.assertRaises(r.CaptureError):r.B2('arbitrary')
        c=r.B2('cleanup-failure')
        with self.assertRaises(r.CaptureError):r.transfer(self.control,self.package,self.report,'normal',c)

    def test_no_retry_after_runner_failure(self):
        c=r.B2('normal')
        with patch.object(r,'bounded',side_effect=OSError()):
            with self.assertRaises(r.CaptureError):c.run('backend')
            with self.assertRaises(r.CaptureError):c.run('backend')
        self.assertEqual(len(c.calls),1)

    def test_runner_bidirectional_bound(self):
        payload=b'x'*125620
        out=r.bounded([sys.executable,'-c','import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'],payload,len(payload),5)
        self.assertEqual(out,payload)

    def test_runner_output_overflow(self):
        with self.assertRaises(r.CaptureError):r.bounded([sys.executable,'-c','print("x"*10000)'],b'',16,5)

    def test_runner_timeout_and_nonzero(self):
        with self.assertRaises(r.CaptureError):r.bounded([sys.executable,'-c','import time; time.sleep(10)'],b'',16,.1)
        with self.assertRaises(r.CaptureError):r.bounded([sys.executable,'-c','raise SystemExit(1)'],b'',16,5)

    def test_payload_and_remote_scope(self):
        c=r.B2('normal')
        with patch.object(r,'bounded',return_value=b'radar-b2: b2\n'):c.run('backend')
        with self.assertRaises(r.CaptureError):c.run('upload','../outside',b'bad')
        with self.assertRaises(r.CaptureError):c.run('upload','package-'+'0'*32+'-'+c.sha+'.zip',b'bad')
        self.assertEqual(len(c.calls),1)
