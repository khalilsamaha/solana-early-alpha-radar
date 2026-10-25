"""Replay real signed synthetic journals for the two-cycle historical book."""
import copy
import gzip
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch
import cycles as m
import test_unsigned_replacement as fixture
from test_cycle_execution import s, binding, Transport, BASE, fake_key


class TwoCycleCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.UnsignedReplacementCase.setUpClass.__func__(cls)
        helper = fixture.UnsignedReplacementCase()
        helper.home = cls.template; helper.wallet = cls.wallet; helper.pool = cls.pool
        baseline = dict(copy.deepcopy(BASE), network='devnet', kind='observed-devnet-deployment', observedAtMs=0)
        with patch('preflight.BASELINE', baseline), patch('preflight_capture.BASELINE', baseline):
            helper.prepare()
            assert helper.entry()['state'] == 'finalized-success'
            assert s.execute_reverse(cls.template, cls.wallet, cls.pool, cycle=True,
                opener=Transport(cls.template,cls.wallet,reverse=True), sleeper=lambda _:None)['state'] == 'finalized-success'
            m.c.sync(cls.template, cls.wallet, cls.pool)
        (cls.template / 'signer.pk8').unlink()
    tearDownClass = classmethod(fixture.UnsignedReplacementCase.tearDownClass.__func__)
    setUp = fixture.UnsignedReplacementCase.setUp
    tearDown = fixture.UnsignedReplacementCase.tearDown

    def sync(self): return m.sync(self.home, self.wallet, self.pool)
    def files(self):
        return {str(p.relative_to(self.home)):p.read_bytes() for p in self.home.rglob('*')
                if p.is_file() and not p.name.startswith(m.NAME)}
    def ledger(self): return m.Ledger(self.home, create=False)

    def test_two_closed_positions_credit_and_fees_reconcile_without_key_or_network(self):
        before=self.files()
        with patch('core.signer',side_effect=AssertionError('sign')), patch('urllib.request.urlopen',side_effect=AssertionError('network')):
            r=self.sync()
        self.assertEqual(r['state'],'closed'); v=r['accounting']; t=v['totals']
        self.assertEqual(len(v['positions']),2); self.assertEqual(t['grossOriginalSpentAtomic'],'2000')
        self.assertEqual(t['confirmedSwapFeeLamports'],'20000'); self.assertEqual(t['residualAcquiredAtomic'],'0')
        self.assertEqual(int(t['walletBeforeFirstEntryLamports'])+int(t['verifiedBetweenCycleCreditLamports'])-20000,int(t['walletAfterSecondExitLamports']))
        self.assertGreater(int(t['verifiedBetweenCycleCreditLamports']),0)
        self.assertEqual(before,self.files()); self.assertFalse(r['nextCycleAuthorized'])
        self.assertTrue(v['source']['unsignedReplacement']['originalReservationPreserved'])

    def test_repeat_and_new_process_do_not_double_count(self):
        first=self.sync(); second=self.sync()
        self.assertTrue(first['ledgerChanged']);self.assertFalse(second['ledgerChanged']);self.assertEqual(second['eventCount'],1)
        out=Path(self.tmp.name)/'book.json.gz'
        r=subprocess.run([sys.executable,'-E','-s',str(Path(__file__).with_name('cycles_cli.py')),'--action','sync',
            '--directory',str(self.home),'--wallet',self.wallet,'--pool',self.pool,'--output',str(out)],capture_output=True,text=True,timeout=30)
        self.assertEqual(r.returncode,0,r.stderr)
        with gzip.open(out,'rt') as f:third=json.load(f)
        self.assertEqual(third['accounting'],first['accounting']); self.assertEqual(third['eventCount'],1)
        self.assertFalse(third['ledgerChanged'])

    def test_missing_exit_before_first_import_creates_no_book(self):
        shutil.rmtree(self.home/binding.CYCLE/s.REVERSE_CHILD)
        with self.assertRaises(ValueError):self.sync()
        self.assertFalse((self.home/m.NAME).exists())

    def test_lost_source_after_import_quarantines_and_cannot_self_clear(self):
        first=self.sync();p=self.home/binding.CYCLE/s.REVERSE_CHILD/'receipt-evidence.json';raw=p.read_bytes();p.unlink()
        r=self.sync();self.assertEqual(r['state'],'quarantined'); self.assertFalse(r['accounting']['accountingUsable'])
        self.assertEqual(r['accounting']['totals'],first['accounting']['totals'])
        p.write_bytes(raw);p.chmod(0o600)
        again=self.sync();self.assertEqual(again['state'],'quarantined');self.assertEqual(again['eventCount'],2)
        self.assertFalse(again['ledgerChanged'])

    def test_public_summary_tamper_does_not_replace_raw_receipt_evidence(self):
        p=self.home/binding.CYCLE/s.REVERSE_CHILD/'observation-000.json'
        v=json.loads(p.read_text());v['receipt']['outputAtomic']='999999';p.write_text(json.dumps(v))
        with self.assertRaises(ValueError):self.sync()
        self.assertFalse((self.home/m.NAME).exists())

    def test_archive_change_is_not_ignored(self):
        self.sync();p=self.home/binding.CYCLE/fixture.u.ARCHIVE/'failure.json';p.write_bytes(p.read_bytes()+b' ')
        self.assertEqual(self.sync()['state'],'quarantined')

    def test_source_spending_change_is_not_ignored(self):
        self.sync()
        with sqlite3.connect(self.home/binding.CYCLE/s.spend_guard.NAME) as db:
            db.execute("UPDATE spending_events SET event_hash='changed' WHERE seq=1")
        self.assertEqual(self.sync()['state'],'quarantined')

    def test_wrong_pool_or_wallet_does_not_poison_book(self):
        self.sync();before=(self.home/m.NAME).read_bytes()
        for wallet,pool in ((fake_key('wrong-wallet'),self.pool),(self.wallet,fake_key('wrong-pool'))):
            with self.assertRaises(ValueError):m.sync(self.home,wallet,pool)
        self.assertEqual(before,(self.home/m.NAME).read_bytes())

    def test_source_lock_prevents_concurrent_accounting(self):
        with m.c.source_lock(self.home,self.wallet):
            with self.assertRaises(BlockingIOError):self.sync()
        self.assertFalse((self.home/m.NAME).exists())

    def test_unsafe_book_permissions_and_symlink_rejected(self):
        self.sync();p=self.home/m.NAME;p.chmod(0o644)
        with self.assertRaises(ValueError):self.sync()
        p.chmod(0o600);saved=self.home/'saved-book';p.rename(saved);p.symlink_to(saved)
        with self.assertRaises(OSError):self.sync()

    def test_modified_accounting_hash_rejected(self):
        self.sync()
        with sqlite3.connect(self.home/m.NAME) as db:db.execute("UPDATE controlled_events SET event_hash='changed'")
        with self.assertRaises(ValueError):self.sync()

    def test_generic_or_first_cycle_book_cannot_be_relabelled(self):
        shutil.copy2(self.home/m.c.NAME,self.home/m.NAME)
        with self.assertRaises(ValueError):self.sync()

    def test_interruption_before_commit_leaves_no_partial_totals(self):
        with patch.object(m.Ledger,'result',side_effect=RuntimeError('synthetic interruption')):
            with self.assertRaises(RuntimeError):self.sync()
        ledger=self.ledger()
        try:self.assertEqual(ledger.read()[1],0)
        finally:ledger.close()
        self.assertEqual(self.sync()['eventCount'],1)

    def test_closed_snapshot_change_is_quarantined_without_overwriting_totals(self):
        first=self.sync();v=copy.deepcopy(first['accounting']);v['totals']['confirmedSwapFeeLamports']='0'
        ledger=self.ledger()
        try:r=ledger.apply(v)
        finally:ledger.close()
        self.assertEqual(r['state'],'quarantined');self.assertEqual(r['accounting']['totals'],first['accounting']['totals'])

    def test_clock_regression_rolls_back_quarantine(self):
        self.sync();ledger=self.ledger()
        try:
            ledger.j.clock=lambda:1
            with self.assertRaises(ValueError):ledger.apply(source_error=True)
            self.assertEqual(ledger.read()[0]['state'],'closed');self.assertEqual(ledger.read()[1],1)
        finally:ledger.close()

    def test_no_signed_bytes_in_report_and_stop_does_not_block_accounting(self):
        (self.home/'STOP').touch(mode=0o600);r=self.sync();text=json.dumps(r)
        for home in (self.home,self.home/binding.CYCLE):
            for child in (s.CHILD,s.REVERSE_CHILD):
                wire=json.loads((home/child/'signed.json').read_text())['wire'];self.assertNotIn(wire,text)
        self.assertEqual(r['transactionsSent'],0);self.assertFalse(r['privateKeyAccessed'])


if __name__=='__main__':unittest.main()
