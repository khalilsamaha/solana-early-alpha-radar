"""Offline tests: all apparent B2 responses are generated in-process."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import reconcile as q
r=q.r
INPUTS=None

class Reconcile(unittest.TestCase):
    def setUp(self):
        if INPUTS is None:raise RuntimeError('Use check_reconcile.py')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.control=Path(self.tmp.name)/'control';self.control.mkdir(mode=0o700);self.payload=None

    def make(self,profile='normal'):
        def fake(command,payload,cap,seconds):
            if 'listremotes' in command:return b'radar-b2: b2\n'
            if 'rcat' in command:self.payload=payload;return b''
            return self.payload
        with patch.object(r.old,'trusted_programs'),patch.object(r,'bounded',side_effect=fake):
            r.transfer(self.control,INPUTS/(profile+'-package.zip'),INPUTS/'report.json',profile,r.B2(profile))

    def change(self,name,fn):
        p=self.control/name;j=json.loads(p.read_text());fn(j);p.write_bytes(r.d.json_bytes(j))

    def check(self,success):
        before=q.inventory(self.control)
        with patch.object(r,'bounded',side_effect=AssertionError('No remote request')) as call:
            result=q.inspect(self.control);call.assert_not_called()
        self.assertEqual(result['recorded_completion_verified'],success)
        self.assertEqual(q.inventory(self.control),before)
        self.assertFalse(result['remote_observed_now']);self.assertFalse(result['retention_verified'])
        self.assertFalse(result['automatic_resume_allowed']);self.assertFalse(result['automatic_retry_allowed'])
        return result

    def test_complete_read_only(self):
        self.make();self.assertFalse(self.check(True)['manual_reconciliation_required'])
        self.check(True)

    def test_quarantine_remains_unresolved(self):
        self.make('shutdown-interruption');result=self.check(True)
        self.assertTrue(result['manual_reconciliation_required'])
        self.assertEqual(result['classification'],'quarantined-incomplete-evidence')

    def test_cleanup_failure_complete_evidence(self):
        self.make('cleanup-failure');self.check(True)

    def test_missing_completion(self):
        self.make();(self.control/'completion.json').unlink();self.check(False)

    def test_partial_completion(self):
        self.make();(self.control/'completion.json').write_bytes(b'{');self.check(False)

    def test_failed_transfer_marker(self):
        self.make();r.exclusive_file(self.control/'failure.json',b'{}\n');self.check(False)

    def test_wrong_intent(self):
        self.make();self.change('intent.json',lambda j:j.update(profile='cleanup-failure'));self.check(False)

    def test_wrong_upload_object(self):
        self.make();self.change('upload-observation.json',lambda j:j.update(remote_object='elsewhere'));self.check(False)

    def test_wrong_restore_contents(self):
        self.make();(self.control/'restored'/'report.json').write_bytes(b'{}\n');self.check(False)

    def test_wrong_download(self):
        self.make();(self.control/'downloaded.zip').write_bytes(b'wrong');self.check(False)

    def test_wrong_completion_calls(self):
        self.make();self.change('completion.json',lambda j:j.update(calls=[]));self.check(False)

    def test_claimed_retention_rejected(self):
        self.make();self.change('completion.json',lambda j:j.update(retention_verified=True));self.check(False)

    def test_missing_control_never_created(self):
        p=Path(self.tmp.name)/'missing';self.assertFalse(q.inspect(p)['recorded_completion_verified']);self.assertFalse(p.exists())

    def test_locked_control_refused(self):
        self.make()
        with r.owner_lock(self.control):self.assertFalse(q.inspect(self.control)['recorded_completion_verified'])

    def test_link_rejected(self):
        self.make();(self.control/'extra').symlink_to(self.control/'package.zip')
        self.assertFalse(q.inspect(self.control)['recorded_completion_verified'])
        self.assertTrue((self.control/'extra').is_symlink())

    def test_changed_during_read(self):
        self.make();real=q.inventory;calls=[]
        def inventory(path):
            result=real(path)
            if path==self.control:
                calls.append(1)
                if len(calls)==2:result['fake']=[1,'changed']
            return result
        with patch.object(q,'inventory',side_effect=inventory):
            self.assertFalse(q.inspect(self.control)['recorded_completion_verified'])

    def test_lock_exit_failure_revokes_verification(self):
        from contextlib import contextmanager
        self.make()
        real=r.d.o.preserve.existing_lock
        @contextmanager
        def bad_lock(path):
            with real(path):
                yield
            if path==self.control/'r1-supervisor.lock':
                raise r.CaptureError('changed-lock')
        with patch.object(r.d.o.preserve,'existing_lock',side_effect=bad_lock):
            result=q.inspect(self.control)
        self.assertFalse(result['recorded_completion_verified'])
        self.assertTrue(result['manual_reconciliation_required'])
