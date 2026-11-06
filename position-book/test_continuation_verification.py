"""Continuation collection shares exact public signatures, never state decisions."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import fresh_exit as m
from preserved_exit_checks import case

wire=m.fresh_signing.timing.wire


def run(c):
    return m.continue_sign_submit(c.home,c.wallet,c.pool,
        expected_original_sha256=c.expected,expected_current_sha256=c.current,
        allow_unsigned_continuation=True,allow_private_key_signing=True,
        allow_devnet_submit=True,collection_opener=c.rpc,clock=c.clock,monotonic=lambda:0)


class ContinuationVerificationTests(unittest.TestCase):
    def test_collection_joins_attempt_and_lost_signer_does_not_leak_or_retry(self):
        with case() as c:
            original=m.continuation.collect_and_prepare;owners=[];flags=[]
            def collect(*args,**kwargs):
                owners.append(wire._SIGNATURE_SCOPE.get());flags.append(kwargs.get('_reuse_signature_scope'))
                value=original(*args,**kwargs)
                self.assertTrue(value['signatureVerification']['sharedWithParent'])
                self.assertIs(wire._SIGNATURE_SCOPE.get(),owners[-1])
                return value
            with patch.object(m.continuation,'collect_and_prepare',collect),\
                 patch.object(m.backend,'_invoke',side_effect=TimeoutError('lost response')) as signer:
                result=run(c)
                self.assertEqual(signer.call_count,1)
                self.assertEqual(result['senderRequests'],0)
                self.assertEqual(flags,[True]);self.assertTrue(owners)
                self.assertEqual(owners[0][0],set())
                self.assertIsNone(wire._SIGNATURE_SCOPE.get())
                again=run(c)
                self.assertEqual(again['networkRequests'],0)
                self.assertEqual(signer.call_count,1)

    def test_source_change_after_shared_collection_still_blocks_signer(self):
        with case() as c:
            original=m.continuation.collect_and_prepare
            read=m.view.read_locked;collected=[False]
            def collect(*args,**kwargs):
                value=original(*args,**kwargs);collected[0]=True;return value
            def changed(*args,**kwargs):
                result=deepcopy(read(*args,**kwargs))
                if collected[0]:result['ledgerHeadSha256']='f'*64
                return result
            with patch.object(m.continuation,'collect_and_prepare',collect),\
                 patch.object(m.view,'read_locked',changed),\
                 patch.object(m.backend,'_invoke',side_effect=AssertionError('must not sign')) as signer:
                result=run(c)
            self.assertTrue(collected[0]);self.assertEqual(signer.call_count,0)
            self.assertEqual(result['senderRequests'],0)
            self.assertIsNone(wire._SIGNATURE_SCOPE.get())

    def test_direct_collection_remains_isolated_from_outer_owner(self):
        with case() as c, wire.signature_verification_scope() as owner:
            scope=wire._SIGNATURE_SCOPE.get()
            result=m.continuation.collect_and_prepare(c.home,c.wallet,c.pool,
                expected_original_sha256=c.expected,expected_current_sha256=c.current,
                allow_unsigned_continuation=True,opener=c.rpc,clock=c.clock,monotonic=lambda:0)
            self.assertTrue(result['createdThisRun'])
            self.assertNotIn('sharedWithParent',result['signatureVerification'])
            self.assertEqual(owner()['verificationCalls'],0)
            self.assertIs(wire._SIGNATURE_SCOPE.get(),scope)

if __name__=='__main__':unittest.main()
