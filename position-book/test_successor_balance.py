"""Synthetic fresh balances constructed independently from raw successor receipts."""
import base64
from copy import deepcopy
import io
import json
import sqlite3
import unittest
from unittest.mock import patch

import successor_balance as m
import test_successor_accounting as fixture
from test_signed_exit_timing import files


def fixture_rows(case):
    package, scope = case.package(); roles = scope['accounts']
    keys = [roles['wallet'], roles['destination'], roles['source'], roles['outputMint'], roles['inputMint']]
    tx = package['bundle']['rpcEvidence']['transaction']['result']
    book = case.c.book()
    try:
        record = m.accounting.submission.handoff.successor.row(book)
        capture = record['candidate']['evidence']['capture']
    finally: book.close()
    by_key = dict(zip(capture['accountKeys'], capture['evidence']['accounts']['result']['value']))
    rows = deepcopy([by_key[key] for key in keys]); txkeys = tx['transaction']['message']['accountKeys']
    rows[0]['lamports'] = tx['meta']['postBalances'][txkeys.index(keys[0])]
    for i in (1, 2):
        amount = next(row for row in tx['meta']['postTokenBalances'] if row['accountIndex'] == txkeys.index(keys[i]))['uiTokenAmount']['amount']
        raw = bytearray(base64.b64decode(rows[i]['data'][0])); raw[64:72] = int(amount).to_bytes(8, 'little')
        rows[i]['data'] = [base64.b64encode(raw).decode(), 'base64']
    return keys, rows, tx['slot']


class Replies:
    def __init__(self, case, *, callback=None):
        self.case = case; self.keys, self.rows, self.slot = fixture_rows(case)
        self.minimum = self.slot; self.calls = []; self.callback = callback
        self.genesis = m.original.GENESIS['devnet']; self.block = None; self.error = False
    def open(self, request, timeout):
        query = json.loads(request.data); self.calls.append((query, timeout)); t = self.case
        t.assertEqual(request.full_url, m.original.ENDPOINT); t.assertTrue(0 < timeout <= 10)
        t.assertEqual(query['method'], m.original.METHODS[len(self.calls)-1])
        if self.callback: self.callback(query['method'])
        if query['method'] == 'getGenesisHash':
            t.assertEqual(query['params'], []); value = self.genesis
        elif query['method'] == 'getMultipleAccounts':
            t.assertEqual(query['params'], [self.keys, dict(encoding='base64', commitment='finalized', minContextSlot=self.minimum)])
            value = dict(context=dict(slot=self.slot), value=self.rows)
        else:
            t.assertEqual(query['params'], [self.slot]); value = t.c.now//1000 if self.block is None else self.block
        result = dict(jsonrpc='2.0', id=query['id'], result=value)
        if self.error: result = dict(jsonrpc='2.0', id=query['id'], error={'message': 'private provider detail'})
        return io.BytesIO(json.dumps(result).encode())


