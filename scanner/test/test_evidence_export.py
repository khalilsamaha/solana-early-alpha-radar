import importlib.util
import gzip
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

spec = importlib.util.spec_from_file_location('audit', Path(__file__).resolve().parents[1]/'scripts'/'evidence-check.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
T = 1791030000000

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT,at INTEGER,data TEXT); CREATE INDEX events_at ON events(kind,at); CREATE TABLE outbox(id TEXT PRIMARY KEY,status TEXT,at INTEGER,delivered_at INTEGER,attempts INTEGER,payload TEXT);')
        self.add('alerts', {'id': f'MINT:{T}:1', 'at': T, 'engineVersion': '0.2.9', 'candidate': {'mint':'MINT', 'priceUsd':10, 'pairAddress':'POOL', 'secret':'PRIVATE'}})
        self.add('outcomes', {'mint':'MINT','at':T+3600000,'alertAt':T,'horizon':'60m','status':'observed','coverage':'sampled','multiple':.05,'priceUsd':.5})
        self.add('snapshots', {'mint':'MINT','at':T,'priceUsd':10,'pairAddress':'POOL'})
        self.add('snapshots', {'mint':'OTHER','at':T+100,'priceUsd':99,'pairAddress':'OTHERPOOL'})
        self.db.execute('INSERT INTO outbox VALUES (?,?,?,?,?,?)',(f'MINT:{T}:1','sent',T,T+700,1,'PRIVATE'))
    def tearDown(self):
        self.db.close()
    def add(self, kind, row):
        self.db.execute('INSERT INTO events(kind,at,data) VALUES (?,?,?)',(kind,row['at'],json.dumps(row)))
    def report(self, **kw):
        return audit.analyze(self.db,T+7200000,**kw)
    def test_exact_mint_delivery_and_no_payload(self):
        r=self.report()
        self.assertEqual(r['baselineEntries'][0]['notification']['deliveryDelayMs'],700)
        self.assertEqual([s['mint'] for s in r['cases'][0]['snapshots']],['MINT'])
        self.assertNotIn('PRIVATE',json.dumps(r))
        self.assertEqual(r['baselineReturnArithmeticMismatches'],[])
    def test_later_alert_does_not_create_new_entry(self):
        self.add('alerts',{'id':f'OLD:{T-10000}:2','at':T+200,'engineVersion':'0.2.9','candidate':{'mint':'OLD','priceUsd':15}})
        self.assertEqual(self.report()['cohort']['baselineEntries'],1)
        self.assertEqual(self.report()['cohort']['excludedLaterOrUnrecognizedAlerts'],1)
    def test_old_version_excluded(self):
        self.add('alerts',{'id':f'OLD:{T}:1','at':T,'engineVersion':'0.2.7','candidate':{'mint':'OLD'}})
        self.assertEqual(self.report()['cohort']['baselineEntries'],1)
    def test_arithmetic_inconsistency_is_exposed(self):
        self.add('outcomes',{'mint':'MINT','at':T+900000,'alertAt':T,'horizon':'15m','status':'observed','coverage':'sampled','multiple':.02,'priceUsd':10})
        self.assertEqual(len(self.report()['baselineReturnArithmeticMismatches']),1)
    def test_gap_excluded_from_median(self):
        r=audit.summary([{'status':'observed','coverage':'gapped','multiple':200}, {'status':'observed','coverage':'sampled','multiple':.1}], 'multiple')
        self.assertEqual(r['median'],.1)
        self.assertEqual(r['gapped'],1)
    def test_caps_are_explicit(self):
        r=self.report(scan_limit=1)
        self.assertTrue(r['queryBudgets']['snapshots']['truncated'])
        self.assertFalse(r['completeWithinDeclaredWindow'])
    def test_alternate_pool_evidence_and_transition_preserved(self):
        self.add('research-entries',{'id':'R','mint':'ALT','at':T,'version':'research-0.2.9','cohort':'early-activity','priceUsd':2})
        self.add('research-outcomes',{'entryId':'R','mint':'ALT','at':T+300000,'horizon':'5m','status':'missing','reasonCode':'different-pool','tokenFollowup':{'status':'observed','basis':'alternate-pool','priceUsd':3,'returnPct':50,'migrationVerified':False,'evidence':{'samples':2}}})
        self.add('research-events',{'mint':'ALT','at':T+10000,'event':'pool changed','poolChange':{'at':T+10000,'from':'OLD','to':'NEW','migrationVerified':False}})
        r=self.report()
        f=r['researchOutcomes'][0]['tokenFollowup']
        self.assertEqual(f['basis'],'alternate-pool')
        self.assertFalse(f['migrationVerified'])
        case=next(c for c in r['cases'] if c['mint']=='ALT')
        self.assertEqual(case['researchEvents'][0]['poolChange']['to'],'NEW')
    def test_cutoff_excludes_later_data(self):
        self.add('outcomes',{'mint':'MINT','alertAt':T,'at':T+9000000,'horizon':'later'})
        self.assertEqual(len(self.report()['baselineOutcomes']),1)
    def test_readonly_database_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'snapshot.sqlite'
            target=sqlite3.connect(p)
            self.db.commit()
            self.db.backup(target)
            target.close()
            before=p.read_bytes()
            with sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1',uri=True) as ro:
                audit.analyze(ro,T+7200000)
                with self.assertRaises(sqlite3.OperationalError):
                    ro.execute('DELETE FROM events')
            self.assertEqual(p.read_bytes(),before)
            self.assertFalse(Path(str(p)+'-wal').exists())
    def test_new_qualification_and_history_fields_are_sanitized(self):
        raw={'at':T,'qualification':{'version':'qualification-1','state':'deteriorating','disposition':'defer','metrics':{'drawdownPct':-82},'secret':'PRIVATE'},
             'evidence':{'version':'event-evidence-1','poolAddress':'POOL','samples':[{'at':T,'price':1,'secret':'PRIVATE'}]*40,'inputs':{'priceUsd':1,'secret':'PRIVATE'}}}
        cleaned=audit.clean('alerts',raw)
        self.assertEqual(cleaned['qualification']['state'],'deteriorating')
        self.assertEqual(len(cleaned['evidence']['samples']),24)
        self.assertNotIn('PRIVATE',json.dumps(cleaned))

    def test_completed_backup_to_compressed_report(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p=root/'auto-test.sqlite'
            target=sqlite3.connect(p)
            self.db.commit()
            self.db.backup(target)
            target.close()
            (root/'last-run.json').write_text(json.dumps({'success':True,'state':'complete','backup':str(p),
                'bytes':p.stat().st_size,'snapshot_at':audit.iso(T+7200000)}))
            out=root/'report.json.gz'
            with patch.object(audit,'ROOT',root), patch.object(audit.sys,'argv',['audit','--output',str(out)]):
                audit.main()
            with gzip.open(out,'rt') as f:
                report=json.load(f)
            self.assertEqual(report['backup']['filename'],'auto-test.sqlite')
            self.assertEqual(report['cohort']['baselineEntries'],1)

if __name__=='__main__': unittest.main()
