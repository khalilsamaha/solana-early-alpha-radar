import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import orchestrate as o
from capture import CaptureError,canonical,digest


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='r1-orchestrate-test-');self.root=Path(self.tmp.name)
        registration=self.root/'registration';registration.mkdir(mode=0o700)
        self.sha=o.contract.freeze(registration)['contract_sha256'];self.contract=registration/'contract.json'
        self.control=self.root/'control';self.control.mkdir(mode=0o700)
    def tearDown(self):self.tmp.cleanup()
    def run_case(self,scenario='normal'):
        return o.run(self.control,self.contract,self.sha,scenario,pipe_only=True)
    def unchanged(self):
        return {str(p.relative_to(self.control)):(p.lstat().st_mode,p.read_bytes() if p.is_file() else None)
                for p in self.control.rglob('*')}

    def test_three_integrated_outcomes_are_preserved_and_no_inspection_side_effects(self):
        for name in o.SCENARIOS:
            if name!='normal':self.control=self.root/name;self.control.mkdir(mode=0o700)
            r=self.run_case(name);interrupted=name=='shutdown-interruption'
            self.assertEqual(r['operation_failed'],interrupted)
            self.assertTrue(r['completion']['finalization_complete'])
            self.assertEqual(r['completion']['reconciliation_required'],interrupted)
            self.assertEqual(r['cleanup']['direct_restore_calls'],0 if interrupted else 1)
            self.assertTrue(all(a['process_reaped'] for a in r['cleanup']['actors']))
            before=self.unchanged()
            with patch.object(o,'Backend',side_effect=AssertionError('inspection executed adapter')):
                observed=o.inspect(self.control)
            self.assertEqual(self.unchanged(),before)
            self.assertTrue(observed['finalization_complete'])
            self.assertEqual(observed['reconciliation_required'],interrupted)
            self.assertFalse(observed['automatic_resume_allowed'])

    def test_admission_and_lifecycle_claim_precede_first_actor(self):
        original=o.Backend.prepare;observed=[]
        def guarded(backend):
            admission,_=o.read(self.control,'admission.json')
            claim,_=o.read(self.control/'lifecycle-registry','claim.json')
            self.assertEqual(admission['contract_sha256'],self.sha)
            self.assertEqual(claim['registration_id'],self.sha)
            observed.append(True);return original(backend)
        with patch.object(o.Backend,'prepare',guarded):self.run_case()
        self.assertEqual(observed,[True])

    def test_consumed_control_never_rearms_or_invokes_adapter(self):
        self.run_case();before=self.unchanged()
        with patch.object(o,'Backend',side_effect=AssertionError('rearmed')) as backend:
            with self.assertRaises(CaptureError):self.run_case('cleanup-failure')
            backend.assert_not_called()
        self.assertEqual(self.unchanged(),before)

    def test_live_mode_and_nonboolean_transport_rejected(self):
        with patch.object(o,'Backend') as backend:
            for name,pipe in (('live',True),('normal',1)):
                with self.assertRaises(CaptureError):o.run(self.control,self.contract,self.sha,name,pipe_only=pipe)
            backend.assert_not_called()
        self.assertEqual(list(self.control.iterdir()),[])

    def test_wrong_hash_or_edited_approval_fails_before_admission(self):
        with self.assertRaises(CaptureError):o.run(self.control,self.contract,'0'*64,'normal',pipe_only=True)
        row=o.strict_json(self.contract.read_bytes());row['proposal']['live_launch_authorized']=True
        raw=(canonical(row)+'\n').encode();self.contract.write_bytes(raw)
        with self.assertRaises(CaptureError):o.run(self.control,self.contract,digest(raw),'normal',pipe_only=True)
        self.assertEqual(list(self.control.iterdir()),[])

    def test_preservation_failure_never_publishes_completion(self):
        with patch.object(o.preserve,'preserve',side_effect=OSError('synthetic storage failure')):
            with self.assertRaises(OSError):self.run_case()
        self.assertTrue((self.control/'finalization-intent.json').exists())
        self.assertFalse((self.control/'completion.json').exists())
        self.assertFalse(o.inspect(self.control)['finalization_complete'])
        cleanup,_=o.read(self.control,'cleanup.json');self.assertTrue(cleanup['broker_reaped'])
        with self.assertRaises(CaptureError):self.run_case()

    def test_restore_failure_keeps_archive_but_no_completion(self):
        with patch.object(o.preserve,'restore',side_effect=OSError('synthetic restore failure')):
            with self.assertRaises(OSError):self.run_case()
        self.assertTrue((self.control/'preserved/evidence.zip').exists())
        self.assertFalse((self.control/'completion.json').exists())
        self.assertTrue(o.inspect(self.control)['reconciliation_required'])

    def test_receipt_write_failure_never_retries_or_counts_as_complete(self):
        original=o.write
        def failing(directory,name,row):
            if name=='completion.json':raise OSError('synthetic receipt failure')
            return original(directory,name,row)
        with patch.object(o,'write',failing):
            with self.assertRaises(OSError):self.run_case()
        self.assertTrue((self.control/'restored/report.json').exists())
        self.assertFalse(o.inspect(self.control)['finalization_complete'])
        with self.assertRaises(CaptureError):self.run_case()

    def test_unconfirmed_cleanup_cannot_start_preservation(self):
        original=o.Backend.close
        def failing(backend):original(backend);raise CaptureError('synthetic cleanup uncertainty')
        with patch.object(o.Backend,'close',failing),patch.object(o.preserve,'preserve') as preservation:
            with self.assertRaises(CaptureError):self.run_case()
            preservation.assert_not_called()
        self.assertTrue((self.control/'cleanup.json').exists())
        self.assertFalse((self.control/'completion.json').exists())

    def test_source_drift_blocks_finalization(self):
        original=o.pins();changed=dict(original);changed['r1-orchestration/orchestrate.py']='0'*64
        with patch.object(o,'pins',side_effect=[original,changed]):
            with self.assertRaises(CaptureError):self.run_case()
        self.assertFalse((self.control/'preserved').exists())
        self.assertFalse((self.control/'completion.json').exists())

    def test_receipt_intent_archive_and_restored_mutations_require_reconciliation(self):
        self.run_case()
        for name in ('completion.json','finalization-intent.json','admission.json','cleanup.json',
                     'preserved/evidence.zip','restored/capture.db','runtime/broker/session.jsonl'):
            path=self.control/name;raw=path.read_bytes();path.write_bytes(raw+b' ')
            before=self.unchanged();result=o.inspect(self.control)
            self.assertTrue(result['reconciliation_required']);self.assertFalse(result['finalization_complete'])
            self.assertEqual(self.unchanged(),before);path.write_bytes(raw)
        self.assertTrue(o.inspect(self.control)['finalization_complete'])

    def test_missing_control_inspection_creates_nothing(self):
        missing=self.root/'missing';r=o.inspect(missing)
        self.assertTrue(r['reconciliation_required']);self.assertFalse(missing.exists())

    def test_busy_control_refuses_second_run_without_side_effects(self):
        with o.owner_lock(self.control):
            with self.assertRaises(CaptureError):self.run_case()
            self.assertFalse(o.inspect(self.control)['finalization_complete'])
            self.assertEqual({p.name for p in self.control.iterdir()},{'r1-supervisor.lock'})


if __name__=='__main__':unittest.main()
