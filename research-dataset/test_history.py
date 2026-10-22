import copy
import gzip
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import history
from build import build, ROOT
from test_dataset import fixture, shift

HOUR = 3600000


def ledger(path, reports):
    with sqlite3.connect(path) as db:
        db.executescript('''
          PRAGMA journal_mode=WAL;
          CREATE TABLE meta(k TEXT PRIMARY KEY,v TEXT NOT NULL);
          CREATE TABLE signals(seq INTEGER PRIMARY KEY,at INTEGER,cohort TEXT,mint TEXT,
            decision TEXT NOT NULL,detected INTEGER NOT NULL,data TEXT NOT NULL);
          CREATE INDEX signals_at ON signals(detected);
          CREATE TABLE probes(seq INTEGER PRIMARY KEY,at INTEGER NOT NULL,mint TEXT NOT NULL,
            state TEXT NOT NULL,data TEXT NOT NULL);
          CREATE INDEX probes_at ON probes(at);
          CREATE TABLE incidents(at INTEGER,kind TEXT,detail TEXT);
        ''')
        for k, v in {'sourceIdentity': reports[0]['sourceIdentity'], 'cursor': {'seq': 900},
                     'version': 'quote-observer-0.7.0'}.items():
            db.execute('INSERT INTO meta VALUES(?,?)', (k, json.dumps(v)))
        for report in reports:
            insert(db, report)


