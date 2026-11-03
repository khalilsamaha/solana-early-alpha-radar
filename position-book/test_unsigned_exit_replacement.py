from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import unsigned_exit_replacement as m
import unsigned_exit_replacement_checks as c


class ReplacementTests(unittest.TestCase):
    def test_portable_contract(self):
        r=c.run();self.assertEqual(r['casesPassed'],17)

    def test_offline_cli_exclusive_and_no_operational_flags(self):
        cli=Path(__file__).with_name('unsigned_exit_replacement_cli.py')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.gz';args=[sys.executable,'-E','-s',str(cli),'--output',str(out)]
            p=subprocess.run(args,capture_output=True,text=True,timeout=240)
            self.assertEqual(p.returncode,0,p.stderr+p.stdout)
            raw=out.read_bytes();r=json.loads(gzip.decompress(raw));self.assertEqual(r['casesPassed'],17)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0)
            self.assertEqual(out.read_bytes(),raw);out.unlink()
            for flag in (['--action','replace'],['--directory',d],['--allow-devnet-submit'],['--allow-unsigned-replacement']):
                self.assertNotEqual(subprocess.run(args+flag,capture_output=True).returncode,0)
                self.assertFalse(out.exists())

    def test_changed_identity_and_stop_after_collection_refuse_persistence(self):
        for mode in ('identity','stop','marker','signing'):
            with self.subTest(mode=mode),c.case() as f:
                e,p=f.capture()
                if mode=='identity':f.expected='0'*64
                if mode=='stop':(f.home/'STOP').touch(mode=0o600)
                if mode=='marker':(f.path.parent/m.MARKERS[0]).touch(mode=0o600)
                if mode=='signing':
                    b=f.book()
                    try:b.db.execute('CREATE TABLE admission_exit_signing (seq INTEGER)')
                    finally:b.close()
                before=f.path.read_bytes()
                with self.assertRaises(ValueError):f.replace(e,p)
                self.assertEqual(before,f.path.read_bytes())

    def test_old_evidence_or_provenance_rewrite_is_not_fresh_evidence(self):
        with c.case() as f:
            b=f.book()
            try:old=m.preparation.original_saved(b,f.clock())
            finally:b.close()
            before=f.path.read_bytes()
            with self.assertRaises(ValueError):f.replace(old['evidence'],old['collection'])
            self.assertEqual(before,f.path.read_bytes())
            e,p=f.capture();p['provenance']['validUntilExclusiveMs']+=30000
            with self.assertRaises(ValueError):f.replace(e,p)
            self.assertEqual(before,f.path.read_bytes())

    def test_replay_corruption_or_orphan_never_uses_old_record(self):
        for mode in ('original','replacement','orphan','too-many','early-signing'):
            with self.subTest(mode=mode),c.case() as f:
                f.run();b=f.book()
                try:
                    if mode=='original':b.db.execute("UPDATE admission_exit_preparation SET hash=?",('0'*64,))
                    if mode=='replacement':b.db.execute("UPDATE admission_exit_replacement SET value=?",('[]',))
                    if mode=='orphan':b.db.execute('DROP TABLE admission_exit_preparation')
                    if mode=='too-many':
                        b.db.execute('ALTER TABLE admission_exit_replacement RENAME TO old_replacement')
                        b.db.execute('CREATE TABLE admission_exit_replacement AS SELECT * FROM old_replacement')
                        b.db.execute('INSERT INTO admission_exit_replacement SELECT * FROM old_replacement')
                    if mode=='early-signing':
                        b.db.execute('CREATE TABLE admission_exit_signing (seq INTEGER,at_ms INTEGER)')
                        b.db.execute('INSERT INTO admission_exit_signing VALUES(1,1)')
                    with self.assertRaises((ValueError,TypeError)):m.preparation.saved(b,f.clock())
                finally:b.close()

    def test_input_caps_and_invalid_identity_before_rpc(self):
        with patch.object(m,'replace',side_effect=AssertionError('write')),patch('admission_exit_capture.collect',side_effect=AssertionError('network')):
            for identity in (None,'','X'*64,1):
                with self.assertRaises(ValueError):m.collect_and_replace('/missing','w','p',expected_preparation_sha256=identity,allow_unsigned_replacement=True)
        with c.case() as f:
            e,p=f.capture();before=f.path.read_bytes()
            with patch.object(m,'MAX_RECORD',100),self.assertRaises(ValueError):f.replace(e,p)
            self.assertEqual(before,f.path.read_bytes())

    def test_source_conflict_is_checked_at_persistence(self):
        with c.case() as f:
            e,p=f.capture();before=f.path.read_bytes()
            with patch.object(m.view,'read_locked',return_value={'phase':'wrong'}),self.assertRaises((ValueError,KeyError)):
                f.replace(e,p)
            self.assertEqual(before,f.path.read_bytes())
