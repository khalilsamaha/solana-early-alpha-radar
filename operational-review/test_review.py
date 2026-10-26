import copy
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import operational as review
import privileged

NOW=1793000000000


def baseline():
    comparison={'expectedFiles':1,'matched':1,'unavailable':[],'mismatched':[]}
    local={'scannerHostFiles':comparison,'scannerContainer':{'files':comparison,'container':{'status':'running','health':'healthy','restartCount':0}},
      'observerInstallation':{'files':comparison,'expectedVersion':'0.9.0','configuredVersions':['0.9.0']},
      'observer':{'state':'read','version':'quote-observer-0.9.0','lastPollAgeSeconds':2,'halted':False},
      'services':{k:{'ActiveState':'active'} for k in privileged.UNITS},'disk':{'usedPct':30},
      'backups':{'jobs':{k:{'evidence':{'status':'read','success':True,'localVerified':True,'cloudVerified':True,'cloud_verified':True,
        'finishedAt':review.datetime.fromtimestamp((NOW-60000)/1000,review.timezone.utc).isoformat()}} for k in ('scanner-local','scanner-cloud','quote-ledger')}}}
    health={'readiness':{'state':'read','httpStatus':200,'ready':True},'health':{'state':'read','lastMarketAgeSeconds':1,'lastLoopAgeSeconds':1}}
    study={'state':'registration-verified','preservation':{'state':'indexes-checked','captures':1,'preservationLagSeconds':100}}
    return local,health,study


def codes(args): return {x['code'] for x in review.findings(*args,NOW)}