def insert(db, report):
    for s in report['signals']:
        db.execute('INSERT INTO signals VALUES(?,?,?,?,?,?,?)',
                   (s['seq'], s.get('signalAt'), s.get('cohort'), s.get('mint'), s['decision'], s['detectedAt'], json.dumps(s)))
    for p in report['probes']:
        s = p['signal']
        db.execute('INSERT INTO probes VALUES(?,?,?,?,?)',
                   (s['seq'], s['detectedAt'], s['mint'], p['state'], json.dumps(p)))


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'observer.sqlite'
        self.out = self.root / 'capture'
        self.q = shift(fixture(), -365 * 24 * HOUR, 900)
        self.end = self.q['signals'][0]['detectedAt'] + HOUR
        ledger(self.db, [self.q])

    def capture(self, **kw):
        return history.capture(self.db, self.out, hours=3, chunk_hours=1,
                               evidence_cutoff=self.end, **kw)

    def test_chunk_boundaries_and_outcomes_after_entry_window(self):
        # The entry falls exactly on a chunk boundary; its later exits stay available.
        before = history.quote_backup.logical_summary(self.db)
        index = self.capture()
        reports, _, _ = history.load_capture(self.out)
        self.assertEqual([len(r['signals']) for r in reports], [0, 0, 1])
        self.assertEqual(build(reports)['rows'][0]['targets'], build([self.q])['rows'][0]['targets'])
        self.assertEqual(index['counts'], {'signals': 1, 'probes': 1})
        self.assertEqual(before, history.quote_backup.logical_summary(self.db))
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in self.out.iterdir()))

    def test_historical_end_does_not_erase_later_available_outcomes(self):
        end = self.q['signals'][0]['detectedAt'] + 1
        self.capture(end_at=end)
        reports, _, _ = history.load_capture(self.out)
        result = build(reports)
        self.assertEqual(result['merge']['coveredIntervals'][-1][1], end)
        self.assertEqual(result['capturedAt'], self.end)
        self.assertEqual(result['rows'][0]['targets']['120000']['returnPct'], 10)

    def test_half_open_end_excludes_boundary_signal(self):
        self.capture(end_at=self.q['signals'][0]['detectedAt'])
        reports, _, _ = history.load_capture(self.out)
        self.assertEqual(sum(len(r['signals']) for r in reports), 0)

    def test_one_snapshot_despite_concurrent_writer(self):
        later = shift(self.q, 1000, 901)
        original = history.publish
        written = False
        def publishing(path, data):
            nonlocal written
            if not written:
                with sqlite3.connect(self.db) as db:
                    insert(db, later)
                written = True
            original(path, data)
        with patch.object(history, 'publish', side_effect=publishing):
            self.capture()
        reports, _, _ = history.load_capture(self.out)
        self.assertEqual(sum(len(r['signals']) for r in reports), 1)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM signals').fetchone()[0], 2)

    def test_caps_fail_without_publishing_partial_capture(self):
        for limit in ('CHUNK_ROWS', 'CHUNK_BYTES', 'TOTAL_ROWS', 'TOTAL_BYTES', 'ROW_BYTES'):
            with self.subTest(limit=limit), patch.object(history, limit, 0):
                with self.assertRaisesRegex(ValueError, 'cap'):
                    self.capture()
                self.assertFalse(self.out.exists())
                self.assertFalse(list(self.root.glob('.quote-history-*')))

    def test_bad_index_identity_and_missing_index_fail(self):
        with sqlite3.connect(self.db) as db:
            db.execute('UPDATE signals SET detected=detected+1')
        with self.assertRaisesRegex(ValueError, 'index fields'):
            self.capture()
        with sqlite3.connect(self.db) as db:
            db.execute('DROP INDEX signals_at')
        with self.assertRaises(sqlite3.OperationalError):
            self.capture()
        self.assertFalse(self.out.exists())

    def test_modified_chunk_rejected(self):
        self.capture()
        part = self.out / 'part-00.json.gz'
        part.write_bytes(part.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            history.load_capture(self.out)

    def test_noncontiguous_and_path_escape_index_rejected(self):
        self.capture()
        path = self.out / 'capture-index.json.gz'
        original = history.read(path)[0]
        for field, value in [('file', '../escape.gz'), ('startAt', 1)]:
            index = copy.deepcopy(original)
            index['chunks'][0][field] = value
            with gzip.open(path, 'wt') as out:
                json.dump(index, out)
            with self.assertRaisesRegex(ValueError, 'chunk index'):
                history.load_capture(self.out)

    def test_local_archive_verified_and_uses_backup_cutoff_without_network(self):
        directory = self.root / 'backups'
        with patch.object(history.quote_backup, 'rclone', side_effect=AssertionError('network forbidden')):
            status = history.quote_backup.backup(self.db, directory)
            archive = Path(status['archive'])
            before = archive.read_bytes()
            inventory = history.backup_inventory(directory)
            self.assertEqual(len(inventory), 1)
            with history.restored(archive) as (db, cutoff, source):
                index = history.capture(db, self.out, hours=3, chunk_hours=1,
                                        end_at=self.end, evidence_cutoff=cutoff, source=source)
            self.assertEqual(index['capturedAt'], history.iso_ms(inventory[0]['snapshotCompletedAt']))
            self.assertEqual(index['source']['kind'], 'verified-local-quote-backup')
            self.assertEqual(archive.read_bytes(), before)
            archive.write_bytes(before + b'tamper')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                with history.restored(archive):
                    self.fail('unverified archive accepted')

    def test_cli_builds_history_directory(self):
        self.capture()
        output = self.root / 'dataset.json.gz'
        command = [sys.executable, str(ROOT / 'research-dataset/build.py'), '--history-dir',
                   str(self.out), '--output', str(output)]
        run = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        result, _ = history.read(output)
        self.assertEqual(result['summary']['admitted'], 1)
        self.assertTrue(result['historyCapture']['complete'])
        self.assertFalse(result['mlReadiness']['modelTrained'])

    def test_running_watch_request_counter_can_advance(self):
        early = copy.deepcopy(self.q)
        early['capturedAt'] = early['signals'][0]['signalAt'] + 20000
        p = early['probes'][0]
        p['observations'] = p['observations'][:2]
        p.pop('finishedAt'); p['state'] = 'running'; p['requests'] = 2
        self.q['probes'][0]['requests'] = 5
        self.assertEqual(build([early, self.q])['summary']['admitted'], 1)

    def test_wrapper_publishes_both_outputs_and_cleans_failed_staging(self):
        for directory in ('src', 'scripts', 'bin'):
            (self.root / directory).mkdir()
        fake_sudo = self.root / 'bin/sudo'
        fake_sudo.write_text('#!' + sys.executable + '\nimport os,subprocess,sys\n'
                            'if os.environ.get("RADAR_FAIL_TEST"): sys.exit(1)\n'
                            'sys.exit(subprocess.call(sys.argv[1:]+["--database",os.environ["RADAR_TEST_DB"]]))\n')
        fake_sudo.chmod(0o700)
        env = dict(os.environ, PATH=str(fake_sudo.parent) + os.pathsep + os.environ['PATH'],
                   RADAR_TEST_DB=str(self.db))
        cmd = ['bash', str(ROOT / 'research-dataset/history-run.sh'), '--hours', '3']
        run = subprocess.run(cmd, cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        output, = self.root.glob('radar-history-*')
        self.assertTrue((output / 'capture/capture-index.json.gz').is_file())
        self.assertTrue((output / 'research-dataset.json.gz').is_file())
        self.assertIn(str(output / 'research-dataset.json.gz'), run.stdout)
        env['RADAR_FAIL_TEST'] = '1'
        fail = subprocess.run(cmd, cwd=self.root, env=env, capture_output=True, text=True)
        self.assertNotEqual(fail.returncode, 0)
        self.assertEqual(list(self.root.glob('radar-history-*')), [output])
        self.assertFalse(list(self.root.glob('.radar-history-*')))


if __name__ == '__main__':
    unittest.main()
