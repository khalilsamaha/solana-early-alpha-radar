import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import capture_review as cr
from audit import load_capture, build
import history
from test_history import ledger
from test_dataset import fixture, shift

HOUR = 3600000

class CaptureReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.q = shift(fixture(), -365 * 24 * HOUR, 900)
        self.end = self.q['signals'][0]['detectedAt'] + HOUR
        self.n = 0

    def capture(self, q=None, end=None):
        self.n += 1
        db = self.root / ('db' + str(self.n))
        out = self.root / ('capture' + str(self.n))
        ledger(db, [q or self.q])
        history.capture(db, out, hours=3, chunk_hours=1, evidence_cutoff=end or self.end)
        return out

    def test_overlapping_captures_equal_original_and_order_independent(self):
        a = self.capture(); b = self.capture(end=self.end+1000)
        data, evidence = cr.combine([b, a])
        self.assertEqual(data['rows'], build(load_capture(b)[0])['rows'])
        self.assertEqual(cr.combine([a,b]), (data,evidence))
        self.assertEqual(evidence['uniqueAdmittedWatches'], 1)
        self.assertEqual(evidence['duplicateWatchesRemoved'], 1)
        self.assertEqual(evidence['decisionCounts'][0]['count'], 1)
        self.assertFalse(evidence['gapBetweenCaptures'])

    def test_pending_watch_accepts_only_append_only_progress(self):
        early = copy.deepcopy(self.q)
        p = early['probes'][0]
        p['observations'] = p['observations'][:2]
        p.pop('finishedAt'); p['state'] = 'running'; p['requests'] = 2
        self.q['probes'][0]['requests'] = 5
        a = self.capture(early, early['signals'][0]['signalAt']+20000)
        b = self.capture()
        data, _ = cr.combine([b,a])
        self.assertEqual(data['rows'], build(load_capture(b)[0])['rows'])

    def test_revised_terminal_watch_refused(self):
        a = self.capture()
        q = copy.deepcopy(self.q); q['probes'][0]['finishedAt'] += 1
        b = self.capture(q, self.end+1000)
        with self.assertRaisesRegex(ValueError, 'revised probe'):
            cr.combine([a,b])

    def test_immutable_entry_conflict_refused(self):
        a = self.capture()
        q = copy.deepcopy(self.q)
        for s in [q['signals'][0],q['probes'][0]['signal']]:
            s['features']['liquidityUsd'] = 9999
        b = self.capture(q, self.end+1000)
        with self.assertRaisesRegex(ValueError,'immutable signal'):
            cr.combine([a,b])

    def test_source_change_refused(self):
        a = self.capture()
        q = copy.deepcopy(self.q); q['sourceIdentity'] = 'other-source'
        b = self.capture(q, self.end+1000)
        with self.assertRaisesRegex(ValueError,'source identities'):
            cr.combine([a,b])

    def test_coverage_gaps_explicit_and_separate_watches_retained(self):
        a = self.capture()
        q = shift(self.q, 5*HOUR, 901)
        b = self.capture(q, self.end+5*HOUR)
        data,e = cr.combine([a,b])
        self.assertEqual(len(data['rows']),2)
        self.assertTrue(e['gapBetweenCaptures'])
        self.assertEqual(len(e['coveredIntervals']),2)

    def test_tampered_chunk_and_caps_fail(self):
        a = self.capture()
        for name in ('MAX_SIGNALS','MAX_WATCHES','MAX_COMBINED_BYTES'):
            with self.subTest(name=name), patch.object(cr,name,0):
                with self.assertRaisesRegex(ValueError,'cap'): cr.combine([a])
        with self.assertRaises(ValueError): cr.combine([a]*9)
        p=a/'part-00.json.gz'; p.write_bytes(p.read_bytes()+b'tampered')
        with self.assertRaisesRegex(ValueError,'checksum'): cr.combine([a])

    def test_skipped_signals_preserved_in_counts_not_assigned_returns(self):
        q = copy.deepcopy(self.q); q['signals'][0]['decision']='observer-busy'; q['probes']=[]
        a = self.capture(q)
        data,e = cr.combine([a,a])
        self.assertEqual(data['rows'],[])
        self.assertEqual(e['uniqueEligibleSignals'],1)
        self.assertEqual(e['decisionCounts'][0]['decision'],'observer-busy')
        self.assertEqual(e['decisionCounts'][0]['count'],1)

if __name__=='__main__': unittest.main()
