"""Composition faults over actual collectors, durable journals and fake providers."""
import unittest
from unittest.mock import patch

import successor_execution as m
from successor_execution_checks import Provider
import test_successor_signing_integration as base
import test_restricted_successor_signer as key_fixtures
from test_signed_exit_timing import files


class ExecutionTests(unittest.TestCase):
    setUpClass=classmethod(base.IntegrationTests.setUpClass.__func__)
    tearDownClass=classmethod(base.IntegrationTests.tearDownClass.__func__)
    setUp=base.IntegrationTests.setUp
    tearDown=base.IntegrationTests.tearDown
    inputs=base.IntegrationTests.inputs
    rows=base.IntegrationTests.rows
    markers=key_fixtures.SuccessorBackendTests.markers
    def run_case(self,*,lost=True,sign_hook=None,send_hook=None):
        reads,quotes,clock=self.inputs();clock.at=max(clock.at,self.c.now+500);self.timer=clock
        rpc=Provider(self.c.path,lost=lost,hook=send_hook)
        def sign(root,wallet,pool,expected,request,current_clock):
            self.c.now=current_clock();self.candidate=expected
            wire=self.c.sign_successor(request);self.markers(wire)
            if sign_hook:sign_hook()
            return wire
        with patch.object(m.signing.backend,'_invoke',side_effect=sign):
            result=m._collect_sign_submit(self.c.home,self.c.wallet,self.c.pool,self.expected,self.retired,
                allow_unsigned_successor=True,allow_private_key_signing=True,allow_devnet_submit=True,
                expiry_opener=reads,quote_opener=quotes,submission_opener=rpc,clock=clock,monotonic=lambda:0)
        self.c.now=clock();return result,reads,quotes,rpc

    def test_full_composition_lost_send_and_exact_signature_recovery(self):
        before=self.rows();r,reads,quotes,rpc=self.run_case()
        self.assertEqual(r['state'],'successor-submission-unknown',r)
        self.assertEqual((len(reads.calls),len(quotes.calls),len(rpc.calls)),(8,20,5))
        self.assertEqual(r['networkRequestsThisRun'],33);self.assertEqual(r['sendRequestsThisRun'],1)
        self.assertTrue(r['completedWithinOriginalDeadline']);self.assertTrue(r['originalDeadlineCheckedBeforeSend'])
        self.assertIsNone(r['transactionsSent']);self.assertTrue(r['recoveryRequired'])
        self.c.now+=30000;(self.c.home/'STOP').touch(mode=0o600)
        recovered=m._recover(self.c.home,self.c.wallet,self.c.pool,r['successorSha256'],opener=rpc,clock=lambda:self.c.now)
        self.assertEqual(recovered['state'],'successor-finalized-evidence');self.assertFalse(recovered['reservationsReleased'])
        after=self.rows();self.assertEqual(before,{k:after[k] for k in before})
        self.assertNotIn(rpc.wire,str(r));self.assertNotIn('rpcEvidence',str(r))

    def test_repeated_composition_does_not_refresh_sign_or_send(self):
        first,_,_,_=self.run_case(lost=False);self.assertEqual(first['state'],'rpc-acknowledged')
        frozen=files(self.c)
        again,reads,quotes,rpc=self.run_case(sign_hook=lambda:self.fail('second signer'))
        self.assertEqual(again['state'],'existing-successor-held');self.assertEqual(reads.calls+quotes.calls+rpc.calls,[])
        self.assertEqual(files(self.c),frozen);self.assertEqual(again['sendRequestsThisRun'],0)

    def test_late_signer_response_never_reaches_submission(self):
        def late():self.timer.at+=10000
        r,_,_,rpc=self.run_case(sign_hook=late)
        self.assertTrue(r['signing']['signerAcknowledgmentValidated']);self.assertFalse(r['completedWithinOriginalDeadline'])
        self.assertFalse(rpc.calls);self.assertEqual(r['sendRequestsThisRun'],0)

    def test_expiry_during_preflight_prevents_send_and_preserves_signed_state(self):
        def late(method):
            if method=='getFeeForMessage':self.timer.at+=10000
        r,_,_,rpc=self.run_case(send_hook=late)
        self.assertFalse(r['completedWithinOriginalDeadline']);self.assertEqual(r['sendRequestsThisRun'],0)
        self.assertNotIn('sendTransaction',rpc.calls)
        status=m.submission._status(self.c.home,self.c.wallet,self.c.pool,r['successorSha256'],clock=lambda:self.c.now)
        self.assertEqual(status['state'],'not-attempted')

    def test_stop_during_preflight_never_reaches_send(self):
        def stop(method):
            if method=='getFeeForMessage':(self.c.home/'STOP').touch(mode=0o600)
        r,_,_,rpc=self.run_case(send_hook=stop)
        self.assertEqual(r['sendRequestsThisRun'],0);self.assertFalse(r['completedWithinOriginalDeadline'])
        self.assertNotIn('sendTransaction',rpc.calls);self.assertTrue(r['signing']['signerAcknowledgmentValidated'])
        status=m.submission._status(self.c.home,self.c.wallet,self.c.pool,r['successorSha256'],clock=lambda:self.c.now)
        self.assertEqual(status['state'],'not-attempted')

    def test_late_send_reply_retained_but_never_passes_original_deadline(self):
        def late(method):
            if method=='sendTransaction':self.timer.at+=10000
        r,_,_,rpc=self.run_case(send_hook=late)
        self.assertEqual(r['sendRequestsThisRun'],1);self.assertTrue(r['originalDeadlineCheckedBeforeSend'])
        self.assertFalse(r['completedWithinOriginalDeadline']);self.assertTrue(r['applicationSendBoundaryRecorded'])
        self.assertEqual(r['submission']['state'],'successor-submission-unknown');self.assertTrue(r['recoveryRequired'])
        self.assertEqual(m._recover(self.c.home,self.c.wallet,self.c.pool,r['successorSha256'],opener=rpc,clock=lambda:self.c.now)['state'],'successor-finalized-evidence')

    def test_exception_after_commit_keeps_unknown_effects_and_no_retry(self):
        request=m.submission.transport.SendRpc.request
        def fail(client,method,params):
            if method=='sendTransaction':raise OSError('PRIVATE_PROVIDER_DETAIL')
            return request(client,method,params)
        with patch.object(m.submission.transport.SendRpc,'request',fail):r,_,_,rpc=self.run_case()
        self.assertTrue(r['recoveryRequired']);self.assertIsNone(r['applicationSendBoundaryRecorded'])
        self.assertEqual(r['senderRequests'],4);self.assertEqual(r['sendRequestsThisRun'],0);self.assertNotIn('PRIVATE',str(r))
        status=m.submission._status(self.c.home,self.c.wallet,self.c.pool,r['successorSha256'],clock=lambda:self.c.now)
        self.assertEqual(status['state'],'successor-submission-unknown')
        again,reads,quotes,rpc=self.run_case();self.assertEqual(again['state'],'existing-successor-held');self.assertEqual(reads.calls+quotes.calls+rpc.calls,[])

    def test_optins_and_all_injected_providers_required_before_access(self):
        with patch.object(m,'_run',side_effect=AssertionError('access')):
            opts=dict(allow_unsigned_successor=True,allow_private_key_signing=True,allow_devnet_submit=True)
            for key in opts:
                for val in (False,1,'yes',None):
                    flags=dict(opts);flags[key]=val
                    with self.assertRaises(ValueError):m._collect_sign_submit('/missing','w','p','a'*64,'b'*64,**flags)
            with self.assertRaisesRegex(ValueError,'successor-execution-injected-providers-required'):
                m._collect_sign_submit('/missing','w','p','a'*64,'b'*64,**opts)

    def test_transport_generation_guard_blocks_mismatched_request(self):
        def wrong(*args,**kw):
            kw['_guard']('sendTransaction',dict(request=dict(successorSha256='0'*64,validUntilExclusiveMs=1)))
            raise AssertionError('guard accepted')
        with patch.object(m.submission,'_submit',side_effect=wrong):r,_,_,rpc=self.run_case()
        self.assertEqual(r['diagnosticCode'],'successor-execution-identity');self.assertFalse(rpc.calls)
        self.assertFalse(r['completedWithinOriginalDeadline'])

    def test_original_operation_budget_is_checked_before_every_sender_request(self):
        tick=[0]
        original=m.submission._submit
        def exhausted(*a,**kw):
            tick[0]=121
            return original(*a,**kw)
        # The transport has its own budget; its enclosing guard must also retain
        # the composition's earlier start rather than resetting at signing.
        with patch.object(m.submission,'_submit',side_effect=exhausted):
            reads,quotes,clock=self.inputs();clock.at=max(clock.at,self.c.now+500)
            def sign(root,wallet,pool,expected,request,current_clock):
                self.c.now=current_clock();self.candidate=expected;wire=self.c.sign_successor(request);self.markers(wire);return wire
            rpc=Provider(self.c.path)
            with patch.object(m.signing.backend,'_invoke',side_effect=sign):
                r=m._collect_sign_submit(self.c.home,self.c.wallet,self.c.pool,self.expected,self.retired,
                    allow_unsigned_successor=True,allow_private_key_signing=True,allow_devnet_submit=True,
                    expiry_opener=reads,quote_opener=quotes,submission_opener=rpc,clock=clock,monotonic=lambda:tick[0])
        self.assertEqual(r['diagnosticCode'],'successor-execution-budget');self.assertFalse(rpc.calls)

    def test_owner_cleanup_cannot_hide_a_late_return(self):
        class Stub:
            def open(self,*args,**kw):raise AssertionError('provider')
        def result(*a,**kw):
            return dict(state='rpc-acknowledged',timing={},originalDeadlineMs=101,completedAtMs=100,
                completedWithinOriginalDeadline=True,sendRequestsThisRun=1)
        with patch.object(m,'_run',side_effect=result):
            r=m._collect_sign_submit('/unused','w','p','a'*64,'b'*64,allow_unsigned_successor=True,
                allow_private_key_signing=True,allow_devnet_submit=True,expiry_opener=Stub(),quote_opener=Stub(),
                submission_opener=Stub(),clock=lambda:102,monotonic=lambda:0)
        self.assertEqual(r['stage'],'return-boundary');self.assertFalse(r['completedWithinOriginalDeadline'])
        self.assertEqual(r['headroomAtReturnMs'],-1);self.assertEqual(r['sendRequestsThisRun'],1)


if __name__=='__main__':unittest.main()
