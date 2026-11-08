from contextlib import closing
import unittest,tempfile,sqlite3,json,time
from pathlib import Path
from manage import read_report
class ReportTests(unittest.TestCase):
    def test_status_export_preserves_failed_and_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'observer.sqlite';now=int(time.time()*1000)
            with closing(sqlite3.connect(p)) as db, db:
                db.executescript('CREATE TABLE meta(k TEXT,v TEXT);CREATE TABLE signals(seq INTEGER,cohort TEXT,decision TEXT,detected INTEGER,data TEXT);CREATE TABLE probes(seq INTEGER,at INTEGER,state TEXT,data TEXT);CREATE TABLE incidents(at INTEGER,kind TEXT,detail TEXT);')
                db.execute('INSERT INTO meta VALUES(?,?)',('lastPollAt',json.dumps(now)))
                db.execute('INSERT INTO signals VALUES(?,?,?,?,?)',(1,'early-activity','observer-busy',now,'{"seq":1}'))
                db.execute('INSERT INTO probes VALUES(?,?,?,?)',(2,now,'buy-quote-failed','{"signal":{"seq":2}}'))
            r=read_report({'reports':d});self.assertEqual(r['signals'][0]['decision'],'observer-busy');self.assertEqual(r['probes'][0]['state'],'buy-quote-failed')
            self.assertNotIn('signals',read_report({'reports':d},status=True))
            with closing(sqlite3.connect(p)) as db, db:self.assertEqual(db.execute('SELECT count(*) FROM signals').fetchone()[0],1)
    def test_capacity_includes_legacy_admissions_and_reports_release_time(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'observer.sqlite';now=1800000000000
            with closing(sqlite3.connect(p)) as db, db:
                db.executescript('CREATE TABLE meta(k TEXT,v TEXT);CREATE TABLE signals(seq INTEGER,cohort TEXT,decision TEXT,detected INTEGER,data TEXT);CREATE TABLE probes(seq INTEGER,at INTEGER,state TEXT,data TEXT);CREATE TABLE incidents(at INTEGER,kind TEXT,detail TEXT);')
                db.execute('INSERT INTO meta VALUES(?,?)',('samplingRegistration',json.dumps({'id':'cohort-budgets-v2'})))
                for seq,mins in enumerate([1,10,20,30]):
                    at=now-mins*60000
                    db.execute('INSERT INTO signals VALUES(?,?,?,?,?)',(seq,'early-activity','admitted',at,'{}'))
                    db.execute('INSERT INTO probes VALUES(?,?,?,?)',(seq,at,'complete','{}'))
            with patch('manage.time.time',return_value=now/1000):r=read_report({'reports':d},status=True)
            self.assertEqual(r['cohortCapacity']['early-activity']['hourUsed'],4)
            self.assertEqual(r['cohortCapacity']['early-activity']['cohortBudgetOpensAt'],now+40*60000)
            self.assertEqual(r['cohortCapacity']['baseline']['cohortBudgetOpensAt'],now)
    def test_three_cohort_capacity_uses_new_limits_and_preserves_legacy_counts(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            now=1800000000000
            with closing(sqlite3.connect(Path(d)/'observer.sqlite')) as db, db:
                db.executescript('CREATE TABLE meta(k TEXT,v TEXT);CREATE TABLE signals(seq INTEGER,cohort TEXT,decision TEXT,detected INTEGER,data TEXT);CREATE TABLE probes(seq INTEGER,at INTEGER,state TEXT,data TEXT);CREATE TABLE incidents(at INTEGER,kind TEXT,detail TEXT);')
                policy={'id':'three-cohort-budgets-v3','cohorts':['baseline','early-activity','fast30-shadow'],'perCohortHour':2,'perCohortDay':48,'minimumCohortSpacingMs':1800000}
                db.execute('INSERT INTO meta VALUES(?,?)',('samplingRegistration',json.dumps(policy)))
                for seq,mins in enumerate([1,10]):
                    at=now-mins*60000
                    db.execute('INSERT INTO signals VALUES(?,?,?,?,?)',(seq,'fast30-shadow','admitted',at,'{}'))
                    db.execute('INSERT INTO probes VALUES(?,?,?,?)',(seq,at,'complete','{}'))
            with patch('manage.time.time',return_value=now/1000):r=read_report({'reports':d},status=True)
            self.assertEqual(r['cohortCapacity']['fast30-shadow']['cohortBudgetOpensAt'],now+50*60000)
            self.assertEqual(len(r['cohortCapacity']),3)
    def test_missing_database_does_not_create_empty_file(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):read_report({'reports':d})
            self.assertFalse((Path(d)/'observer.sqlite').exists())
if __name__=='__main__':unittest.main()
