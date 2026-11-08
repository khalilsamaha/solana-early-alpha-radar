"""One post-child historical replay, with exact child ACK binding retained."""
import json
import subprocess
import unittest
from unittest.mock import patch

import test_restricted_successor_signer as fixtures

backend=fixtures.backend
handoff=fixtures.handoff


class BackendReplayTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.SuccessorBackendTests.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.SuccessorBackendTests.tearDownClass.__func__)
    setUp=fixtures.SuccessorBackendTests.setUp
    tearDown=fixtures.SuccessorBackendTests.tearDown
    markers=fixtures.SuccessorBackendTests.markers
    rows=fixtures.SuccessorBackendTests.rows
    def dispatch(self):
        return backend._dispatch(self.c.home,self.c.wallet,self.c.pool,self.candidate,
            allow_private_key_signing=True,clock=lambda:self.c.now)

    def child(self,hook):
        original_run=subprocess.run
        def run(cmd,**kwargs):
            if not any(str(arg).endswith('/successor_signer.mjs') for arg in cmd):
                return original_run(cmd,**kwargs)
            self.markers();hook()
            return subprocess.CompletedProcess(cmd,0,'{"state":"successor-signed-recorded"}','')
        return patch.object(backend.subprocess,'run',side_effect=run)

    def test_full_history_replayed_before_boundary_before_child_and_after_child(self):
        calls=[];load=handoff.load
        def observed(*a,**kw):
            calls.append((self.c.path.parent/backend.ACK).exists())
            return load(*a,**kw)
        with patch.object(handoff,'load',side_effect=observed),self.child(lambda:self.assertEqual(calls,[False,False])):
            r=self.dispatch()
        self.assertEqual(calls,[False,False,True]);self.assertTrue(r['acknowledgmentRecorded'])

    def test_changed_old_backend_evidence_after_child_blocks_parent_acknowledgment(self):
        old=self.c.path.parent/'exit-signer-ack.json';raw=old.read_bytes()
        def changed():old.write_text('{}')
        try:
            with self.child(changed),self.assertRaises(ValueError):self.dispatch()
            b=self.c.book()
            try:
                state=handoff.read(b,handoff.successor.row(b),self.c.now)
                self.assertEqual(state['state'],'successor-signing-unknown')
                self.assertIsNone(state['signed']);self.assertEqual(state['eventCount'],1)
            finally:b.close()
        finally:old.write_bytes(raw)
        with patch.object(backend,'_invoke',side_effect=AssertionError('second key invocation')):
            self.assertEqual(self.dispatch()['state'],'successor-signing-unknown')

    def test_corrupt_new_ack_cannot_reach_parent_signed_record(self):
        def changed():
            path=self.c.path.parent/backend.ACK
            ack=json.loads(path.read_text());ack['requestSha256']='0'*64;path.write_text(json.dumps(ack))
        with self.child(changed),self.assertRaisesRegex(ValueError,'successor-signer-ack-binding'):
            self.dispatch()
        b=self.c.book()
        try:self.assertEqual(handoff.read(b,handoff.successor.row(b),self.c.now)['state'],'successor-signing-unknown')
        finally:b.close()

    def test_mismatched_invocation_identity_rejected_before_child(self):
        b=self.c.book()
        try:request=handoff.request_for(handoff.successor.row(b))
        finally:b.close()
        with patch.object(backend.subprocess,'run',side_effect=AssertionError('child')):
            with self.assertRaisesRegex(ValueError,'successor-backend-request-mismatch'):
                backend._invoke(self.c.home,self.c.wallet,self.c.pool,'0'*64,request,lambda:self.c.now)


if __name__=='__main__':unittest.main()
