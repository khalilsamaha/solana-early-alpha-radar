import importlib.util, json, sqlite3, tempfile, unittest, time
from pathlib import Path
from unittest.mock import patch
import quote_backup as backup
from launch_audit import audit,FIELDS

class OperationsTests(unittest.TestCase):
    def ledger(self,path):
        with sqlite3.connect(path) as db:
            db.executescript('CREATE TABLE meta(k TEXT PRIMARY KEY,v TEXT);CREATE TABLE signals(seq INTEGER PRIMARY KEY,at INTEGER,cohort TEXT,mint TEXT,decision TEXT,detected INTEGER,data TEXT);CREATE TABLE probes(seq INTEGER PRIMARY KEY,at INTEGER,mint TEXT,state TEXT,data TEXT);CREATE TABLE incidents(at INTEGER,kind TEXT,detail TEXT);')
            for k,v in {'sourceIdentity':'dev:ino','cursor':{'alerts':42},'samplingRegistration':{'id':'frozen','at':1},'registeredAt':1}.items():db.execute('INSERT INTO meta VALUES(?,?)',(k,json.dumps(v)))
            db.execute("INSERT INTO signals VALUES(42,1,'baseline','mint','admitted',1,'{}')")
            db.execute("INSERT INTO probes VALUES(42,1,'mint','running','{}')")
        return path
    def test_live_wal_snapshot_restore_preserves_every_table_and_cursor_without_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=self.ledger(root/'source.sqlite')
            with sqlite3.connect(src) as writer:
                writer.execute('PRAGMA journal_mode=WAL');writer.execute("INSERT INTO incidents VALUES(2,'test','evidence')");writer.commit()
                expected=backup.logical_summary(src);result=backup.backup(src,root/'output')
                self.assertTrue(result['success']);self.assertFalse(result['cloudVerified'])
                archive=Path(result['archive']);manifest=json.loads(archive.with_name(archive.name+'.json').read_text())
                self.assertEqual(backup.verify_archive(archive,manifest),expected)
                self.assertEqual(backup.logical_summary(src),expected)
                self.assertEqual(archive.stat().st_mode&0o777,0o600)
                self.assertEqual(writer.execute('SELECT state FROM probes').fetchone()[0],'running')
    def test_corrupt_archive_and_modified_cursor_fail_verification(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);result=backup.backup(self.ledger(root/'source.sqlite'),root/'out');archive=Path(result['archive']);m=json.loads(archive.with_name(archive.name+'.json').read_text())
            m['ledger']['metadata']['cursor']['alerts']=100
            with self.assertRaisesRegex(ValueError,'differs'):backup.verify_archive(archive,m)
            archive.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'checksum'):backup.verify_archive(archive,m)
    def test_cloud_failure_is_not_success_and_local_copy_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(backup,'rclone',side_effect=RuntimeError('private-url')):
                with self.assertRaisesRegex(RuntimeError,'credentials'):backup.backup(self.ledger(root/'s.sqlite'),root/'out',True)
            status=json.loads((root/'out/last-run.json').read_text());self.assertFalse(status['success']);self.assertTrue(status['localVerified']);self.assertFalse(status['cloudVerified'])
            self.assertNotIn('private-url',json.dumps(status));self.assertEqual(len(list((root/'out').glob('*.sqlite.gz'))),1)
    def test_cloud_archive_and_manifest_round_trip_and_no_remote_delete(self):
        with tempfile.TemporaryDirectory() as d:
            import shutil
            root=Path(d);remote={};calls=[]
            def transfer(args):
                calls.append(args);op,src,dst=args;self.assertEqual(op,'copyto')
                if dst.startswith(backup.REMOTE):remote[dst]=Path(src).read_bytes()
                else:Path(dst).write_bytes(remote[src])
            with patch.object(backup,'rclone',side_effect=transfer):r=backup.backup(self.ledger(root/'s.sqlite'),root/'out',True)
            self.assertTrue(r['cloudVerified']);self.assertEqual(len(calls),4)
    def test_invalid_ledger_fails_and_cannot_publish_archive(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'bad.sqlite';sqlite3.connect(src).close()
            with self.assertRaises(RuntimeError):backup.backup(src,root/'out')
            self.assertFalse(json.loads((root/'out/last-run.json').read_text())['success']);self.assertEqual(list((root/'out').glob('*.gz')),[])
    def test_audit_unknown_zero_and_reported_creator_roles(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'radar.sqlite';now=int(time.time()*1000)
            with sqlite3.connect(file) as db:
                db.executescript('CREATE TABLE kv(key TEXT PRIMARY KEY,data TEXT);CREATE TABLE launch_registry(mint TEXT PRIMARY KEY,received_at INTEGER,data TEXT);')
                for n in range(2):
                    e={'version':'launch-registry-1','receivedAt':now,'availableAt':now,'fields':{'creatorReported':'actor','traderReported':'other','initialBuyReported':'0'}}
                    db.execute('INSERT INTO launch_registry VALUES(?,?,?)',(str(n),now,json.dumps(e)))
            result=audit(file);self.assertEqual(result['receivedCreationsInWindow'],2)
            self.assertEqual(result['availability']['initialBuyReported']['present'],2);self.assertEqual(result['availability']['slotReported']['unknown'],2)
            self.assertEqual(result['creatorRoleConflicts'],2);self.assertEqual(result['reportedCreatorsWithMultipleCreationsInWindow'],1)
    def test_audit_missing_registry_and_oversized_record_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'db';db=sqlite3.connect(f);db.execute('CREATE TABLE kv(key TEXT,data TEXT)');db.commit()
            with self.assertRaisesRegex(ValueError,'not installed'):audit(f)
            db.execute('CREATE TABLE launch_registry(mint TEXT,received_at INTEGER,data TEXT)');db.execute('INSERT INTO launch_registry VALUES(?,?,?)',('x',int(time.time()*1000),'x'*4097));db.commit();db.close()
            with self.assertRaisesRegex(ValueError,'cap reached'):audit(f)

if __name__=='__main__':unittest.main()
