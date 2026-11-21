import copy
import io
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
import warnings
from unittest.mock import patch
import zipfile
import handoff_evidence as evidence
import check_handoff_evidence as reader
import test_guarded_session as fixtures
c=evidence.c


class HandoffEvidenceTests(unittest.TestCase):
    setUp=fixtures.GuardedTests.setUp
    make=fixtures.GuardedTests.make
    stopped=fixtures.GuardedTests.stopped

    def complete(self):
        with self.guard.open() as ctrl:
            self.stopped(ctrl);self.guard.run_shared();ctrl.step('start_original');ctrl.step('restore_restart');self.guard.complete()
        evidence.capture_evidence.export(Path(self.paths['capture'])/'supervised-session',self.run/'export/session')
        return evidence.snapshot(self.run,self.registry,self.service)

    def test_actual_pipe_session_and_service_completion_survive_portable_replay(self):
        data=self.complete();raw,assessment=evidence.make(data)
        self.assertEqual(assessment['classification'],'closed-restored-offline-handoff-evidence',assessment)
        self.assertFalse(assessment['components']['native_application_verified'])
        self.assertFalse(assessment['components']['native_disposal_verified'])
        # Original host paths are deliberately unavailable to the reader.
        original=evidence.a.storage.open_directory
        def forbid_original(path):
            self.assertFalse(str(path).startswith(str(self.root)))
            return original(path)
        with patch.object(evidence.a.storage,'open_directory',side_effect=forbid_original):
            restored,result=evidence.verify(raw,c.digest(raw))
        self.assertEqual(restored,data);self.assertEqual(result,assessment)
        self.assertFalse(result['activation_authorized']);self.assertFalse(result['automatic_resume_allowed'])

    def test_export_is_exclusive_and_reads_back_exact_bytes(self):
        self.complete();destination=self.run/'handoff.zip'
        receipt=evidence.export(self.run,self.registry,self.service,destination)
        self.assertEqual(receipt['sha256'],c.digest(destination.read_bytes()))
        self.assertTrue(receipt['local_export_and_restore_verified']);self.assertFalse(receipt['remote_preservation_verified'])
        with self.assertRaises(FileExistsError):evidence.export(self.run,self.registry,self.service,destination)

    def test_read_only_reader_distinguishes_complete_quarantine_and_invalid_input(self):
        data=self.complete()
        for complete in (True,False):
            if not complete:del data['service/'+evidence.guarded.service.RESULT]
            raw,_=evidence.make(data);path=self.run/('complete.zip' if complete else 'quarantine.zip');c.write_new(path,raw)
            output=io.StringIO()
            with redirect_stdout(output):code=reader.main(['--archive',str(path),'--sha256',c.digest(raw)])
            result=c.parse(output.getvalue().encode());self.assertEqual(code,0 if complete else 2)
            self.assertEqual(result['status'],'verified-historical-offline-evidence')
            self.assertFalse(result['live_host_observed']);self.assertEqual(path.read_bytes(),raw)
        output=io.StringIO()
        with redirect_stdout(output):code=reader.main(['--archive',str(path),'--sha256','0'*64])
        self.assertEqual(code,1);self.assertNotIn(str(path),output.getvalue())
        self.assertEqual(c.parse(output.getvalue().encode())['status'],'invalid-or-unavailable-handoff-evidence')

    def test_missing_service_confirmation_quarantines_otherwise_restored_evidence(self):
        data=self.complete();del data['service/'+evidence.guarded.service.RESULT]
        raw,assessment=evidence.make(data)
        self.assertEqual(assessment['classification'],'quarantined-handoff-evidence')
        self.assertIn('invalid-service-evidence',assessment['reasons'])
        self.assertTrue(assessment['components']['control']['original_restored'])
        self.assertEqual(evidence.verify(raw,c.digest(raw))[1],assessment)

    def test_missing_supervision_or_bridge_cannot_be_reconstructed_from_capture(self):
        data=self.complete()
        for name in ('registry/'+evidence.v.RESULT,'registry/'+evidence.shared.RESULT,'registry/worker-credential.json'):
            changed=dict(data);del changed[name];assessment=evidence.assess(changed)
            self.assertEqual(assessment['classification'],'quarantined-handoff-evidence')
            self.assertEqual(assessment['components']['capture']['classification'],'closed-clean-session-evidence')

    def test_corrupted_control_or_mixed_claim_is_not_promoted(self):
        data=self.complete()
        for name in ('registry/claim.json','registry/'+evidence.shared.INTENT,'registry/'+evidence.guarded.CLAIM):
            changed=dict(data);value=c.parse(changed[name])
            if name.endswith('/claim.json'):value['source_sha256']='0'*64
            elif name.endswith(evidence.shared.INTENT):value['control_events_sha256']='0'*64
            else:value['service_attempt_sha256']='0'*64
            changed[name]=c.raw(value)
            self.assertEqual(evidence.assess(changed)['classification'],'quarantined-handoff-evidence')

    def test_missing_reordered_or_replaced_storage_gates_prevent_complete_handoff(self):
        data=self.complete();name='registry/retained-gate-03.json'
        for fault in ('missing','action','identity'):
            changed=dict(data)
            if fault=='missing':del changed[name]
            else:
                gate=c.parse(changed[name])
                if fault=='action':gate['action']='restore_restart'
                else:
                    for key in ('before','after'):gate['observation'][key]['capture']['inode']+=100
                changed[name]=c.raw(gate)
            with self.subTest(fault=fault):
                assessment=evidence.assess(changed)
                self.assertEqual(assessment['classification'],'quarantined-handoff-evidence')
                self.assertIn('invalid-preparation-evidence',assessment['reasons'])

    def test_portable_preparation_checks_always_bind_the_recorded_owner(self):
        data=self.complete();validate=evidence.a.prep.validate_observation;calls=[]
        uid=c.parse(data['registry/'+evidence.a.prep.CLAIM])['registry_identity']['uid']
        def replay(row,plan,claim,*,expected_uid=None):
            self.assertEqual(expected_uid,uid);calls.append(row)
            return validate(row,plan,claim,expected_uid=expected_uid)
        with patch.object(evidence.a.prep,'validate_observation',side_effect=replay):
            self.assertEqual(evidence.assess(data)['classification'],'closed-restored-offline-handoff-evidence')
        self.assertEqual(len(calls),7)

    def test_deadline_receipt_tampering_is_quarantined(self):
        data=self.complete();name='registry/'+evidence.guarded.RESULT
        for mutation in ('order','expired','boolean','clock-regression'):
            changed=dict(data);result=c.parse(changed[name]);timing=result['timing']
            if mutation=='order':timing['events'][0]['phase']='shared'
            elif mutation=='expired':timing['events'][1]['elapsed_seconds']=30
            elif mutation=='boolean':timing['events'][0]['elapsed_seconds']=True
            else:timing['events'][-1]['elapsed_seconds']=-1
            changed[name]=c.raw(result)
            self.assertEqual(evidence.assess(changed)['classification'],'quarantined-handoff-evidence')

    def test_authority_flags_are_never_promoted_by_repacked_hashes(self):
        data=self.complete();name='registry/'+evidence.guarded.CLAIM
        for value in (True,0,'false'):
            changed=dict(data);claim=c.parse(changed[name]);claim['activation_authorized']=value;changed[name]=c.raw(claim)
            raw,assessment=evidence.make(changed)
            self.assertIn('invalid-authority-evidence',assessment['reasons'])
            self.assertEqual(evidence.verify(raw,c.digest(raw))[1]['classification'],'quarantined-handoff-evidence')

    def test_rewriting_manifest_assessment_cannot_promote_quarantine(self):
        data=self.complete();del data['service/'+evidence.guarded.service.RESULT];raw,_=evidence.make(data)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:members={n:archive.read(n) for n in archive.namelist()}
        manifest=c.parse(members['manifest.json']);manifest['assessment']['classification']='closed-restored-offline-handoff-evidence'
        manifest['assessment']['reasons']=[];members['manifest.json']=c.raw(manifest);forged=evidence.pack(members)
        with self.assertRaisesRegex(ValueError,'handoff-envelope-binding'):evidence.verify(forged,c.digest(forged))

    def test_empty_interruption_is_preserved_as_quarantine(self):
        with self.guard.open() as ctrl:self.stopped(ctrl)
        data=evidence.snapshot(self.run,self.registry,self.service);raw,assessment=evidence.make(data)
        self.assertEqual(assessment['classification'],'quarantined-handoff-evidence')
        self.assertEqual(assessment['components']['control']['state'],'locally-stopped')
        self.assertEqual(evidence.verify(raw,c.digest(raw))[1],assessment)
        self.assertFalse(assessment['components']['service']['current_process_state_observed'])

    def test_application_snapshot_requires_disposal_and_rejects_unsafe_files(self):
        self.complete();directory=self.registry/evidence.app.DATA;directory.mkdir(mode=0o700)
        (directory/'radar.sqlite').write_bytes(b'fixture');(directory/'radar.sqlite').chmod(0o600)
        path=self.registry/'native-scanner-disposal.json'
        for removed in (False,True):
            if path.exists():path.unlink()
            c.write_new(path,c.raw({'removed':removed,'reaped':True}))
            data=evidence.snapshot(self.run,self.registry,self.service)
            self.assertEqual('application-data/radar.sqlite' in data,removed)
        (directory/'linked').symlink_to(directory/'radar.sqlite')
        data=evidence.snapshot(self.run,self.registry,self.service)
        self.assertFalse(any(n.startswith('application-data/') for n in data))
        self.assertIn('unavailable',c.parse(data['snapshot.json'])['application_snapshot'])

    def test_zip_path_compression_duplicates_and_wrong_digest_rejected_before_replay(self):
        with patch.object(evidence,'assess',side_effect=AssertionError('replay')):
            with self.assertRaisesRegex(ValueError,'handoff-external-digest'):evidence.verify(b'bad','0'*64)
            for name in ('../outside','/tmp/out','application-data/../outside','application-data//extra'):
                stream=io.BytesIO()
                with zipfile.ZipFile(stream,'w') as archive:archive.writestr(name,b'x')
                raw=stream.getvalue()
                with self.assertRaises(ValueError):evidence.verify(raw,c.digest(raw))
            for fault in ('compression','duplicate','permissions','extra','archive-comment'):
                stream=io.BytesIO()
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore',UserWarning)
                    with zipfile.ZipFile(stream,'w') as archive:
                        info=zipfile.ZipInfo('snapshot.json',(1980,1,1,0,0,0));info.create_system=3
                        info.external_attr=(0o100644 if fault=='permissions' else 0o100600)<<16
                        if fault=='compression':info.compress_type=zipfile.ZIP_DEFLATED
                        if fault=='extra':info.extra=b'\x01\x00\x00\x00'
                        archive.writestr(info,b'{}')
                        if fault=='duplicate':archive.writestr(info,b'{}')
                        if fault=='archive-comment':archive.comment=b'not-canonical'
                raw=stream.getvalue()
                with self.subTest(fault=fault),self.assertRaises(ValueError):evidence.verify(raw,c.digest(raw))
        for name in ('registry/secret.env','service/unrelated.json'):
            with self.assertRaises(ValueError):evidence.make({name:b'x'})


if __name__=='__main__':unittest.main()
