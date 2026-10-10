import gzip
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import paper_model as m
import radar_research as r

T=1791128059483

def entry(points, **kw):
    return dict(id='M:1',at=T,pairAddress='POOL',cohort='baseline',path=[dict(at=T+t*1000,price=p,pairAddress='POOL') for t,p in points],**kw)

class PolicyTests(unittest.TestCase):
    def runmodel(self,e,policy=None,delay=0,cut=500,cost=0):
        return m.run_policy(e,policy or m.POLICIES[0],delay,T+cut*1000,cost)
    def test_time_limit_uses_first_observation_after_exit_delay(self):
        e=entry([(0,100),(15,105),(30,110),(45,115),(60,130),(75,120)])
        o=self.runmodel(e)
        self.assertEqual(o['simulatedExitAt'],T+75000)
        self.assertAlmostEqual(o['grossReturnPct'],20)
    def test_reaction_delay_changes_entry_price(self):
        e=entry([(0,100),(15,120),(30,110),(45,115),(60,130),(75,120),(90,132)])
        o=self.runmodel(e,delay=10000)
        self.assertEqual(o['simulatedEntryAt'],T+15000)
        self.assertAlmostEqual(o['grossReturnPct'],10)
    def test_stop_does_not_fill_at_threshold_or_trigger_price(self):
        e=entry([(0,100),(15,90),(30,80),(45,1)])
        o=self.runmodel(e,m.POLICIES[2])
        self.assertEqual(o['exitReason'],'stop-observed')
        self.assertEqual(o['simulatedExitPrice'],1)
        self.assertAlmostEqual(o['grossReturnPct'],-99)
    def test_target_can_end_in_loss_during_exit_delay(self):
        e=entry([(0,100),(15,130),(30,50)])
        o=self.runmodel(e,m.POLICIES[2])
        self.assertEqual(o['exitReason'],'target-observed')
        self.assertEqual(o['grossReturnPct'],-50)
    def test_gap_does_not_create_optimistic_fill(self):
        o=self.runmodel(entry([(0,100),(75,200)]))
        self.assertEqual(o['status'],'unresolved')
        self.assertEqual(o['reason'],'observation-gap-before-exit')
    def test_new_pool_cannot_supply_exit(self):
        e=entry([(0,100),(30,110),(60,120)])
        e['path'].append({'at':T+75000,'price':1000,'pairAddress':'OTHER'})
        self.assertEqual(self.runmodel(e)['status'],'unresolved')
    def test_future_data_never_used(self):
        e=entry([(0,100),(30,110),(60,120),(75,1000)])
        self.assertEqual(self.runmodel(e,cut=60)['status'],'pending')
    def test_conflicting_observations_invalid(self):
        e=entry([(0,100),(30,110),(30,120),(60,130),(75,140)])
        self.assertEqual(self.runmodel(e)['reason'],'conflicting-observations')
    def test_exact_duplicates_harmless(self):
        e=entry([(0,100),(30,110),(30,110),(60,120),(75,130)])
        self.assertEqual(self.runmodel(e)['status'],'observed-model')
    def test_costs_apply_both_sides(self):
        e=entry([(0,100),(30,100),(60,100),(75,100)])
        o=self.runmodel(e,cost=100)
        self.assertAlmostEqual(o['netReturnPct'],(.99/1.01-1)*100)
    def test_incomplete_path_excluded(self):
        self.assertEqual(self.runmodel(entry([(0,100)],pathTruncated=True))['status'],'invalid')
    def test_no_delayed_entry_quote(self):
        self.assertEqual(self.runmodel(entry([(0,100)]),delay=10000)['reason'],'no-timely-entry-observation')
    def test_pending_entry_not_imputed_loss(self):
        o=self.runmodel(entry([(0,100)]),delay=30000,cut=20)
        self.assertEqual(o['status'],'pending')
        self.assertIsNone(m.summary([o])['unresolvedAsTotalLossStressMeanPct'])
    def test_unresolved_stress_is_explicit(self):
        s=m.summary([{'status':'observed-model','netReturnPct':50,'reason':'ok'},{'status':'unresolved','reason':'missing'}])
        self.assertEqual(s['meanNetPct'],50)
        self.assertEqual(s['unresolvedAsTotalLossStressMeanPct'],-25)
    def test_all_entries_remain_in_each_policy_denominator(self):
        e=entry([(0,100)])
        out=m.evaluate([e],T+500000)
        self.assertEqual(len(out['groups']),27)
        self.assertTrue(all(g['entries']==1 for g in out['groups'].values()))
    def test_time_exit_priority_over_later_target(self):
        e=entry([(0,100),(30,100),(60,100),(90,100),(120,150),(135,140)])
        o=self.runmodel(e,m.POLICIES[2])
        self.assertEqual(o['exitReason'],'time-limit')
    def test_triggers_do_not_read_post_exit_conflicts(self):
        # Evidence after a completed exit cannot change that earlier decision.
        e=entry([(0,100),(30,100),(60,100),(75,100),(90,120),(90,130)])
        self.assertEqual(self.runmodel(e)['status'],'observed-model')

