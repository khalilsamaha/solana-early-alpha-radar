"""Atomic collection persistence, protocol replay and coordinator refusal checks."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import admission_exit_collection_checks as c


class CollectedExitTests(unittest.TestCase):
    def test_portable_cli_cases_and_private_exclusive_output(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'result.json.gz'
            args=[sys.executable,'-E','-s',str(Path(__file__).with_name('admission_exit_collection_cli.py')),'--output',str(path)]
            run=subprocess.run(args,capture_output=True,text=True,timeout=180)
            self.assertEqual(run.returncode,0,run.stderr)
            r=json.loads(gzip.decompress(path.read_bytes()))
            self.assertEqual(r['casesPassed'],21);self.assertEqual(len(r['cases']),21)
            self.assertTrue(r['atomicCollectionAndPreparation']);self.assertEqual(r['networkRequests'],0)
            self.assertEqual(path.stat().st_mode&0o777,0o600);old=path.read_bytes()
            self.assertNotEqual(subprocess.run(args,capture_output=True,timeout=10).returncode,0)
            self.assertEqual(path.read_bytes(),old)

    def test_coordinator_collects_once_then_replays_without_rpc(self):
        with c.case() as case:
            c.collect(case);c.apply(case);first,e,b=c.fixture.setup(case);clock=c.fixture.Clock()
            rpc=c.fixture.Opener(first,e)
            snapshot=case.e['costInputs']['reservations']
            with patch.object(c.m.exit,'BASELINE',b),patch.object(c.m.exit.view,'read_locked',return_value=snapshot):
                result=c.m.collect_and_prepare(case.home,case.wallet,case.pool,opener=rpc,clock=clock,monotonic=lambda:0)
                self.assertTrue(result['collectionRecorded']);self.assertTrue(result['createdThisRun'])
                self.assertEqual(result['collectionRequestsThisRun'],20)
                old=case.path.read_bytes();clock.at+=30000
                later=c.m.collect_and_prepare(case.home,case.wallet,case.pool,opener=rpc,clock=clock,monotonic=lambda:0)
                self.assertEqual(later['collectionRequestsThisRun'],0);self.assertEqual(len(rpc.calls),20)
                self.assertEqual(later['state'],'exit-preparation-expired');self.assertEqual(case.path.read_bytes(),old)

    def test_stop_between_collection_and_write_cannot_commit(self):
        with c.case() as case:
            c.collect(case);c.apply(case);first,e,b=c.fixture.setup(case);clock=c.fixture.Clock()
            rpc=c.fixture.Opener(first,e);original=c.m.exit.prepare
            def stopped(*args,**kwargs):
                (case.home/'STOP').touch(mode=0o600)
                return original(*args,**kwargs)
            old=case.path.read_bytes()
            with patch.object(c.m.exit,'BASELINE',b),patch.object(c.m.exit.view,'read_locked',return_value=case.e['costInputs']['reservations']),patch.object(c.m.exit,'prepare',side_effect=stopped):
                with self.assertRaisesRegex(ValueError,'stop-marker-present'):
                    c.m.collect_and_prepare(case.home,case.wallet,case.pool,opener=rpc,clock=clock,monotonic=lambda:0)
            self.assertEqual(len(rpc.calls),20);self.assertEqual(case.path.read_bytes(),old)

    def test_recorded_proof_semantics_survive_recomputed_outer_hash(self):
        with c.case() as case:
            c.collect(case);c.apply(case);e,p,b=c.collected(case);c.prepare(case,e,p,b)
            db=c.sqlite3.connect(case.path)
            try:
                row=json.loads(db.execute('SELECT value FROM admission_exit_preparation').fetchone()[0])
                row['collection']['requestTrace'][18]['parametersSha256']='0'*64
                c.rehash(row['collection'],row['evidence'])
                row['binding']['collectionSha256']=c.m.digest(row['collection'])
                db.execute('UPDATE admission_exit_preparation SET value=?,hash=?',(c.m.exit.encoded(row),c.m.digest(row)));db.commit()
            finally:db.close()
            before=case.path.read_bytes()
            with self.assertRaisesRegex(ValueError,'exit-collection-request-binding'):c.status(case,b)
            self.assertEqual(case.path.read_bytes(),before)

    def test_changed_admission_between_collection_and_persistence_is_rejected(self):
        with c.case() as case:
            c.collect(case);c.apply(case);e,p,b=c.collected(case)
            book=case.book()
            try:book.change(lambda state,now:dict(state,reviewMarker='changed'),enforce_deadline=False)
            finally:book.close()
            old=case.path.read_bytes()
            with self.assertRaisesRegex(ValueError,'exit-collection-current-admission-changed'):
                c.prepare(case,e,p,b)
            self.assertEqual(case.path.read_bytes(),old)

    def test_request_metadata_is_not_a_decorative_success_claim(self):
        with c.case() as case:
            c.collect(case);c.apply(case);e,p,b=c.collected(case)
            p['packetBuild']['requests'][2]['state']='network-error';c.rehash(p,e)
            old=case.path.read_bytes()
            with self.assertRaisesRegex(ValueError,'exit-collection-request-metadata'):c.prepare(case,e,p,b)
            self.assertEqual(case.path.read_bytes(),old)

    def test_schema_and_database_size_caps_fail_before_commit(self):
        with c.case() as case:
            c.collect(case);c.apply(case);e,p,b=c.collected(case);old=case.path.read_bytes()
            with patch.object(c.m,'MAX_COLLECTION',100):
                with self.assertRaisesRegex(ValueError,'exit-collection-cap'):c.prepare(case,e,p,b)
            original=c.m.exit.write_record
            def oversized(book,record):
                original(book,record)
                book.db.execute('CREATE TABLE size_probe(value BLOB)')
                book.db.execute('INSERT INTO size_probe VALUES(zeroblob(?))',(65*1024*1024,))
            with patch.object(c.m.exit,'write_record',side_effect=oversized):
                with self.assertRaisesRegex(ValueError,'exit-ledger-size-cap'):c.prepare(case,e,p,b)
            self.assertEqual(case.path.read_bytes(),old)


if __name__=='__main__':unittest.main()
