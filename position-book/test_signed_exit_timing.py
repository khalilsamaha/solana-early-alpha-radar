"""Read-only reconstruction of a signed-but-unsent expiry; no retry authority."""
import json
import unittest
from unittest.mock import patch

import exit_history_timing as m
from fresh_exit_checks import case
from exit_submission_checks import signed_case, submit, FakeRpc


def files(c):
    return {str(p):p.read_bytes() for root in (c.home,c.path.parent)
            for p in root.rglob('*') if p.is_file()}


class SignedTimingTests(unittest.TestCase):
    def inspect(self,c):
        with patch.object(m.view,'now',c.clock), \
             patch.object(m.backend,'_invoke',side_effect=AssertionError('private signer')), \
             patch('socket.socket',side_effect=AssertionError('network')):
            return m.inspect(c.home,c.wallet,c.pool)

    def test_expired_signed_ack_preserved_without_send_or_authorization(self):
        with case() as c:
            def late(root,request):
                wire=c.adapter(root,request);c.timer.at+=10000;return wire
            failed=c.run(adapter=late)
            self.assertEqual(failed['diagnosticCode'],'fresh-signing-expired')
            self.assertEqual(failed['senderRequests'],0)
            before=files(c);r=self.inspect(c)
            self.assertEqual(r['state'],'saved-exit-timing-observed',r)
            t=r['signingTimeline']
            self.assertEqual(t['state'],'expired-signed-locally-unsubmitted-held')
            self.assertTrue(t['acknowledgmentRecordedAfterDeadline'])
            self.assertTrue(t['deadlineExpiredAtObservation'])
            self.assertGreaterEqual(t['observedAtMs'],t['deadlineMs'])
            self.assertLessEqual(t['remainingAtAcknowledgmentTimestampMs'],0)
            self.assertFalse(t['applicationSendBoundaryRecorded'])
            self.assertEqual(t['transportState'],'not-attempted')
            self.assertEqual(t['backendAttemptToRecordedAcknowledgmentMs'],
                             t['acknowledgmentRecordedAtMs']-t['backendAttemptRecordedAtMs'])
            for key in ('signatureCreationAtMs','ackFileWrittenAtMs',
                        'signingBoundaryCommitCompletedAtMs','acknowledgmentCommitCompletedAtMs'):
                self.assertIsNone(t[key])
            for key in ('retryAllowed','replacementAuthorized','reservationsReleasedThisRun'):
                self.assertFalse(t[key])
            self.assertEqual(files(c),before)
            self.assertNotIn(c.exit_wire,json.dumps(r));self.assertNotIn(c.wallet,json.dumps(r))
            self.assertEqual(r['networkRequests'],0);self.assertFalse(r['privateKeyAccessed'])
            # Historical expiry is not permission to reopen any boundary.
            self.assertEqual(c.run()['networkRequests'],0)
            self.assertEqual(c.signs,1);self.assertEqual(files(c),before)

    def test_send_boundary_never_classified_as_unsent_even_when_reply_lost(self):
        with signed_case() as c:
            submit(c,FakeRpc(c,lost=True));c.now+=30000;c.clock=lambda:c.now
            before=files(c);r=self.inspect(c)
            self.assertEqual(r['state'],'saved-exit-timing-observed',r)
            self.assertEqual(r['signingTimeline']['state'],'transport-recorded-inspect-recovery')
            self.assertTrue(r['signingTimeline']['applicationSendBoundaryRecorded'])
            self.assertEqual(files(c),before)

    def test_missing_or_corrupt_ack_has_no_partial_success_or_raw_error(self):
        for kind in ('missing','wire','marker-clock'):
            with self.subTest(kind=kind),signed_case() as c:
                c.now+=30000;c.clock=lambda:c.now
                path=c.path.parent/m.backend.ACK
                if kind=='missing':path.unlink()
                elif kind=='wire':
                    value=json.loads(path.read_text());value['wireSha256']='0'*64
                    path.write_text(json.dumps(value))
                else:
                    path=c.path.parent/m.backend.ATTEMPT
                    value=json.loads(path.read_text());value['atMs']=c.now+1000
                    path.write_text(json.dumps(value))
                before=files(c);r=self.inspect(c)
                self.assertEqual(r['state'],'history-unavailable')
                self.assertIsNone(r['timing']);self.assertIsNone(r['signingTimeline'])
                self.assertEqual(files(c),before)
                self.assertNotIn(str(c.home),json.dumps(r))

    def test_corrupt_signing_ledger_is_not_an_unsent_certificate(self):
        with signed_case() as c:
            c.clock=lambda:c.now;b=c.book()
            try:b.db.execute("UPDATE admission_exit_signing SET value='{}' WHERE seq=2")
            finally:b.close()
            before=files(c);r=self.inspect(c)
            self.assertEqual(r['state'],'history-unavailable')
            self.assertIsNone(r['signingTimeline']);self.assertEqual(files(c),before)


if __name__=='__main__':unittest.main()
