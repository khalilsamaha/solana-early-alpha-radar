"""Closure stays blocked on real fixture replay; no summary authorizes release."""
import json
import socket
import sqlite3
import unittest
from unittest.mock import patch

import successor_closure as m
import test_successor_balance as fixture
import exit_closure as legacy
from test_signed_exit_timing import files


class ClosureTests(unittest.TestCase):
    F = fixture.BalanceTests
    setUpClass = classmethod(F.setUpClass.__func__)
    tearDownClass = classmethod(F.tearDownClass.__func__)
    setUp = F.setUp
    tearDown = F.tearDown
    dispatch = F.dispatch
    lost = F.lost
    boundary = F.boundary
    markers = F.markers
    rows = F.rows
    submit = F.submit
    recover = F.recover
    package = F.package
    collect_effects = F.collect_effects
    apply_accounting = F.apply_accounting
    ready = F.ready
    observe = F.observe
    rewrite = fixture.fixture.AccountingTests.rewrite

    def assess(self):
        before = files(self.c)
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('network')):
            result = m.status(self.c.home, self.c.wallet, self.c.pool, self.candidate, clock=lambda:self.c.now)
        self.assertEqual(files(self.c), before)
        for flag in ('closureEligible','closureRecorded','scopedClosureRecorded','retiredAttemptEffectsReconciled',
                     'retiredAttemptNonExecutionProven','freshBalancesEvaluated','currentWalletBalanceEstablished',
                     'sourceStateChanged','reservationsReleased','retiredExposureReleased','fundsAvailableForNewEntry',
                     'nextCycleAuthorized','executionApproved','networkRequests','privateKeyAccessed','signaturesCreated','transactionsSent'):
            self.assertFalse(result[flag], flag)
        for secret in (self.c.wallet, self.signed['signed']['signedWireBase64'], self.signed['signed']['signature']):
            self.assertNotIn(secret,json.dumps(result))
        return result

    def test_flat_accounting_exact_binding_and_fee_partition_remain_held(self):
        self.ready();result=self.assess()
        self.assertEqual(result['state'],'successor-closure-blocked-held')
        self.assertEqual(result['blockers'],['retired-exposure-unresolved'])
        self.assertEqual(result['held'],dict(originalFeeCommitmentLamports='26000',knownFeesPaidLamports='10002',
            remainingFeeHeldLamports='15998',retiredFeeExposureHeldLamports='10000',otherFeeHeldLamports='5998',
            sourceProceedsHeldAtomic='96',ownedAcquiredResidualAtomic='0',protectedAcquiredInventoryAtomic='902'))
        self.assertEqual(result['identity']['successorSha256'],self.candidate)
        book=self.c.book()
        try:
            saved=m.accounting.saved(book,self.c.now)
            self.assertEqual(result['identity']['successorAccountingSha256'],m.digest(saved))
            self.assertEqual(result['identity']['receiptCaptureSha256'],saved['captureSha256'])
        finally:book.close()

    def test_absent_accounting_never_reports_zero_exposure(self):
        for collect in (False,True):
            if collect:self.collect_effects()
            result=self.assess();self.assertIsNone(result['held'])
            self.assertIn('successor-accounting-required',result['blockers'])

    def test_failed_exit_preserves_residual_and_exposure(self):
        self.collect_effects(failure=True);self.apply_accounting();result=self.assess()
        self.assertEqual(result['blockers'],['owned-inventory-remains','retired-exposure-unresolved'])
        self.assertEqual(result['held']['ownedAcquiredResidualAtomic'],'98')
        self.assertEqual(result['held']['sourceProceedsHeldAtomic'],'0')

    def test_stop_expiry_and_repeat_are_historical_reads(self):
        self.ready();before=self.assess();self.c.now+=30000;(self.c.home/'STOP').touch(mode=0o600)
        semantic=lambda r:{k:v for k,v in r.items() if k not in ('signatureVerification','timingOptimization')}
        self.assertEqual(semantic(self.assess()),semantic(before))
        self.assertEqual(semantic(self.assess()),semantic(before))

    def test_rehashed_retired_exposure_cannot_be_erased(self):
        self.ready();book=self.c.book()
        try:
            row=m.accounting.saved(book,self.c.now);row['effects']['retiredFeeExposureHeldLamports']='0'
            book.db.execute('UPDATE admission_successor_accounting SET value=?,hash=?',
                (m.accounting.encoded(row),m.digest(row)))
        finally:book.close()
        before=files(self.c)
        with self.assertRaises(ValueError):self.assess()
        self.assertEqual(files(self.c),before)

    def test_wrong_generation_and_foreign_closure_refuse(self):
        self.ready();before=files(self.c)
        with self.assertRaises(ValueError):
            m.status(self.c.home,self.c.wallet,self.c.pool,'0'*64,clock=lambda:self.c.now)
        self.assertEqual(files(self.c),before)
        book=self.c.book()
        try:book.db.execute('CREATE TABLE admission_exit_closure(id INTEGER)')
        finally:book.close()
        before=files(self.c)
        with self.assertRaises(ValueError):self.assess()
        self.assertEqual(files(self.c),before)

    def test_query_only_snapshot_blocks_writes_and_competing_commit(self):
        self.ready();book=self.c.book();seen=[];original=m.accounting.replay
        try:
            with self.assertRaisesRegex(ValueError,'successor-closure-read-snapshot-required'):
                m.review(self.c.home,book,self.c.wallet,self.c.pool,self.candidate,lambda:self.c.now)
        finally:book.close()
        def inspect(root,b,*args):
            self.assertTrue(b.db.in_transaction);self.assertEqual(b.db.execute('PRAGMA query_only').fetchone()[0],1)
            with self.assertRaises(sqlite3.OperationalError):b.db.execute('CREATE TABLE forbidden(n)')
            other=sqlite3.connect(self.c.path,timeout=0,isolation_level=None)
            try:
                other.execute('BEGIN IMMEDIATE');other.execute('CREATE TABLE competing(n)')
                with self.assertRaises(sqlite3.OperationalError):other.execute('COMMIT')
                other.execute('ROLLBACK')
            finally:other.close()
            seen.append(True);return original(root,b,*args)
        with patch.object(m.accounting,'replay',side_effect=inspect):self.assess()
        self.assertEqual(seen,[True])

    def test_later_conflicting_receipt_cannot_reuse_prior_verdict(self):
        self.ready();self.assess()
        def change(seq,value):
            if value['kind']=='capture':value['rpcEvidence']['transaction']['result']['meta']['fee']=10001
        self.rewrite(change);result=self.assess()
        self.assertEqual(result['accountingState'],'quarantined');self.assertIsNone(result['held'])
        self.assertIn('successor-evidence-quarantined',result['blockers'])

    def test_matching_balances_do_not_unlock_legacy_closure_or_accept_report_inputs(self):
        self.ready();self.assertEqual(self.observe()['state'],'successor-balances-match-held')
        result=self.assess();self.assertEqual(result['blockers'],['retired-exposure-unresolved'])
        before=files(self.c)
        class NoRpc:
            def open(self,*args,**kwargs):raise AssertionError('unexpected RPC')
        stopped=legacy.collect_and_close(self.c.home,self.c.wallet,self.c.pool,opener=NoRpc(),
            clock=lambda:self.c.now,monotonic=lambda:0)
        self.assertEqual(stopped['state'],'exit-closure-blocked');self.assertEqual(stopped['networkRequests'],0)
        self.assertFalse(stopped['closureRecorded']);self.assertEqual(files(self.c),before)
        with self.assertRaises(TypeError):m.status('/missing','wallet','pool','hash',report=result)


if __name__=='__main__':unittest.main()
