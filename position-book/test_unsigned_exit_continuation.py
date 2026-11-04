from contextlib import contextmanager, nullcontext
from copy import deepcopy
import gzip,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import unsigned_exit_continuation as m
import unsigned_exit_continuation_checks as c
import unsigned_exit_continuation_cli as cli


class ContinuationTests(unittest.TestCase):
    def test_portable_contract(self):
        r=c.run();self.assertEqual(r['state'],'offline-checks-passed')
        self.assertEqual(r['casesPassed'],25)

    def test_independent_contract(self):
        r=c.independent_contract();self.assertEqual(r['casesPassed'],14)
        self.assertFalse(r['privateKeyAccessed']);self.assertEqual(r['signaturesCreated'],0)

    def test_offline_command_scope_and_exclusive_private_report(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz'
            argv=['check','--output',str(out)]
            with patch.object(sys,'argv',argv),patch.object(cli,'run',return_value=dict(state='offline-checks-passed',casesPassed=25)),patch.object(cli,'independent_contract',return_value=dict(cases={'synthetic':'passed'},casesPassed=14)):
                cli.main()
                self.assertEqual(out.stat().st_mode&0o777,0o600)
                raw=out.read_bytes();self.assertTrue(json.loads(gzip.decompress(raw))['disposableFixtureSigning'])
                with self.assertRaises(ValueError):cli.main()
                self.assertEqual(raw,out.read_bytes())
            out.unlink()
            for flags in (['--action','execute'],['--directory',d],['--wallet','w'],['--allow-devnet-submit'],['--allow-unsigned-continuation'],['--input','report.gz']):
                r=subprocess.run([sys.executable,'-E','-s',cli.__file__,'--output',str(out)]+flags,capture_output=True)
                self.assertNotEqual(r.returncode,0);self.assertFalse(out.exists())

    def test_capture_modes_cannot_cross(self):
        import admission_exit_capture as capture
        with patch.object(m.view.cycles.c,'source_lock',side_effect=AssertionError('source accessed')):
            for options in ({'_preserved_expected':('a'*64,'b'*64)}, {'_replacement_expected':'a'*64}, {'_evidence_sink':None}):
                with self.assertRaisesRegex(ValueError,'exit-capture-mode-conflict'):
                    capture.collect('/missing','w','p',**dict({'_continuation_expected':('a'*64,'b'*64),'_evidence_sink':lambda x:None},**options))

    def test_changed_source_or_identity_after_capture_refuses_without_write(self):
        with c.case() as f:
            e,p=c.private_capture(f);before=f.path.read_bytes()
            for mode in ('identity','stop','source','provenance','record-cap'):
                old=f.current
                try:
                    if mode=='identity':f.current='a'*64
                    if mode=='stop':(f.home/'STOP').touch(mode=0o600)
                    proof=deepcopy(p)
                    if mode=='provenance':proof['provenance']['identity']['admissionStateSha256']='f'*64
                    with patch.object(m.view,'read_locked',return_value={'phase':'wrong'}) if mode=='source' else nullcontext():
                        with patch.object(m,'MAX_RECORD',100) if mode=='record-cap' else nullcontext():
                            with self.assertRaises((ValueError,KeyError)):c.prepare(f,e,proof)
                    self.assertEqual(f.path.read_bytes(),before)
                finally:
                    f.current=old
                    if mode=='stop':(f.home/'STOP').unlink()

    def test_snapshot_cleanup_error_never_persists_collected_items(self):
        import sqlite3,admission_recovery
        original=admission_recovery.admission_read_lock
        @contextmanager
        def close_failure(path):
            with original(path):yield
            raise sqlite3.OperationalError('PRIVATE')
        with c.case() as f:
            before=f.path.read_bytes()
            with patch.object(admission_recovery,'admission_read_lock',close_failure):r=c.collect(f)
            self.assertEqual(r['state'],'unavailable');self.assertIsNone(r['binding']);self.assertIsNone(r['provenance'])
            self.assertEqual(before,f.path.read_bytes());self.assertNotIn('PRIVATE',json.dumps(r))

    def test_relationship_rejects_reused_original_hash_and_changed_constraints(self):
        with c.case() as f:
            e,p=c.private_capture(f);b=f.book()
            try:
                old=m.preparation.original_saved(b,f.clock());previous=m.replacement.replay(b,old,f.clock())
                now=f.clock();binding=m.preparation.review(b,e,now)
                from admission_exit_collection import review
                binding=review(b,e,p,now,binding)
                current=dict(format=m.preparation.COLLECTED_FORMAT,recordedAtMs=now,evidence=e,collection=p,binding=binding)
                m.relationship(old,previous,current)
                for key,value in [('quantityAtomic','1'),('feeCommitmentRemainingLamports','1'),('feeCapLamports','10001'),('protectedInventoryAtomic','0'),('attemptsConsumed',1),('attemptNumber',2)]:
                    bad=deepcopy(current);bad['binding'][key]=value
                    with self.subTest(key=key),self.assertRaises(ValueError):m.relationship(old,previous,bad)
                bad=deepcopy(current);bad['evidence']['packet']['policy']['blockhash']=old['evidence']['packet']['policy']['blockhash']
                with self.assertRaises(ValueError):m.relationship(old,previous,bad)
            finally:b.close()


if __name__=='__main__':unittest.main()