class BalanceTests(unittest.TestCase):
    F = fixture.AccountingTests
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

    def ready(self):
        self.collect_effects(); self.apply_accounting()

    def observe(self, rpc=None, **kwargs):
        before = files(self.c)
        result = m.collect(self.c.home, self.c.wallet, self.c.pool, self.candidate,
            opener=rpc or Replies(self), clock=lambda: self.c.now, monotonic=kwargs.pop('monotonic', lambda: 0), **kwargs)
        self.assertEqual(files(self.c), before)
        for key in ('evidencePersisted', 'sourceStateChanged', 'reservationsReleased', 'retiredExposureReleased',
                    'retiredAttemptNonExecutionProven', 'fundsAvailableForNewEntry', 'scopedClosureRecorded',
                    'nextCycleAuthorized', 'executionApproved', 'privateKeyAccessed', 'signaturesCreated', 'transactionsSent'):
            self.assertFalse(result[key], key)
        for secret in (self.c.wallet, self.signed['signed']['signedWireBase64'], 'private provider detail'):
            self.assertNotIn(secret, json.dumps(result))
        return result

    def test_fresh_five_account_snapshot_matches_successor_receipt_and_preserves_exposure(self):
        self.ready(); rpc = Replies(self); result = self.observe(rpc)
        self.assertEqual(result['state'], 'successor-balances-match-held', result)
        self.assertEqual(result['networkRequests'], 4); self.assertEqual(len(rpc.calls), 4)
        self.assertGreater(result['headroomAtReturnMs'], 0)
        self.assertEqual(result['snapshot']['ownedAcquiredResidualAtomic'], '0')
        self.assertEqual(result['snapshot']['acquiredAccountAtomic'], '902')
        self.assertEqual(result['snapshot']['sourceProceedsHeldAtomic'], '96')
        self.assertEqual(result['snapshot']['feeHeldLamports'], '15998')
        self.assertEqual(result['snapshot']['retiredFeeExposureHeldLamports'], '10000')

    def test_missing_accounting_or_failed_exit_cannot_request_balances(self):
        rpc = Replies(self); self.assertFalse(self.observe(rpc)['balanceReconciliationPassed']); self.assertFalse(rpc.calls)
        self.collect_effects(failure=True); self.apply_accounting(); rpc = Replies(self)
        result = self.observe(rpc); self.assertEqual(result['diagnosticCode'], 'successor-balance-flat-required')
        self.assertFalse(rpc.calls)

    def test_no_default_network_provider_and_wrong_generation_refuse(self):
        with patch.object(m.accounting.submission.transport, '_open', side_effect=AssertionError('source access')):
            with self.assertRaisesRegex(ValueError, 'successor-balance-injected-provider-required'):
                m.collect('/missing', 'wallet', 'pool', 'hash')
        self.ready(); rpc = Replies(self); before = files(self.c)
        result = m.collect(self.c.home, self.c.wallet, self.c.pool, '0'*64,
            opener=rpc, clock=lambda: self.c.now, monotonic=lambda: 0)
        self.assertFalse(result['balanceReconciliationPassed']); self.assertFalse(rpc.calls)
        self.assertEqual(files(self.c), before)

    def test_current_source_commitments_and_post_observation_change_block(self):
        self.ready(); original = m.view.read_locked
        for threshold in (0, 4):
            rpc = Replies(self)
            def changed(*args, **kwargs):
                source = deepcopy(original(*args, **kwargs))
                if not kwargs.get('_closed_history', False) and len(rpc.calls) >= threshold:
                    source['nativeHeldLamports'] = '1'
                return source
            with patch.object(m.view, 'read_locked', side_effect=changed): result = self.observe(rpc)
            self.assertFalse(result['balanceReconciliationPassed'])
            self.assertEqual(result['diagnosticCode'], 'balance-source-changed')
            self.assertEqual(len(rpc.calls), threshold)

    def test_account_drift_including_deposits_and_missing_accounts_blocks(self):
        self.ready()
        def token_amount(rows):
            raw = bytearray(base64.b64decode(rows[2]['data'][0])); raw[64:72] = (901).to_bytes(8, 'little')
            rows[2]['data'] = [base64.b64encode(raw).decode(), 'base64']
        for mutate in (lambda rows: rows[0].update(lamports=rows[0]['lamports']+1),
                       lambda rows: rows[0].update(lamports=rows[0]['lamports']-1), token_amount,
                       lambda rows: rows[3].update(lamports=rows[3]['lamports']+1),
                       lambda rows: rows.__setitem__(1, None)):
            rpc = Replies(self); mutate(rpc.rows); result = self.observe(rpc)
            self.assertFalse(result['balanceReconciliationPassed']); self.assertIsNone(result['snapshot'])

    def test_cluster_slot_chain_clock_and_provider_errors_stay_held(self):
        self.ready()
        for field, value in (('genesis', m.original.GENESIS['mainnet-beta']), ('slot', 0),
                             ('block', self.c.now//1000-60), ('block', self.c.now//1000+60), ('error', True)):
            with self.subTest(field=field):
                rpc = Replies(self); setattr(rpc, field, value); result = self.observe(rpc)
                self.assertFalse(result['balanceReconciliationPassed']); self.assertLessEqual(len(rpc.calls), 4)

    def test_stop_during_request_prevents_following_request(self):
        self.ready(); rpc = Replies(self, callback=lambda method: (self.c.home/'STOP').touch(mode=0o600))
        before = files(self.c)
        result = m.collect(self.c.home, self.c.wallet, self.c.pool, self.candidate,
            opener=rpc, clock=lambda: self.c.now, monotonic=lambda: 0)
        self.assertEqual(len(rpc.calls), 1); self.assertEqual(result['diagnosticCode'], 'balance-stopped')
        (self.c.home/'STOP').unlink(); self.assertEqual(files(self.c), before)

    def test_validation_and_close_time_cannot_publish_stale_success(self):
        self.ready(); stamp = self.c.now; original = m.original.review
        def slow(*args):
            result = original(*args); self.c.now += m.original.FRESH_MS; return result
        with patch.object(m.original, 'review', side_effect=slow):
            result = self.observe(); self.assertFalse(result['balanceReconciliationPassed'])
        self.c.now = stamp; rpc = Replies(self); book = self.c.book()
        try: book_type = type(book); close = book_type.close
        finally: book.close()
        def slow_close(book):
            close(book)
            if len(rpc.calls) == 4: self.c.now += m.original.FRESH_MS
        with patch.object(book_type, 'close', slow_close): result = self.observe(rpc)
        self.assertFalse(result['balanceReconciliationPassed']); self.assertIsNone(result['snapshot'])

    def test_snapshot_blocks_writer_and_operation_budget_clips_timeouts(self):
        self.ready(); collisions = []
        def collide(method):
            db = sqlite3.connect(self.c.path, timeout=0, isolation_level=None)
            try:
                db.execute('BEGIN IMMEDIATE'); db.execute('CREATE TABLE competing_writer (n INTEGER)')
                with self.assertRaises(sqlite3.OperationalError): db.execute('COMMIT')
                db.execute('ROLLBACK'); collisions.append(True)
            finally: db.close()
        self.assertTrue(self.observe(Replies(self, callback=collide))['balanceReconciliationPassed'])
        self.assertEqual(len(collisions), 4)
        tick = [0]; original = m.context; calls = []
        def slow(*args):
            result = original(*args); calls.append(True)
            if len(calls) == 1: tick[0] = 119.5
            return result
        rpc = Replies(self)
        with patch.object(m, 'context', side_effect=slow): result = self.observe(rpc, monotonic=lambda: tick[0])
        self.assertTrue(result['balanceReconciliationPassed'], result)
        self.assertTrue(all(timeout <= 0.5 for _, timeout in rpc.calls))
        tick[0] = 0; calls.clear(); rpc = Replies(self)
        def too_slow(*args):
            result = original(*args); tick[0] = 120; return result
        with patch.object(m, 'context', side_effect=too_slow): result = self.observe(rpc, monotonic=lambda: tick[0])
        self.assertEqual(result['diagnosticCode'], 'successor-balance-total-budget'); self.assertFalse(rpc.calls)


if __name__ == '__main__': unittest.main()
