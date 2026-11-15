import copy
import unittest
from unittest.mock import patch
import test_capture_session as fixtures
import manifest_supervisor as v
import scanner_peer
session=v.session;m=v.m;p=v.p


class ScannerPeerTests(unittest.TestCase):
    def setUp(self):fixtures.CaptureSessionTests.setUp(self)
    def run_scanner(self,mode='session-scanner-normal'):return v.run(self.plan,self.sha,mode=mode)
    def recover(self):return v.inspect(self.registry,self.sha)

    def test_real_node_receives_post_retirement_creation_and_both_children_reaped(self):
        row=self.run_scanner();self.assertEqual(row['outcome'],v.SUCCESS)
        self.assertTrue(row['worker_reaped']);self.assertTrue(row['scanner']['reaped'])
        self.assertEqual(row['scanner']['returncode'],0)
        self.assertEqual(row['scanner']['result'],scanner_peer.expected('session-scanner-normal'))
        self.assertEqual(row['scanner']['result']['creations'],2)
        self.assertEqual(row['terminal']['session_evidence']['transport'],'pipe')
        self.assertTrue(row['terminal']['session_evidence']['discovery_continued_after_retirement'])
        self.assertFalse(row['scanner']['manifest_kernel_limits_applied'])
        self.assertFalse(row['scanner']['image_verified'])
        before=fixtures.CaptureSessionTests.files(self)
        with patch.object(scanner_peer.Scanner,'start',side_effect=AssertionError('start')),\
             patch.object(v.subprocess,'Popen',side_effect=AssertionError('spawn')):
            self.assertEqual(self.recover(),row)
        self.assertEqual(before,fixtures.CaptureSessionTests.files(self))
        with self.assertRaises(ValueError):self.run_scanner()

    def test_cleanup_failure_stops_discovery_without_later_creation(self):
        row=self.run_scanner('session-scanner-cleanup-failure');self.assertEqual(row['outcome'],v.SUCCESS)
        self.assertEqual(row['scanner']['result']['tokens'],2)
        self.assertEqual(row['terminal']['session_evidence']['research_cleanup'],'upstream-aborted')
        self.assertFalse(row['terminal']['session_evidence']['discovery_continued_after_retirement'])
        self.assertEqual(self.recover(),row)

    def test_lost_scanner_confirmation_cannot_confirm_capture_success(self):
        original=scanner_peer.Scanner.finish
        def lost(actor,*args):original(actor,*args);raise OSError('lost-response')
        with patch.object(scanner_peer.Scanner,'finish',lost):row=self.run_scanner()
        self.assertEqual(row['outcome'],'worker-failed');self.assertIsNone(row['terminal'])
        self.assertTrue(row['worker_reaped']);self.assertTrue(row['scanner']['reaped'])
        self.assertEqual(self.recover(),row)

    def test_scanner_started_but_ready_return_lost_never_starts_capture(self):
        original=scanner_peer.Scanner.start
        def lost(actor,*args):original(actor,*args);raise OSError('lost-ready')
        with patch.object(scanner_peer.Scanner,'start',lost):row=self.run_scanner()
        self.assertEqual(row['outcome'],'worker-start-failed');self.assertEqual(row['workers_started'],0)
        self.assertEqual(row['scanner']['started'],1);self.assertTrue(row['scanner']['reaped'])
        self.assertFalse(session.directory(self.manifest).exists())
        self.assertEqual(self.recover(),row)

    def test_worker_start_failure_reaps_already_started_scanner(self):
        original=v.subprocess.Popen
        def popen(command,*args,**kwargs):
            if command[0]==v.sys.executable:raise OSError('private-detail')
            return original(command,*args,**kwargs)
        with patch.object(v.subprocess,'Popen',side_effect=popen):row=self.run_scanner()
        self.assertEqual(row['workers_started'],0);self.assertTrue(row['scanner']['reaped'])
        self.assertEqual(row['outcome'],'worker-start-failed')
        self.assertNotIn(b'private-detail',b''.join(fixtures.CaptureSessionTests.files(self).values()))

    def test_node_unavailable_consumes_claim_without_capture(self):
        with patch.object(scanner_peer.shutil,'which',return_value=None):row=self.run_scanner()
        self.assertEqual(row['outcome'],'worker-start-failed');self.assertEqual(row['scanner']['started'],0)
        self.assertFalse(row['scanner']['reaped']);self.assertEqual(self.recover(),row)
        with self.assertRaises(ValueError):self.run_scanner()

    def test_uncertain_scanner_reaping_leaves_supervision_unresolved(self):
        original=scanner_peer.Scanner.close
        def uncertain(actor,*args):original(actor,*args);raise ValueError('uncertain')
        with patch.object(scanner_peer.Scanner,'close',uncertain):
            with self.assertRaises(ValueError):self.run_scanner()
        self.assertEqual(self.recover()['outcome'],'supervision-unresolved')
        self.assertIsNone(self.recover()['worker_reaped'])

    def test_capacity_failure_cannot_even_construct_scanner(self):
        original=p.s.sample
        with patch.object(p.s,'sample',side_effect=lambda fd:{**original(fd),'available_bytes':0}),\
             patch.object(scanner_peer,'Scanner',side_effect=AssertionError('actor')):
            with self.assertRaisesRegex(ValueError,'runtime-session-storage'):self.run_scanner()
        self.assertEqual(self.recover()['outcome'],'supervision-unresolved')

    def test_scanner_receipt_tampering_rejects_success(self):
        row=self.run_scanner();self.assertEqual(row['outcome'],v.SUCCESS)
        for mutate in (lambda x:x.update(reaped=False),lambda x:x.update(image_verified=True),
                       lambda x:x.update(started=True),lambda x:x.update(returncode=1),
                       lambda x:x.update(result=None),lambda x:x['result'].update(tokens=2),
                       lambda x:x.update(manifest_kernel_limits_applied=True)):
            changed=copy.deepcopy(row);mutate(changed['scanner'])
            (self.registry/v.RESULT).write_bytes(m.raw(changed))
            with self.assertRaises(ValueError):self.recover()

    def test_long_duration_not_supported_by_short_scanner_fixture(self):
        changed=m.build(self.config,{**self.policy,'service_seconds':6})
        with self.assertRaisesRegex(ValueError,'scanner-fixture-duration'):
            session.validate_mode(changed,'session-scanner-normal')
        self.assertFalse((self.registry/v.CLAIM).exists())

    def test_zero_exit_incomplete_scanner_result_cannot_confirm_success(self):
        original=scanner_peer.Scanner.finish
        def incomplete(actor,deadline,mode,collect):
            def corrupted(process,seconds):
                raw,outcome=collect(process,seconds)
                value=m.parse(raw);value['tokens']=0
                return m.raw(value),outcome
            return original(actor,deadline,mode,corrupted)
        with patch.object(scanner_peer.Scanner,'finish',incomplete):row=self.run_scanner()
        self.assertEqual(row['outcome'],'worker-failed');self.assertIsNone(row['terminal'])
        self.assertTrue(row['scanner']['reaped']);self.assertEqual(row['scanner']['returncode'],0)
        self.assertIsNone(row['scanner']['result']);self.assertEqual(self.recover(),row)

    def test_input_change_after_scanner_ready_prevents_capture_and_reaps_scanner(self):
        original_start=scanner_peer.Scanner.start;original_pins=v.r.pins;actors=[];changed=False
        def start(actor,*args):
            nonlocal changed
            original_start(actor,*args);actors.append(actor);changed=True
        with patch.object(scanner_peer.Scanner,'start',start),\
             patch.object(v.r,'pins',side_effect=lambda:{'changed':'0'*64} if changed else original_pins()):
            with self.assertRaisesRegex(ValueError,'runtime-final-binding'):self.run_scanner()
        self.assertFalse(session.directory(self.manifest).exists());self.assertEqual(len(actors),1)
        self.assertIsNotNone(actors[0].process.returncode)
        self.assertEqual(self.recover()['outcome'],'supervision-unresolved')


if __name__=='__main__':unittest.main()
