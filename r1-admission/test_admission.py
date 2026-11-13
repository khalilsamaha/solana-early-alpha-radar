from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import admission as ad


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='r1-admission-test-')
        self.root = Path(self.tmp.name)
        self.registry = self.root/'registry'; self.registry.mkdir(mode=0o700)
        self.output = self.root/'run'

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self):
        # Fixed failed spawn leaves a real durable, source-bound consumed admission.
        with patch.object(ad.subprocess, 'Popen', side_effect=OSError('synthetic failure')):
            result = ad.run(self.registry, self.output, development=True)
        self.assertEqual(result['status'], 'supervised-admission-failed-live-blocked')
        self.assertEqual(result['workers_started'], 0)
        return result

    def test_success_is_independently_replayed_and_bound_before_launch(self):
        result = ad.run(self.registry, self.output, development=True)
        self.assertEqual(result['status'], 'supervised-admission-development-passed-unix-pending')
        self.assertTrue(result['worker_reaped'])
        self.assertEqual(result['evidence']['assessment']['local_session_outcome'], 'capture-stopped')
        request, raw = ad.load_request(self.output)
        self.assertEqual(result['request_sha256'], ad.digest(raw))
        admitted = ad.a.row((self.output/'control/admission.json').read_bytes())
        self.assertEqual(admitted['limits'], request['limits'])
        self.assertFalse(result['live_launch_authorized'])
        self.assertFalse(result['evidence']['assessment']['precollection_approval_proven'])
        with patch.object(ad.subprocess, 'Popen') as spawn:
            with self.assertRaises(ad.CaptureError):
                ad.run(self.registry, self.root/'different-output', development=True)
            spawn.assert_not_called()
        self.assertFalse((self.root/'different-output').exists())
        before = {str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(ad.subprocess, 'Popen') as spawn:
            recovery = ad.inspect(self.registry,self.output)
            spawn.assert_not_called()
        self.assertFalse(recovery['reconciliation_required'])
        self.assertFalse(recovery['automatic_resume_allowed'])
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_failed_spawn_consumes_registry_before_any_retry(self):
        self.prepare()
        self.assertTrue((self.registry/'claim.json').exists())
        with patch.object(ad.credential, 'load_descriptor') as load:
            with self.assertRaises(ad.CaptureError):
                ad.run(self.registry, self.root/'new-output', development=True)
            load.assert_not_called()
        self.assertTrue(ad.inspect(self.registry,self.output)['reconciliation_required'])

    def test_missing_terminal_receipt_requires_reconciliation_without_writes(self):
        self.prepare()
        (self.output/'supervisor.json').unlink()  # deliberate crash fixture
        before = {str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = ad.inspect(self.registry,self.output)
        self.assertEqual(result['state'],'admitted-outcome-unconfirmed')
        self.assertTrue(result['reconciliation_required'])
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_recovery_rejects_false_success_and_live_authority(self):
        self.prepare()
        path = self.output/'supervisor.json'; row = ad.a.row(path.read_bytes())
        for changes in ({'live_launch_authorized':True}, {'worker_reaped':1},
                        {'status':'supervised-admission-development-passed-unix-pending'}):
            with self.subTest(changes=changes):
                path.write_bytes(ad.s.json_bytes({**row,**changes}))
                with self.assertRaises(ad.CaptureError): ad.inspect(self.registry,self.output)

    def test_native_consumer_cannot_hide_missing_discovery_or_second_upstream(self):
        row={'creations':1,'tokens':1,'discovery_gaps':1,'upstream_connections_opened':0,'sources':['pumpportal:create']}
        ad.node_result('normal',row)
        for changes in ({'creations':0},{'upstream_connections_opened':1},{'sources':[]},{'extra':True}):
            with self.assertRaises(ad.CaptureError): ad.node_result('normal',{**row,**changes})

    def test_missing_worker_receipt_is_not_repaired(self):
        self.prepare()
        request, raw = ad.load_request(self.output)
        with self.assertRaises((ad.CaptureError,OSError)):
            ad.verify_evidence(self.output,request,raw)
        self.assertFalse((self.output/'worker-result.json').exists())

    def test_credential_failure_cannot_release_claim(self):
        with patch.object(ad.credential, 'load_descriptor', side_effect=ad.CaptureError('synthetic')):
            with patch.object(ad.subprocess, 'Popen') as spawn:
                result = ad.run(self.registry, self.output, development=True)
                spawn.assert_not_called()
        self.assertEqual(result['failure_stage'], 'credential')
        self.assertTrue((self.registry/'claim.json').exists())

    def test_invalid_request_edits_fail_closed(self):
        self.prepare()
        path = self.output/'request.json'; original = path.read_bytes()
        row = ad.a.row(original)
        changes = ({'live_launch_authorized':True}, {'automatic_resume_allowed':True},
                   {'production_handoff_verified':True}, {'source_sha256':{}},
                   {'limits':{**row['limits'],'messages':5}}, {'development_endpoint':1},
                   {'extra':'unsupported'}, {'parent_pid':True})
        for change in changes:
            with self.subTest(change=change):
                path.write_bytes(ad.s.json_bytes({**row, **change}))
                with self.assertRaises(ad.CaptureError): ad.load_request(self.output)
        path.write_bytes(original)
        ad.load_request(self.output)

    def test_draft_mutation_cannot_be_promoted_to_approved(self):
        self.prepare()
        path = self.output/'registration/contract.json'
        row = ad.a.row(path.read_bytes()); row['proposal']['live_launch_authorized'] = True
        path.write_bytes(ad.s.json_bytes(row))
        with self.assertRaises(ad.CaptureError): ad.load_request(self.output)

    def test_replaced_claim_is_rejected(self):
        self.prepare()
        path = self.registry/'claim.json'
        row = ad.a.row(path.read_bytes()); row['output'] = str(self.root/'other')
        path.write_bytes(ad.s.json_bytes(row))
        with self.assertRaises(ad.CaptureError): ad.load_request(self.output)

    def test_overlapping_paths_do_not_claim_or_start(self):
        with patch.object(ad.subprocess, 'Popen') as spawn:
            with self.assertRaises(ad.CaptureError):
                ad.run(self.registry, self.registry/'child', development=True)
            spawn.assert_not_called()
        self.assertFalse((self.registry/'claim.json').exists())

    def test_unknown_scenario_or_non_boolean_mode_does_not_claim(self):
        for scenario, dev in (('live',False), ('normal',1)):
            with self.assertRaises(ad.CaptureError):
                ad.run(self.registry, self.output, scenario, development=dev)
        self.assertFalse((self.registry/'claim.json').exists())

    def test_worker_receipt_tampering_cannot_pass_on_zero_exit(self):
        result = ad.run(self.registry, self.output, development=True)
        self.assertTrue(result['worker_reaped'])
        request, raw = ad.load_request(self.output)
        path = self.output/'worker-result.json'; row = ad.a.row(path.read_bytes())
        row['credential_descriptor_closed'] = False
        path.write_bytes(ad.s.json_bytes(row))
        with self.assertRaises(ad.CaptureError): ad.verify_result(self.output, request, raw)

    def test_cleanup_failure_stays_failed_inside_complete_evidence(self):
        result = ad.run(self.registry, self.output, 'cleanup-failure', development=True)
        self.assertEqual(result['status'], 'supervised-admission-development-passed-unix-pending')
        self.assertEqual(result['evidence']['assessment']['local_session_outcome'], 'transport-cleanup-failed')
        self.assertFalse(result['evidence']['assessment']['live_launch_authorized'])

    def test_secret_bearing_diagnostic_refuses_completion_and_is_not_retained(self):
        result = ad.run(self.registry, self.output, 'tainted-diagnostic', development=True)
        self.assertEqual(result['status'], 'supervised-admission-failed-live-blocked')
        self.assertTrue(result['worker_reaped'])
        self.assertFalse((self.output/'worker-result.json').exists())
        self.assertFalse((self.output/'export').exists())
        for path in self.output.rglob('*'):
            if path.is_file(): self.assertNotIn(b'R1-SYNTHETIC-', path.read_bytes())


if __name__ == '__main__': unittest.main()