class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'db.sqlite'
        self.db=sqlite3.connect(self.path)
        self.db.executescript('CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT,at INTEGER,data TEXT);CREATE INDEX events_at ON events(kind,at);')
        for i in range(20):
            self.add('alerts',{'id':f'M{i}:{T}:1','at':T,'engineVersion':'0.2.9','candidate':{'mint':f'M{i}','pairAddress':f'P{i}','priceUsd':100,'symbol':'TEST','secret':'DO-NOT-EXPORT'},'secret':'DO-NOT-EXPORT'})
            for sec,price in [(15,105),(30,110),(45,115),(60,120),(75,125)]:
                self.add('snapshots',{'mint':f'M{i}','at':T+sec*1000,'observedAt':T+sec*1000,'priceUsd':price,'pairAddress':f'P{i}','secret':'DO-NOT-EXPORT'})
        self.db.commit()
    def tearDown(self):
        self.db.close();self.temp.cleanup()
    def add(self,kind,obj):
        self.db.execute('INSERT INTO events(kind,at,data) VALUES (?,?,?)',(kind,obj['at'],json.dumps(obj)))
    def capture(self,**kwargs):return r.capture(self.path,cutoff=T+600000,**kwargs)
    def test_all_twenty_entries_have_paths_not_selected_cases(self):
        out=self.capture()
        self.assertEqual(len(out['entries']),20)
        self.assertTrue(all(len(e['path'])==6 for e in out['entries']))
        self.assertNotIn('DO-NOT-EXPORT',json.dumps(out))
    def test_later_alert_excluded(self):
        self.add('alerts',{'id':f'M0:{T}:2','at':T+1000,'engineVersion':'0.2.9','candidate':{'mint':'M0','pairAddress':'P0','priceUsd':101}})
        self.db.commit();out=self.capture()
        self.assertEqual(len(out['entries']),20)
        self.assertEqual(out['excludedLaterAlerts'],1)
    def test_old_engine_excluded(self):
        self.add('alerts',{'id':f'OLD:{T}:1','at':T,'engineVersion':'0.2.8'})
        self.db.commit();self.assertEqual(len(self.capture()['entries']),20)
    def test_future_snapshot_excluded(self):
        self.add('snapshots',{'at':T+700000,'observedAt':T+700000,'mint':'M0','priceUsd':10000,'pairAddress':'P0'})
        self.db.commit();self.assertEqual(len(self.capture()['entries'][0]['path']),6)
    def test_budget_and_cap_fail_closed(self):
        with self.assertRaises((TimeoutError,sqlite3.OperationalError)):self.capture(budget=-1)
        with self.assertRaises(RuntimeError):self.capture(scan_cap=3)
    def test_backup_unchanged(self):
        before=self.path.read_bytes();self.capture()
        self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse(Path(str(self.path)+'-wal').exists())
    def test_live_wal_read_does_not_alter_content(self):
        self.db.execute('PRAGMA journal_mode=WAL')
        before=self.db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
        self.capture(live=True)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM events').fetchone()[0],before)
    def test_snapshots_before_first_eligible_entry_do_not_consume_cap(self):
        for i in range(250):
            self.add('snapshots',{'at':T-60000-i,'observedAt':T-60000-i,'mint':'OLD','priceUsd':1,'pairAddress':'OLD'})
        self.db.commit()
        out=self.capture(scan_cap=110)
        self.assertEqual(out['rowsRead']['snapshots'],100)
        self.assertEqual(out['pathQueryWindow']['start'],r.iso(T))
        self.assertEqual(len(out['entries']),20)

    def test_summary_exposes_mean_and_loss_tail(self):
        out=self.capture();out['evaluation']=m.evaluate(out['entries'],out['cutoffMs'])
        message=r.summary_text(out)
        self.assertIn('mean=',message)
        self.assertIn('losses>=50%=',message)

    def test_live_transaction_does_not_mix_concurrent_writer_changes(self):
        self.db.execute('PRAGMA journal_mode=WAL')
        original=json.loads
        changed=[False]
        def inject(raw,*a,**kw):
            row=original(raw,*a,**kw)
            if not changed[0] and row.get('engineVersion')=='0.2.9':
                changed[0]=True
                self.db.execute("UPDATE events SET data=json_set(data,'$.priceUsd',999999) WHERE kind='snapshots'")
                self.db.commit()
            return row
        with patch.object(r.json,'loads',inject):
            result=self.capture(live=True)
        self.assertTrue(changed[0])
        self.assertEqual(result['entries'][0]['path'][1]['price'],105)

    def test_readonly_connection_enforced(self):
        original=sqlite3.connect
        conns=[]
        def tracked(*a,**kw):
            conn=original(*a,**kw);conns.append(a[0]);return conn
        with patch.object(r.sqlite3,'connect',tracked):self.capture(live=True)
        self.assertIn('mode=ro',conns[0]);self.assertNotIn('immutable',conns[0])
    def test_early_cohort_is_included_without_double_baseline(self):
        for cohort in ['baseline','early-activity']:
            self.add('research-entries',{'id':'R:'+cohort,'mint':'R','at':T,'version':'research-0.2.9','cohort':cohort,'priceUsd':1,'pairAddress':'PR'})
        self.db.commit();out=self.capture()
        self.assertEqual(len(out['entries']),21)
        self.assertEqual(out['entries'][-1]['cohort'],'early-activity')
    def test_research_samples_can_fill_archive_sparsity(self):
        self.add('research-outcomes',{'entryId':'R','mint':'M0','entryAt':T,'at':T+60000,'cohort':'baseline',
            'evidenceHistory':{'poolAddress':'P0','samples':[{'at':T+10000,'price':102}]}})
        self.db.commit();self.assertEqual(len(self.capture()['entries'][0]['path']),7)
    def test_publish_roundtrip_and_no_nan(self):
        report=self.capture();report['evaluation']=m.evaluate(report['entries'],report['cutoffMs'])
        p=Path(self.temp.name)/'out.json.gz';r.publish(report,p)
        self.assertEqual(json.loads(gzip.decompress(p.read_bytes()))['format'],r.VERSION)
        self.assertEqual(p.stat().st_mode&0o777,0o600)
    def test_retention_leaves_other_files_alone(self):
        root=Path(self.temp.name)
        for i in range(5):(root/f'research-{i}.json.gz').write_bytes(b'x')
        other=root/'unrelated.json.gz';other.write_bytes(b'y')
        r.prune_reports(root,keep=2)
        self.assertEqual(len(list(root.glob('research-*'))),2);self.assertTrue(other.exists())
    def test_malformed_entry_not_silently_excluded(self):
        self.add('alerts',{'id':f'BAD:{T}:1','at':T,'engineVersion':'0.2.9','candidate':{'mint':'BAD'}})
        self.db.commit()
        with self.assertRaises(ValueError):self.capture()


