import copy
import json
import gzip
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import reservation_view as m
import test_readiness as fixture
from test_cycle_execution import s, binding


class ReservationViewCase(unittest.TestCase):
    setUpClass = classmethod(fixture.ReadinessCase.setUpClass.__func__)
    tearDownClass = classmethod(fixture.ReadinessCase.tearDownClass.__func__)
    setUp = fixture.ReadinessCase.setUp
    tearDown = fixture.ReadinessCase.tearDown
    files = fixture.ReadinessCase.files

    def inspect(self, **kwargs):
        return m.inspect(self.home, self.wallet, self.pool, **kwargs)

    def test_closed_view_replays_receipts_without_key_rpc_or_writes(self):
        before = self.files()
        with (patch('core.signer', side_effect=AssertionError('sign')),
              patch('urllib.request.urlopen', side_effect=AssertionError('network'))):
            r = self.inspect()
        self.assertEqual(r['state'], 'local-reservations-observed', r)
        v = r['reservations']
        self.assertEqual(v['phase'], 'closed')
        self.assertEqual(v['nativeHeldLamports'], '0')
        self.assertEqual([a['heldAtomic'] for a in v['tokenAccounts']], ['0','0'])
        self.assertEqual(v['confirmedFeeLamports'], '20000')
        self.assertFalse(r['nextCycleAuthorized'])
        self.assertFalse(r['walletWideReservationsKnown'])
        self.assertEqual(before, self.files())

    def test_missing_spending_ledger_does_not_become_zero_or_get_created(self):
        (self.home/binding.CYCLE/s.spend_guard.NAME).unlink()
        before = self.files(); r = self.inspect()
        self.assertEqual(r['state'], 'unavailable')
        self.assertIsNone(r['reservations']); self.assertEqual(before, self.files())

    def test_recovery_sidecars_remain_untouched(self):
        for suffix in ('-journal','-wal','-shm'):
            p = self.home/binding.CYCLE/(s.spend_guard.NAME+suffix)
            p.write_bytes(b'preserve'); p.chmod(0o600)
            before = self.files()
            self.assertEqual(self.inspect()['state'], 'unavailable')
            self.assertEqual(before, self.files()); p.unlink()

    def test_stop_and_lock_contention_refuse_without_mutation(self):
        with m.cycles.c.source_lock(self.home, self.wallet):
            self.assertEqual(self.inspect()['state'], 'unavailable')
        p = self.home/'STOP'; p.touch(mode=0o600); before = self.files()
        self.assertEqual(self.inspect()['state'], 'unavailable')
        self.assertEqual(before, self.files())

    def test_wrong_wallet_pool_and_source_symlink(self):
        from pool_fixtures import fake_key
        self.assertEqual(m.inspect(self.home,fake_key('wallet'),self.pool)['state'], 'unavailable')
        self.assertEqual(m.inspect(self.home,self.wallet,fake_key('pool'))['state'], 'unavailable')
        p = self.home/binding.CYCLE/s.spend_guard.NAME
        renamed = p.with_suffix('.saved'); p.rename(renamed); p.symlink_to(renamed)
        before = self.files(); self.assertEqual(self.inspect()['state'], 'unavailable')
        self.assertEqual(before, self.files())

    def test_missing_final_receipt_cannot_release_reserved_money(self):
        (self.home/binding.CYCLE/s.REVERSE_CHILD/'receipt-evidence.json').unlink()
        before = self.files(); self.assertEqual(self.inspect()['state'], 'unavailable')
        self.assertEqual(before, self.files())

    def test_unresolved_exit_retains_real_journal_reservations(self):
        import sqlite3
        child=self.home/binding.CYCLE/s.REVERSE_CHILD
        for p in child.glob('observation-*.json'):p.unlink()
        (child/'receipt-evidence.json').unlink()
        # Restore the synthetic fixture to its valid pre-reconciliation prefix,
        # representing a process interruption before the finalized observation.
        p=self.home/binding.CYCLE/s.spend_guard.NAME
        with sqlite3.connect(p) as db:
            db.execute('DELETE FROM spending_events WHERE seq=(SELECT MAX(seq) FROM spending_events)')
        before=self.files();r=self.inspect()
        self.assertEqual(r['state'],'local-reservations-observed',r)
        self.assertEqual(r['reservations']['phase'],'exit-unresolved')
        self.assertEqual(r['reservations']['nativeHeldLamports'],'10000')
        self.assertGreater(int(r['reservations']['tokenAccounts'][1]['heldAtomic']),0)
        self.assertEqual(before,self.files())

    def test_tampered_hash_chain_is_unavailable(self):
        import sqlite3
        p = self.home/binding.CYCLE/s.spend_guard.NAME
        with sqlite3.connect(p) as db:
            db.execute("UPDATE spending_events SET event_hash='wrong' WHERE seq=1")
        before = self.files(); self.assertEqual(self.inspect()['state'], 'unavailable')
        self.assertEqual(before, self.files())

    def test_clock_regression_deadline_and_future_ledger(self):
        stamp = m.now()
        for ticks in ((stamp,stamp-1), (stamp,stamp+10001), (0,0)):
            it = iter(ticks)
            self.assertEqual(self.inspect(clock=lambda:next(it))['state'], 'unavailable')

    def test_no_raw_signed_bytes_or_signatures_exported(self):
        text = json.dumps(self.inspect())
        child = self.home/binding.CYCLE/s.REVERSE_CHILD
        signed = json.loads((child/'signed.json').read_text())
        self.assertNotIn(signed['wire'], text)
        self.assertNotIn(s.report(child.parent,self.wallet,reverse=True)['signature'], text)

    def test_public_reservation_report_not_accepted_as_binding_input(self):
        with patch.object(m,'read_locked', side_effect=AssertionError('must not read')):
            r = m.bind(self.home,self.wallet,self.pool,{'reservations': {'otherTokenAtomic':'0'}})
        self.assertEqual(r['state'], 'unavailable')
        self.assertFalse(r['localLedgerRead'])

    def synthetic_bundle(self, stamp):
        # Copy synthetic fixture evidence, never rewrite a real journal or assert
        # these clocks represent live chain observations.
        from preflight import split_capture
        raw = json.loads((self.home/binding.CYCLE/s.CHILD/'presend-preflight.json').read_text())
        c, _ = split_capture(raw)
        c['startedAtMs'], c['finishedAtMs'] = stamp-500, stamp-200
        p = c['packet']['policy']; a = p['accounts']
        p['issuedAtMs'], p['expiresAtMs'] = stamp-1000, stamp+5000
        c['packet']['feeAssertion']['observedAtMs'] = stamp-400
        q = {k:a[k] for k in ('wallet','pool','source','destination','inputMint','outputMint')}
        q.update(network='devnet',program=m.quote_binding.PROGRAM,
                 inAmount=p['amountIn'],outAmount='1000',minimumOutAmount=p['minimumAmountOut'],
                 requestedAtMs=stamp-1500,receivedAtMs=stamp-1200,
                 contextSlot=c['evidence']['accounts']['result']['context']['slot'])
        return dict(format=m.quote_binding.VERSION,quote=q,capture=c,reservations=None,maxSlippageBps=100)

    def test_binding_uses_actual_local_ledger_and_real_parsers_without_source_changes(self):
        stamp = m.now(); b = self.synthetic_bundle(stamp); before = self.files()
        r = m.bind(self.home,self.wallet,self.pool,b,clock=lambda:stamp)
        self.assertEqual(r['state'],'local-reservation-binding-consistent',r)
        self.assertTrue(r['localLedgerRead']);self.assertIsNone(b['reservations'])
        self.assertEqual(r['binding']['binding']['inputAmountAtomic'],'1000')
        self.assertFalse(r['executionApproved']);self.assertFalse(r['nextCycleAuthorized'])
        self.assertEqual(before,self.files())

    def test_stale_quote_remains_stale_after_a_fresh_ledger_read(self):
        stamp=m.now();b=self.synthetic_bundle(stamp)
        b['quote']['requestedAtMs']=stamp-10001
        r=m.bind(self.home,self.wallet,self.pool,b,clock=lambda:stamp)
        self.assertEqual(r['state'],'unavailable');self.assertTrue(r['localLedgerRead'])
        self.assertEqual(r['binding']['reasons'],['quote-stale-or-future'])

    def test_binding_cannot_use_an_unrelated_token_account(self):
        stamp=m.now();b=self.synthetic_bundle(stamp)
        from pool_fixtures import fake_key
        b['quote']['source']=fake_key('unrelated')
        r=m.bind(self.home,self.wallet,self.pool,b,clock=lambda:stamp)
        self.assertEqual(r['state'],'unavailable');self.assertIsNone(r['binding'])

    def test_fresh_quote_collectors_replay_real_test_journals_without_changes(self):
        import fresh_quote
        from test_fresh_quote import Opener, responses
        from test_cycle_execution import BASE
        from preflight_checks import edit
        second=json.loads((self.home/binding.CYCLE/s.CHILD/'presend-preflight.json').read_text())
        # This old disposable fixture used an all-zero fee config. Give the
        # mocked current RPC snapshots a supported input-fee denominator; the
        # stored setup/receipt evidence is not edited or used as live evidence.
        edit(second,1,12,(2500).to_bytes(8,'little'))
        first=copy.deepcopy(second)
        first.update(packet=None,selection='explicit-pool',messageSha256=None)
        del first['accountKeys'][8:11]
        del first['evidence']['accounts']['result']['value'][8:11]
        second['evidence']['fee']['result']['value']=5000
        base=dict(copy.deepcopy(BASE),network='devnet',kind='observed-devnet-deployment',observedAtMs=0)
        opener=Opener(responses(first,second))
        before=self.files();stamp=m.now()
        with (patch('preflight.BASELINE',base),patch('preflight_capture.BASELINE',base),
              patch('core.signer',side_effect=AssertionError('sign'))):
            r=fresh_quote.observe(self.home,self.wallet,self.pool,opener=opener,clock=lambda:stamp)
        self.assertEqual(r['state'],'fresh-quote-observation-consistent',r)
        self.assertEqual(r['networkRequests'],18)
        self.assertEqual(r['reservations']['confirmedFeeLamports'],'20000')
        self.assertFalse(r['nextCycleAuthorized']);self.assertFalse(r['privateKeyAccessed'])
        self.assertEqual(before,self.files())

    def test_stop_arriving_during_binding_still_blocks(self):
        stamp=m.now();b=self.synthetic_bundle(stamp)
        real=m.quote_binding._review
        def stop(*args,**kwargs):
            (self.home/'STOP').touch(mode=0o600)
            return real(*args,**kwargs)
        with patch.object(m.quote_binding,'_review',side_effect=stop):
            r=m.bind(self.home,self.wallet,self.pool,b,clock=lambda:stamp)
        self.assertEqual(r['state'],'unavailable');self.assertIsNone(r['binding'])

    def test_projection_preserves_unknown_and_open_exposure(self):
        # Pure arithmetic projection after the storage reader has checked integrity.
        with m.cycles.c.submit.spend_guard.Guard(self.home/binding.CYCLE) as guard:
            state = guard.read()[0]; summary = guard.summary()
        for phase, principal, acquired, fee in (
                ('entry-unresolved','1000','0','20000'), ('open','0','998','10000'),
                ('exit-unresolved','0','998','10000'), ('exit-failed-position-open','0','998','0')):
            summary.update(state=phase,heldEntryPrincipalAtomic=principal,
                           lastReconciledAcquiredAtomic=acquired,reservedFeeLamports=fee)
            v = m.project(state,summary,wallet=self.wallet,pool=self.pool)
            self.assertEqual(v['tokenAccounts'][0]['heldAtomic'], principal)
            self.assertEqual(v['tokenAccounts'][1]['heldAtomic'], None if phase=='entry-unresolved' else acquired)
            self.assertEqual(v['nativeHeldLamports'],fee)
            self.assertTrue(v['exposureOpen'])
        state['quarantined'] = True
        with self.assertRaises(ValueError):m.project(state,summary,wallet=self.wallet,pool=self.pool)

    def test_cli_private_report_no_overwrite_and_no_source_output(self):
        out=Path(self.tmp.name)/'reservation-view.json.gz'
        args=[sys.executable,'-E','-s',str(Path(__file__).with_name('reservation_cli.py')),
              '--directory',str(self.home),'--wallet',self.wallet,'--pool',self.pool]
        before=self.files()
        p=subprocess.run(args+['--output',str(out)],capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stderr)
        raw=out.read_bytes();r=json.loads(gzip.decompress(raw))
        self.assertEqual(r['state'],'local-reservations-observed')
        self.assertEqual(out.stat().st_mode&0o777,0o600)
        self.assertNotEqual(subprocess.run(args+['--output',str(out)],capture_output=True,timeout=30).returncode,0)
        self.assertEqual(out.read_bytes(),raw)
        forbidden=self.home/'bad-report.json.gz'
        self.assertNotEqual(subprocess.run(args+['--output',str(forbidden)],capture_output=True,timeout=30).returncode,0)
        self.assertFalse(forbidden.exists());self.assertEqual(before,self.files())


if __name__ == '__main__':
    unittest.main()
