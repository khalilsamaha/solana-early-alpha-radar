import io
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import delivery as d
import transfer as t
from capture import CaptureError,digest,exclusive_file


class DeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=tempfile.TemporaryDirectory(prefix='r1-delivery-fixtures-');cls.root=Path(cls.fixture.name)
        cls.addClassCleanup(cls.fixture.cleanup)
        registration=cls.root/'registration';registration.mkdir(mode=0o700)
        sha=d.o.contract.freeze(registration)['contract_sha256'];cls.controls={};cls.packages={}
        for scenario in d.o.SCENARIOS:
            control=cls.root/scenario;control.mkdir(mode=0o700)
            d.o.run(control,registration/'contract.json',sha,scenario,pipe_only=True)
            output=cls.root/(scenario+'-export');d.export(control,output)
            cls.controls[scenario]=control;cls.packages[scenario]=(output/'package.zip').read_bytes()
    @classmethod
    def tearDownClass(cls):cls.fixture.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='r1-delivery-test-');self.local=Path(self.tmp.name)
        self.raw=self.packages['normal'];self.package=self.local/'package.zip';exclusive_file(self.package,self.raw)
        self.control=self.local/'transfer';self.control.mkdir(mode=0o700)
        self.mirror=self.local/'mirror';self.mirror.mkdir(mode=0o700);self.transport=t.LocalMirror(self.mirror)
    def tearDown(self):self.tmp.cleanup()
    def run_transfer(self):return t.rehearse(self.control,self.package,digest(self.raw),self.transport)
    def snapshot(self,root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    def repack(self,contents):
        # Update the outer manifest, so inner receipt binding must catch the attack.
        _,inner=d.o.preserve.verify(contents['evidence.zip'])
        contents.pop('manifest.json',None)
        return d.pack({**contents,'manifest.json':d.json_bytes(d.manifest_for(contents,inner))})

    def test_three_portable_packages_restore_all_receipts_and_keep_quarantine(self):
        for name,raw in self.packages.items():
            package=self.local/(name+'.zip');exclusive_file(package,raw)
            before=self.snapshot(self.controls[name]);output=self.local/name
            restored=d.restore(package,digest(raw),output)
            self.assertEqual(restored['reconciliation_required'],name=='shutdown-interruption')
            self.assertEqual(restored['classification'],'quarantined-incomplete-evidence' if name=='shutdown-interruption' else 'complete-replayed-evidence')
            self.assertEqual(self.snapshot(self.controls[name]),before)
            self.assertFalse((output/'runtime').exists());self.assertFalse(restored['remote_preservation_verified'])
            contents,_,_=d.verify(raw,digest(raw))
            for member,value in contents.items():self.assertEqual((output/member).read_bytes(),value)

    def test_wrong_external_hash_and_nonhash_rejected_before_replay(self):
        with patch.object(d.o.preserve,'verify') as replay:
            for sha in ('0'*64,None,True,''):
                with self.assertRaises(CaptureError):d.verify(self.raw,sha)
            replay.assert_not_called()

    def test_recomputed_outer_hash_cannot_hide_cross_run_receipts(self):
        normal=d.unpack(self.raw);other=d.unpack(self.packages['cleanup-failure'])
        for member in ('admission.json','cleanup.json','finalization-intent.json','completion.json','evidence.zip'):
            changed={**normal,member:other[member]};raw=self.repack(changed)
            with self.subTest(member=member),self.assertRaises(CaptureError):d.verify(raw,digest(raw))

    def test_report_tampering_rejected_even_with_rebound_outer_manifest(self):
        for member in ('preservation-report.json','restore-report.json'):
            contents=d.unpack(self.raw);report=d.row(contents[member]);report['archive_bytes']+=1
            contents[member]=d.json_bytes(report);raw=self.repack(contents)
            with self.assertRaises(CaptureError):d.verify(raw,digest(raw))

    def test_live_flag_classification_and_source_manifest_spoofs_rejected(self):
        for key,value in (('live_launch_authorized',True),('classification','healthy'),('source_sha256',{}),('schema_version',True)):
            contents=d.unpack(self.raw);manifest=d.row(contents['manifest.json']);manifest[key]=value
            contents['manifest.json']=d.json_bytes(manifest);raw=d.pack(contents)
            with self.assertRaises(CaptureError):d.verify(raw,digest(raw))

    def test_zip_paths_compression_prefix_suffix_and_directory_count_rejected(self):
        contents=d.unpack(self.raw)
        for invalid in ('../escape','compression','duplicate'):
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED if invalid=='compression' else zipfile.ZIP_STORED) as archive:
                for i,(name,value) in enumerate(contents.items()):
                    archive.writestr('../escape' if invalid=='../escape' and i==0 else name,value)
                if invalid=='duplicate':archive.writestr('extra.json',b'{}')
            raw=stream.getvalue()
            with self.assertRaises(CaptureError):d.verify(raw,digest(raw))
        for raw in (b'prefix'+self.raw,self.raw+b'trailer',self.raw[:-22]+b'X'*22):
            with self.assertRaises(CaptureError):d.verify(raw,digest(raw))
        end=list(struct.unpack('<4s4H2LH',self.raw[-22:]));end[3]=end[4]=60000
        raw=self.raw[:-22]+struct.pack('<4s4H2LH',*end)
        with patch.object(d.zipfile,'ZipFile') as parser:
            with self.assertRaises(CaptureError):d.unpack(raw)
            parser.assert_not_called()

    def test_member_caps_checked_before_zip_read(self):
        with patch.dict(d.CAPS,{'evidence.zip':8}),patch.object(zipfile.ZipFile,'read') as read:
            with self.assertRaises(CaptureError):d.unpack(self.raw)
            read.assert_not_called()

    def test_source_drift_during_verification_rejected(self):
        before=d.pins();after={**before,'r1-delivery/delivery.py':'0'*64}
        with patch.object(d,'pins',side_effect=[before,before,after]):
            with self.assertRaises(CaptureError):d.verify(self.raw,digest(self.raw))

    def test_output_reuse_and_unsafe_source_rejected(self):
        output=self.local/'restored';d.restore(self.package,digest(self.raw),output);before=self.snapshot(output)
        with self.assertRaises(FileExistsError):d.restore(self.package,digest(self.raw),output)
        self.assertEqual(self.snapshot(output),before)
        link=self.local/'link.zip';link.symlink_to(self.package)
        with self.assertRaises(CaptureError):d.restore(link,digest(self.raw),self.local/'linked')
        self.package.chmod(0o644)
        with self.assertRaises(CaptureError):d.restore(self.package,digest(self.raw),self.local/'public')

    def test_export_refuses_busy_source_without_output(self):
        source=self.controls['normal'];output=self.local/'export'
        with d.o.preserve.existing_lock(source/'r1-supervisor.lock'):
            with self.assertRaises(CaptureError):d.export(source,output)
        self.assertFalse(output.exists())

    def test_export_detects_source_change_before_publication(self):
        source=self.controls['normal'];output=self.local/'export';original=d.read_private;calls=[]
        def changed(path,cap):
            raw=original(path,cap)
            if path==source/'completion.json':
                calls.append(True)
                if len(calls)>1:return raw+b' '
            return raw
        with patch.object(d,'read_private',changed):
            with self.assertRaises(CaptureError):d.export(source,output)
        self.assertFalse(output.exists())

    def test_transfer_intent_precedes_upload_completion_follows_independent_restore(self):
        original=self.transport.upload
        def upload(key,raw):
            self.assertTrue((self.control/'intent.json').exists())
            self.assertTrue((self.control/'package.zip').exists())
            self.assertFalse((self.control/'completion.json').exists());original(key,raw)
        with patch.object(self.transport,'upload',upload):result=self.run_transfer()
        self.assertEqual(self.transport.calls,['upload','download'])
        self.assertFalse(result['remote_preservation_verified']);self.assertFalse(result['retention_verified'])
        self.assertTrue(t.inspect(self.control)['finalization_complete'])

    def test_transfer_control_reuse_never_invokes_transport_or_changes_evidence(self):
        self.run_transfer();before=self.snapshot(self.control)
        with patch.object(self.transport,'upload') as upload:
            with self.assertRaises(CaptureError):self.run_transfer()
            upload.assert_not_called()
        self.assertEqual(self.snapshot(self.control),before)

    def test_uncertain_upload_retains_local_package_and_never_downloads_or_retries(self):
        original=self.transport.upload
        def uncertain(key,raw):original(key,raw);raise OSError('credential-sentinel-must-not-escape')
        with patch.object(self.transport,'upload',uncertain):
            with self.assertRaisesRegex(CaptureError,'^delivery-transfer-rehearsal-failed$'):self.run_transfer()
        self.assertEqual(self.transport.calls,['upload']);self.assertEqual(len(list(self.mirror.iterdir())),1)
        self.assertEqual((self.control/'package.zip').read_bytes(),self.raw)
        self.assertNotIn(b'credential-sentinel',(self.control/'failure.json').read_bytes())
        self.assertFalse(t.inspect(self.control)['finalization_complete'])
        with self.assertRaises(CaptureError):self.run_transfer()

    def test_wrong_truncated_oversized_download_never_completes(self):
        for i,bad in enumerate((b'X'+self.raw[1:],self.raw[:-1],self.raw+b'X')):
            if i:self.control=self.local/('transfer'+str(i));self.control.mkdir(mode=0o700)
            mirror=self.local/('mirror'+str(i));mirror.mkdir(mode=0o700);self.transport=t.LocalMirror(mirror)
            with patch.object(self.transport,'download',return_value=bad):
                with self.assertRaises(CaptureError):self.run_transfer()
            self.assertFalse((self.control/'completion.json').exists())
            self.assertTrue((self.control/'package.zip').exists())

    def test_download_exception_keeps_uncertain_object_without_delete(self):
        with patch.object(self.transport,'download',side_effect=OSError('offline download failure')):
            with self.assertRaises(CaptureError):self.run_transfer()
        self.assertEqual(len(list(self.mirror.iterdir())),1)
        self.assertFalse((self.control/'completion.json').exists())

    def test_restore_failure_does_not_publish_completion(self):
        with patch.object(d,'restore',side_effect=OSError('offline restore failure')):
            with self.assertRaises(CaptureError):self.run_transfer()
        self.assertEqual((self.control/'downloaded.zip').read_bytes(),self.raw)
        self.assertFalse((self.control/'completion.json').exists())

    def test_completion_write_failure_or_partial_receipt_requires_reconciliation(self):
        original=d.o.write
        def failed(directory,name,value):
            if name=='completion.json':exclusive_file(directory/name,b'{');raise OSError('offline full disk')
            return original(directory,name,value)
        with patch.object(d.o,'write',failed):
            with self.assertRaises(CaptureError):self.run_transfer()
        self.assertTrue((self.control/'restored/report.json').exists())
        self.assertFalse(t.inspect(self.control)['finalization_complete'])
        with self.assertRaises(CaptureError):self.run_transfer()

    def test_interrupted_transfer_consumes_control_and_preserves_diagnostics(self):
        with patch.object(self.transport,'upload',side_effect=KeyboardInterrupt):
            with self.assertRaises(CaptureError):self.run_transfer()
        self.assertTrue((self.control/'failure.json').exists())
        with self.assertRaises(CaptureError):self.run_transfer()

    def test_reconciliation_is_read_only_and_detects_tampered_receipts_and_restored_bytes(self):
        self.run_transfer();before=self.snapshot(self.control)
        with patch.object(t.LocalMirror,'upload',side_effect=AssertionError('inspection transported')):
            self.assertTrue(t.inspect(self.control)['finalization_complete'])
        self.assertEqual(self.snapshot(self.control),before)
        for name in ('intent.json','completion.json','upload-observation.json','downloaded.zip',
                     'restored/admission.json','restored/replayed-evidence/capture.db'):
            path=self.control/name;raw=path.read_bytes();path.write_bytes(raw+b' ')
            self.assertFalse(t.inspect(self.control)['finalization_complete']);path.write_bytes(raw)
        self.assertTrue(t.inspect(self.control)['finalization_complete'])

    def test_missing_transfer_control_inspection_creates_nothing(self):
        missing=self.local/'missing';self.assertFalse(t.inspect(missing)['finalization_complete']);self.assertFalse(missing.exists())

    def test_quarantine_survives_successful_simulated_transfer(self):
        self.raw=self.packages['shutdown-interruption'];self.package.write_bytes(self.raw)
        result=self.run_transfer();self.assertTrue(result['reconciliation_required'])
        self.assertEqual(result['classification'],'quarantined-incomplete-evidence')
        self.assertFalse(result['automatic_resume_allowed']);self.assertFalse(result['full_gate_accepted'])

    def test_mirror_never_overwrites_existing_object(self):
        exclusive_file(self.mirror/'object.zip',b'old')
        with self.assertRaises(FileExistsError):self.transport.upload('object.zip',self.raw)
        self.assertEqual((self.mirror/'object.zip').read_bytes(),b'old')


if __name__=='__main__':unittest.main()
