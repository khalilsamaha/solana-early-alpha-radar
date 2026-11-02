import gzip
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import durable_admission as m
from durable_admission_checks import case,run,empty
import test_signature_replay as source


class DurableTests(unittest.TestCase):
    def test_portable_contract(self):self.assertEqual(run()['casesPassed'],22)

    def test_inner_change_requires_write_transaction(self):
        with case() as c:
            path=m.storage(c.home);path.mkdir(mode=0o700)
            book=m.Admission(path/m.NAME,c.p,lambda:c.now)
            try:
                with self.assertRaisesRegex(ValueError,'writer-transaction-required'):
                    book._change_in_transaction(book._reservation_action(c.e))
                self.assertEqual(book.status()['state'],'empty')
            finally:book.close()

    def test_raw_validation_expiry_rolls_back(self):
        with case() as c:
            original=m.timing.admission.review
            def slow(*args,**kwargs):
                r=original(*args,**kwargs);c.now=c.deadline;return r
            with patch.object(m.timing.admission,'review',slow):r=c.run()
            self.assertEqual(r['state'],'rehearsal-inspection-required');empty(c)

    def test_duplicate_recovery_sidecar_and_policy_conflict_fail_closed(self):
        with case() as c:
            c.run();side=Path(str(c.path)+'-journal');side.write_bytes(b'preserve');side.chmod(0o600)
            before=c.files();r=c.status();self.assertEqual(r['state'],'rehearsal-inspection-required');self.assertEqual(before,c.files())
            side.unlink()
            with sqlite3.connect(c.path) as db:
                p=json.loads(db.execute('SELECT value FROM admission_policy').fetchone()[0]);p['maximumTotalFeeLamports']='31000'
                db.execute('UPDATE admission_policy SET value=?',(m.encoded(p),))
            before=c.files();r=c.status();self.assertEqual(r['state'],'rehearsal-inspection-required');self.assertEqual(before,c.files())

    def test_missing_symlink_and_partial_directory_are_preserved(self):
        with case() as c:
            slot=m.storage(c.home);slot.symlink_to(c.home,target_is_directory=True)
            before=c.files();r=c.run();self.assertEqual(c.collections,0);self.assertEqual(r['state'],'unavailable')
            self.assertEqual(c.status()['state'],'rehearsal-inspection-required');self.assertEqual(before,c.files())
            slot.unlink();slot.mkdir(mode=0o700)
            self.assertEqual(c.run()['state'],'unavailable');self.assertEqual(c.collections,0)
            self.assertEqual(c.status()['state'],'rehearsal-inspection-required');self.assertEqual(list(slot.iterdir()),[])

    def test_cli_modes_private_exclusive_output(self):
        cli=Path(__file__).with_name('durable_admission_cli.py')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'report.json.gz';cmd=[sys.executable,'-E','-s',str(cli),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            raw=out.read_bytes();data=json.loads(gzip.decompress(raw));self.assertEqual(data['casesPassed'],22)
            self.assertEqual(out.stat().st_mode&0o777,0o600)
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0);self.assertEqual(raw,out.read_bytes())
            for args in (['--action','prepare'],['--allow-devnet-submit'],['--action','status','--allow-local-rehearsal']):
                target=Path(d)/'other.gz';r=subprocess.run(cmd[:-1]+[str(target)]+args,capture_output=True)
                self.assertNotEqual(r.returncode,0);self.assertFalse(target.exists())


class FullSourceTests(unittest.TestCase):
    setUpClass=classmethod(source.SourceReplayTests.setUpClass.__func__)
    tearDownClass=classmethod(source.SourceReplayTests.tearDownClass.__func__)
    setUp=source.SourceReplayTests.setUp
    tearDown=source.SourceReplayTests.tearDown
    files=source.SourceReplayTests.files
    pipeline=source.SourceReplayTests.pipeline

    def test_fresh_collectors_commit_and_recover_without_source_mutation(self):
        before=self.files();original=m.prepare
        def prepare(*args,**kwargs):return original(*args,allow_local_rehearsal=True,**kwargs)
        with patch.object(m.timing,'observe',prepare):r,processes,reads,seconds=self.pipeline()
        self.assertEqual(r['state'],'unsigned-rehearsal-recorded',r)
        self.assertTrue(r['commitOnTimeObserved']);self.assertEqual(r['networkRequests'],20)
        self.assertEqual(reads,5);self.assertEqual(processes,7)
        self.assertEqual(before,self.files());self.assertFalse((self.home.parent/(self.home.name+'-entry-handoff-v1')).exists())
        # Historical review uses stored raw evidence, same pinned deployment and
        # no live-source read or network. The initial synthetic clock is fixed.
        from test_cycle_execution import BASE
        from copy import deepcopy
        baseline=dict(deepcopy(BASE),network='devnet',kind='observed-devnet-deployment',observedAtMs=0)
        path=m.storage(self.home)/m.NAME;raw=path.read_bytes()
        with patch.object(m.timing.admission,'BASELINE',baseline),patch.object(m.view,'read_locked',side_effect=AssertionError('live reread')),patch('socket.socket',side_effect=AssertionError('network')):
            s=m.status(self.home,self.wallet,self.pool,clock=lambda:self._profile_stamp+20000)
        self.assertEqual(s['state'],'unsigned-rehearsal-expired',s);self.assertTrue(s['reservationRecorded'])
        self.assertFalse(s['commitTimingKnown']);self.assertEqual(path.read_bytes(),raw)
        print(json.dumps(dict(kind='synthetic-durable-admission',seconds=seconds,verifierProcesses=processes,sourceReads=reads)),flush=True)


if __name__=='__main__':unittest.main()