class OperationalTests(unittest.TestCase):
    def test_good_evidence_has_no_findings(self): self.assertEqual(codes(baseline()),set())
    def test_running_process_does_not_mask_stale_poll(self):
        a=baseline();a[0]['observer']['lastPollAgeSeconds']=61
        self.assertIn('observer-poll-stale',codes(a))
    def test_old_backup_success_is_stale(self):
        a=baseline();a[0]['backups']['jobs']['scanner-local']['evidence']['finishedAt']='2026-01-01T00:00:00Z'
        self.assertIn('backup-status-stale',codes(a))
    def test_cloud_failure_preserves_local_success(self):
        a=baseline();a[0]['backups']['jobs']['scanner-local']['service']={'Result':'exit-code'}
        a[0]['backups']['jobs']['scanner-cloud']['evidence']['success']=False
        failures=[x for x in review.findings(*a,NOW) if x['code']=='backup-last-attempt-failed']
        self.assertEqual([x['scope'] for x in failures],['scanner-cloud'])
    def test_future_or_missing_clock_not_fresh(self):
        self.assertIsNone(review.age(NOW+1,NOW));self.assertIsNone(review.timestamp('2026-01-01'))
        a=baseline();a[0]['backups']['jobs']['scanner-local']['evidence']['finishedAt']='2099-01-01T00:00:00Z'
        self.assertIn('backup-finish-clock-unavailable-or-future',codes(a))
    def test_unavailable_never_passes_and_null_container_survives(self):
        a=({}, {}, {});self.assertGreater(len(review.findings(*a,NOW)),10)
        a=baseline();a[0]['scannerContainer']['container']=None
        self.assertIn('container-not-confirmed-running',codes(a))
    def test_halt_version_disk_and_heap_reported(self):
        a=baseline();a[0]['observer']['halted']=True;a[0]['observer']['version']='quote-observer-0.8.0'
        a[0]['disk']['usedPct']=96;a[1]['health']['memory']={'heapUsedBytes':85,'heapLimitBytes':100}
        self.assertTrue({'observer-halted','observer-live-version-not-confirmed','disk-usage-high','heap-usage-high'}<=codes(a))
    def test_pending_notifications_are_information_only(self):
        a=baseline();a[1]['health']['notifications']={'pending':2,'failed':0}
        self.assertEqual(review.findings(*a,NOW),[{'code':'notifications-pending','severity':'info'}])
    def test_index_overlap_merges_without_outcome_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'captures').mkdir()
            self.index(root,'one',1000,2000);self.index(root,'two',1900,3000)
            p=review.capture_indexes(root,'source',1500,NOW)
            self.assertEqual(p['requestedWindows'],[[1500,3000]])
            self.assertEqual(p['gapsBeforeLastPreservedEnd'],[])
            self.assertFalse(p['chunkContentsVerified'])
    def test_index_gap_missing_chunk_identity_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'captures').mkdir()
            self.index(root,'one',1000,2000);self.index(root,'two',2500,3000)
            self.assertEqual(review.capture_indexes(root,'source',1000,NOW)['gapsBeforeLastPreservedEnd'],[[2000,2500]])
            with self.assertRaises(ValueError):review.capture_indexes(root,'wrong',1000,NOW)
            p=root/'captures/capture-two/part-00.json.gz';p.unlink()
            with self.assertRaises(ValueError):review.capture_indexes(root,'source',1000,NOW)
            p.symlink_to(root/'captures/capture-one/part-00.json.gz')
            with self.assertRaises(ValueError):review.capture_indexes(root,'source',1000,NOW)
    def test_index_count_and_decompression_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'captures').mkdir()
            for i in range(9):self.index(root,str(i),1000,2000)
            with self.assertRaises(ValueError):review.capture_indexes(root,'source',1000,NOW)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'captures').mkdir();self.index(root,'one',1000,2000)
            p=root/'captures/capture-one/capture-index.json.gz';p.write_bytes(gzip.compress(b' '*65537))
            with self.assertRaises(ValueError):review.capture_indexes(root,'source',1000,NOW)
    def test_study_only_loads_sealed_registration(self):
        with patch.object(review.experiment,'load',return_value=({'secret':'not-exported'},{'installedAt':10,'testNotBeforeAt':20,'sourceIdentity':'private'})), \
             patch.object(review,'capture_indexes',return_value={'state':'indexes-checked'}), \
             patch.object(review.experiment,'review',side_effect=AssertionError('must not evaluate')):
            result=review.study(Path('/unused'),NOW)
            self.assertNotIn('private',json.dumps(result));self.assertNotIn('secret',json.dumps(result))
            self.assertFalse(result['modelEvaluated'])
    def test_sqlite_metadata_only_read_and_allowlisted_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);dbpath=root/'observer.sqlite'
            with sqlite3.connect(dbpath) as db:
                db.execute('CREATE TABLE meta(k TEXT PRIMARY KEY,v TEXT)')
                for k,v in {'lastPollAt':NOW-2000,'version':'quote-observer-0.9.0','halted':'arbitrary-private-error'}.items():db.execute('INSERT INTO meta VALUES(?,?)',(k,json.dumps(v)))
            config=root/'config.json';config.write_text(json.dumps({'reports':tmp,'private':'secret'}))
            before=hashlib.sha256(dbpath.read_bytes()).hexdigest()
            result=privileged.observer(config,NOW)
            self.assertEqual(result['lastPollAgeSeconds'],2);self.assertTrue(result['halted'])
            self.assertNotIn('private-error',json.dumps(result));self.assertNotIn(tmp,json.dumps(result))
            self.assertEqual(before,hashlib.sha256(dbpath.read_bytes()).hexdigest())
    def test_observer_missing_database_never_creates_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'config.json';p.write_text(json.dumps({'reports':tmp}))
            self.assertEqual(privileged.observer(p,NOW),{'state':'unavailable'})
            self.assertFalse((Path(tmp)/'observer.sqlite').exists())
    def test_atomic_output_refuses_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'public.json.gz';review.publish(p,{'ok':True})
            before=p.read_bytes()
            with self.assertRaises(FileExistsError):review.publish(p,{'changed':True})
            self.assertEqual(p.read_bytes(),before);self.assertEqual(p.stat().st_mode&0o777,0o600)
    def test_child_failure_is_sanitized(self):
        with patch.object(review.subprocess,'run',side_effect=OSError('secret')):
            self.assertEqual(review.command_json(['unused'],1),{'state':'unavailable'})

    @staticmethod
    def index(root,name,start,end):
        p=root/'captures'/('capture-'+name);p.mkdir()
        # Intentionally unreadable as a gzip report: review must never parse outcome bytes.
        (p/'part-00.json.gz').write_bytes(b'private outcome contents')
        data={'format':'quote-history-capture-1','complete':True,'sourceIdentity':'source','windowClock':'observer-detected-time',
              'requestedStartAt':start,'entryWindowEndAt':end,'capturedAt':NOW-1,
              'chunks':[{'file':'part-00.json.gz','sha256':'a'*64,'startAt':start,'endAt':end}]}
        (p/'capture-index.json.gz').write_bytes(gzip.compress(json.dumps(data).encode()))

if __name__=='__main__':unittest.main()