class InstallerTests(unittest.TestCase):
    def test_install_idempotence_refusal_and_uninstall_preserves_scanner(self):
        import install as inst
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);bundle=root/'bundle';bundle.mkdir()
            for name in ['paper_model.py','radar_research.py','test_research.py','install.py','research_analysis.py']:
                (bundle/name).write_bytes((Path(__file__).parent/name).read_bytes())
            (bundle/'manifest.json').write_text(json.dumps({'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.iterdir()}}))
            project=root/'project';project.mkdir();(project/'package.json').write_text('{"version":"0.2.9"}')
            (project/'.env').write_text('UNTOUCHED-CANARY')
            attrs={'BUNDLE':bundle,'DEST':root/'lib','LAUNCHER':root/'command','CONFIG':root/'config.json',
                   'REPORTS':root/'reports','SERVICE':root/'research.service','TIMER':root/'research.timer'}
            with patch.multiple(inst,**attrs),patch.object(inst.subprocess,'run') as calls,patch('builtins.print'):
                # Simulate the exact previous installation so upgrade permissions are exercised.
                for target,content in inst.generated(project).items():
                    target.write_text(content.replace('solana-radar-research-tools-1.1.0','solana-radar-research-tools-1.0.1').replace('/solana-radar-research/1.1.0','/solana-radar-research/1.0.1'))
                inst.install(project,timer=True)
                self.assertTrue(attrs['TIMER'].exists())
                self.assertEqual((project/'.env').read_text(),'UNTOUCHED-CANARY')
                reg_before=(attrs['REPORTS']/'shadow-registration-v1.json').read_bytes()
                inst.install(project,timer=True)
                self.assertEqual(reg_before,(attrs['REPORTS']/'shadow-registration-v1.json').read_bytes())
                original=attrs['LAUNCHER'].read_bytes();attrs['LAUNCHER'].write_text('edited')
                with self.assertRaises(RuntimeError):inst.install(project)
                attrs['LAUNCHER'].write_bytes(original)
                (attrs['REPORTS']/'keep.json.gz').write_bytes(b'keep')
                inst.uninstall()
                self.assertFalse(attrs['TIMER'].exists())
                self.assertTrue((attrs['REPORTS']/'keep.json.gz').exists())
                self.assertEqual((project/'.env').read_text(),'UNTOUCHED-CANARY')
                commands=[c.args[0] for c in calls.call_args_list]
                self.assertFalse(any('docker' in cmd for cmd in commands))

if __name__=='__main__':unittest.main(verbosity=2)
