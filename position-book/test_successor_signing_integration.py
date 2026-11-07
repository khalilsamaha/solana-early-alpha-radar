"""Integration boundary faults with real source replay and synthetic providers."""
from pathlib import Path
import unittest
from unittest.mock import patch

import successor_signing_integration as m
import test_retired_exit_successor as fixtures
import test_retired_successor_collection as collectors
import successor_signing_test_fixture as crypto_fixture
from test_signed_exit_timing import files


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.object(fixtures,'signed_case',crypto_fixture.signed_case):fixtures.SuccessorTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixtures.SuccessorTests.tearDownClass.__func__(cls)
    setUp=fixtures.SuccessorTests.setUp
    def tearDown(self):
        for n in (m.backend.ATTEMPT,m.backend.ACK):(self.c.path.parent/n).unlink(missing_ok=True)
        fixtures.SuccessorTests.tearDown(self)
    inputs=collectors.CollectionTests.inputs
    rows=fixtures.SuccessorTests.rows
    def run_case(self,*,adapter=None,expiry_hook=None,quote_hook=None,mono=lambda:0):
        reads,quote,clock=self.inputs(expiry_hook=expiry_hook,quote_hook=quote_hook)
        clock.at=max(clock.at,self.c.now+500)
        self.timer=clock
        def sign(root,wallet,pool,expected,request,current_clock):
            self.c.now=current_clock()
            return (adapter or self.c.sign_successor)(request)
        with patch.object(m.backend,'_invoke',side_effect=sign):
            r=m._collect_sign(self.c.home,self.c.wallet,self.c.pool,self.expected,self.retired,
                allow_unsigned_successor=True,allow_private_key_signing=True,clock=clock,monotonic=mono,
                _expiry_opener=reads,_quote_opener=quote)
        return r,reads,quote

    def test_connected_collectors_commit_exact_ack_and_preserve_previous_tables(self):
        before=self.rows();r,reads,quote=self.run_case()
        self.assertEqual(r['state'],'successor-signed-within-deadline',r)
        self.assertEqual((len(reads.calls),len(quote.calls)),(8,20));self.assertTrue(r['signerAcknowledgmentValidated'])
        self.assertGreater(r['deadlineHeadroomMs'],0);self.assertEqual(r['transactionsSent'],0)
        after=self.rows();self.assertEqual(before,{k:after[k] for k in before})

    def test_explicit_optins_precede_source_access(self):
        with patch.object(m.view.cycles.c,'source_lock',side_effect=AssertionError('source access')):
            for key in ('allow_unsigned_successor','allow_private_key_signing'):
                for val in (False,1,'yes',None):
                    opts=dict(allow_unsigned_successor=True,allow_private_key_signing=True);opts[key]=val
                    with self.assertRaises(ValueError):m._collect_sign('/missing','w','p','a'*64,'b'*64,**opts)

    def test_persisted_candidate_repeat_never_collects_or_signs_again(self):
        r,_,_=self.run_case();before=files(self.c)
        def deny(_):raise AssertionError('signer')
        again,reads,quote=self.run_case(adapter=deny)
        self.assertEqual(again['state'],'existing-successor-held');self.assertEqual(reads.calls+quote.calls,[])
        self.assertEqual(again['signerInvocationAttempts'],0);self.assertEqual(before,files(self.c))

    def test_lost_backend_response_preserves_unknown_and_never_retries(self):
        def lost(_):raise TimeoutError('PRIVATE PROVIDER DETAIL')
        r,_,_=self.run_case(adapter=lost)
        self.assertEqual(r['signerInvocationAttempts'],1);self.assertIsNone(r['signatureCreatedThisRun'])
        self.assertNotIn('PRIVATE',str(r));self.assertEqual(r['transactionsSent'],0)
        again,reads,quote=self.run_case(adapter=lambda _:self.fail('retry'))
        self.assertEqual(again['state'],'existing-successor-held');self.assertEqual(reads.calls+quote.calls,[])

    def test_stop_or_expiry_after_persistence_blocks_key(self):
        prepare=m.successor._prepare_from_producer
        def stopped(*args,**kwargs):
            r=prepare(*args,**kwargs);(self.c.home/'STOP').touch(mode=0o600);return r
        with patch.object(m.successor,'_prepare_from_producer',side_effect=stopped):
            r,_,_=self.run_case(adapter=lambda _:self.fail('key'))
        self.assertEqual(r['signerInvocationAttempts'],0);self.assertEqual(r['diagnosticCode'],'successor-stopped')

    def test_expiry_during_collection_rolls_back_and_never_signs(self):
        before=files(self.c)
        def slow(n,q,rpc):
            if n==20:self.timer.at+=10000
        r,_,_=self.run_case(quote_hook=slow,adapter=lambda _:self.fail('key'))
        self.assertEqual(r['signerInvocationAttempts'],0);self.assertEqual(before,files(self.c))
        self.assertEqual(r['state'],'successor-signing-review-required')

    def test_orphan_marker_blocks_all_reads(self):
        (self.c.path.parent/m.backend.ATTEMPT).touch(mode=0o600)
        r,reads,quote=self.run_case(adapter=lambda _:self.fail('key'))
        self.assertEqual(r['diagnosticCode'],'successor-key-slot-occupied');self.assertEqual(reads.calls+quote.calls,[])

    def test_persisted_expiry_prevents_signing_and_does_not_refresh(self):
        prepare=m.successor._prepare_from_producer
        def expired(*args,**kwargs):
            r=prepare(*args,**kwargs);self.timer.at+=10000;return r
        with patch.object(m.successor,'_prepare_from_producer',side_effect=expired):
            r,_,_=self.run_case(adapter=lambda _:self.fail('key'))
        self.assertTrue(r['preparationCreatedThisRun']);self.assertEqual(r['signerInvocationAttempts'],0)
        self.assertEqual(r['state'],'successor-signing-review-required')
        self.c.now=self.timer.at
        again,reads,quote=self.run_case(adapter=lambda _:self.fail('key'))
        self.assertEqual(again['state'],'existing-successor-held');self.assertEqual(reads.calls+quote.calls,[])

    def test_write_failure_rolls_back_candidate_without_key(self):
        before=files(self.c);write=m.successor.write_record
        def fail(*a):write(*a);raise OSError('PRIVATE DISK FAILURE')
        with patch.object(m.successor,'write_record',side_effect=fail):
            r,_,_=self.run_case(adapter=lambda _:self.fail('key'))
        self.assertEqual(r['collectionRequests'],28);self.assertEqual(r['signerInvocationAttempts'],0)
        self.assertEqual(before,files(self.c));self.assertNotIn('PRIVATE',str(r))

    def test_return_boundary_after_owner_cleanup_cannot_claim_timely_success(self):
        def late_result(*a,**kw):
            return dict(state='successor-signed-within-deadline',timing={},completedWithinOriginalDeadline=True,
                completedAtMs=100,originalDeadlineMs=101)
        with patch.object(m,'_run',side_effect=late_result):
            r=m._collect_sign('/unused','w','p','a'*64,'b'*64,clock=lambda:102,monotonic=lambda:0)
        self.assertFalse(r['completedWithinOriginalDeadline']);self.assertEqual(r['deadlineHeadroomMs'],-1)
        self.assertEqual(r['stage'],'return-boundary')

    def test_late_signed_reply_is_preserved_but_not_timing_success(self):
        def late(request):
            wire=self.c.sign_successor(request);self.timer.at+=10000;return wire
        r,_,_=self.run_case(adapter=late)
        self.assertTrue(r['signerAcknowledgmentValidated']);self.assertFalse(r['completedWithinOriginalDeadline'])
        self.assertEqual(r['state'],'successor-signing-review-required');self.assertEqual(r['transactionsSent'],0)


if __name__=='__main__':unittest.main()
