"""Closed synthetic signed round trip, real receipt replay, bounded read-only transport."""
import base64
import copy
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import cycle_preparation as c
import test_reverse_swap as reverse
from pool_fixtures import BASE, Response, fake_key


class Transport:
    def __init__(self, home, wallet, change=None):
        self.calls = []; self.change = change
        self.receipts = {}
        for name in (c.submit.CHILD, c.submit.REVERSE_CHILD):
            child = home / name
            sig = c.submit.bound(child, wallet)[2]['signatures'][0]
            self.receipts[sig] = c.submit.read(child, 'receipt-evidence.json', 131072)
        last = c.submit.report(home, wallet, reverse=True)['observation']['receipt']
        capture = c.submit.read(home / c.submit.REVERSE_CHILD, 'presend-preflight.json', 4 * 1024 * 1024)
        self.rows = dict(zip(capture['accountKeys'], capture['evidence']['accounts']['result']['value']))
        self.rows[wallet]['lamports'] = int(last['walletAfterLamports'])
        for effect in last['tokenEffects'].values():
            row = self.rows[effect['account']]
            raw = bytearray(base64.b64decode(row['data'][0]))
            raw[64:72] = int(effect['afterAtomic']).to_bytes(8, 'little')
            row['data'][0] = base64.b64encode(raw).decode()

    def open(self, req, timeout=None):
        q = json.loads(req.data); self.calls.append(q)
        assert req.full_url == 'https://api.devnet.solana.com'
        method = q['method']
        if method == 'getGenesisHash': value = c.GENESIS['devnet']
        elif method == 'getSignatureStatuses':
            value = dict(context={'slot': 140}, value=[copy.deepcopy(self.receipts[q['params'][0][0]]['status'])])
        elif method == 'getTransaction': value = copy.deepcopy(self.receipts[q['params'][0]]['transaction'])
        elif method == 'getMultipleAccounts':
            assert q['params'][1] == dict(encoding='base64', commitment='finalized', minContextSlot=130)
            value = dict(context={'slot': 140}, value=[copy.deepcopy(self.rows[k]) for k in q['params'][0]])
        else: raise AssertionError('Unexpected RPC: ' + method)
        if self.change: value = self.change(q, value)
        return Response(json.dumps(dict(jsonrpc='2.0', id=q['id'], result=value)).encode())


class CyclePreparationCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reverse.ReverseCase.setUpClass.__func__(cls)
        baseline = dict(copy.deepcopy(BASE), network='devnet', kind='observed-devnet-deployment', observedAtMs=0)
        with patch('preflight.BASELINE', baseline), patch('preflight_capture.BASELINE', baseline):
            r = c.submit.execute_reverse(cls.template, cls.wallet, cls.pool,
                opener=reverse.ReverseTransport(cls.template), sleeper=lambda _: None)
            assert r['state'] == 'finalized-success', r
    tearDownClass = classmethod(reverse.ReverseCase.tearDownClass.__func__)
    setUp = reverse.ReverseCase.setUp
    tearDown = reverse.ReverseCase.tearDown

    def run_prepare(self, change=None, **kw):
        t = Transport(self.home, self.wallet, change)
        return c.run(self.home, self.wallet, self.pool, prepare=True, opener=t, **kw), t

    def old_files(self):
        return {str(p.relative_to(self.home)): p.read_bytes() for p in self.home.rglob('*')
                if p.is_file() and c.CYCLE not in p.parts}

    def test_prepare_keeps_every_old_file_and_carries_gross_input_and_fees(self):
        before = self.old_files(); r,t = self.run_prepare()
        self.assertEqual(r['state'], 'prepared-not-executable')
        self.assertEqual(r['networkRequests'],7); self.assertEqual(len(t.calls),7)
        self.assertEqual(r['budget']['cumulativeEntryWithAllocationAtomic'],'2000')
        self.assertEqual(r['budget']['cumulativeSwapFeesWithAllocationLamports'],'30000')
        self.assertEqual(r['budget']['historicalNetOriginalTokenAtomic'],'-4')
        self.assertEqual(r['balancesAtPreparation']['backgroundAcquiredAtomic'],'500000000')
        self.assertFalse(r['executionApproved']); self.assertFalse(r['pretradeBudgetEnforced'])
        self.assertEqual(before,self.old_files())

    def test_repeat_and_status_preserve_allocation_without_network_or_new_cycle(self):
        first,_ = self.run_prepare(); t=Transport(self.home,self.wallet)
        second=c.run(self.home,self.wallet,self.pool,prepare=True,opener=t)
        self.assertFalse(second['preparationCreated']); self.assertEqual(t.calls,[])
        self.assertEqual(first['preparationSha256'],second['preparationSha256'])
        self.assertEqual(second,c.run(self.home,self.wallet,self.pool))

    def test_private_key_is_not_needed_for_preparation(self):
        t=Transport(self.home,self.wallet)
        (self.home/'signer.pk8').unlink()
        with patch('core.signer',side_effect=AssertionError('key access')):
            r=c.run(self.home,self.wallet,self.pool,prepare=True,opener=t)
        self.assertFalse(r['privateKeyAccessed']); self.assertEqual(r['state'],'prepared-not-executable')

    def test_legacy_completed_cycle_counts_without_retroactive_guard(self):
        for name in (c.submit.CHILD,c.submit.REVERSE_CHILD):
            child=self.home/name; p=child/'execution.json'; v=json.loads(p.read_text())
            del v['spendingGuardVersion']; p.write_text(json.dumps(v))
            (child/c.submit.spend_guard.MARKER).unlink()
        (self.home/c.submit.spend_guard.NAME).unlink()
        r,_=self.run_prepare()
        self.assertEqual(r['budget']['historicalSwapFeeLamports'],'10000')
        self.assertFalse(r['pretradeBudgetEnforced'])

    def test_open_prior_cycle_blocks_before_rpc_or_directory(self):
        shutil.rmtree(self.home/c.submit.REVERSE_CHILD)
        with self.assertRaisesRegex(ValueError,'prior-round-trip-not-closed'):
            c.run(self.home,self.wallet,self.pool,prepare=True)
        self.assertFalse((self.home/c.CYCLE).exists())

    def test_wrong_chain_rejected_before_any_receipt_or_registration(self):
        t=Transport(self.home,self.wallet,lambda q,v:c.GENESIS['mainnet-beta'])
        with self.assertRaisesRegex(ValueError,'wrong-cluster'):
            c.run(self.home,self.wallet,self.pool,prepare=True,opener=t)
        self.assertEqual(len(t.calls),1); self.assertFalse((self.home/c.CYCLE).exists())

    def test_unavailable_finality_and_changed_receipt_fail_before_registration(self):
        for change in (lambda q,v:dict(context={'slot':140},value=[None]) if q['method']=='getSignatureStatuses' else v,
                       lambda q,v:None if q['method']=='getTransaction' else v,
                       lambda q,v:dict(v,slot=999) if q['method']=='getTransaction' else v):
            with self.assertRaises(ValueError): self.run_prepare(change)
            self.assertFalse((self.home/c.CYCLE).exists())

    def test_changed_wallet_or_token_or_authority_is_not_silently_rebased(self):
        for kind in ('wallet','token','delegate'):
            def change(q,v):
                if q['method']=='getMultipleAccounts':
                    if kind=='wallet':v['value'][0]['lamports']+=1
                    else:
                        row=v['value'][1];raw=bytearray(base64.b64decode(row['data'][0]))
                        if kind=='token':raw[64:72]=(12345).to_bytes(8,'little')
                        else:raw[72:76]=(1).to_bytes(4,'little');raw[76:108]=bytes([7])*32
                        row['data'][0]=base64.b64encode(raw).decode()
                return v
            with self.subTest(kind=kind),self.assertRaises(ValueError): self.run_prepare(change)
            self.assertFalse((self.home/c.CYCLE).exists())

    def test_snapshot_slot_regression_rejected(self):
        with self.assertRaisesRegex(ValueError,'rpc-context-regressed'):
            self.run_prepare(lambda q,v:dict(v,context={'slot':129}) if q['method']=='getMultipleAccounts' else v)

    def test_stale_or_regressed_local_receipt_time_rejected(self):
        for times in ((100000,110001),(100000,99999),(100000,100000,110001)):
            with self.subTest(times=times),self.assertRaisesRegex(ValueError,'balance-observation-expired'):
                self.run_prepare(now=iter(times).__next__)
            self.assertFalse((self.home/c.CYCLE).exists())

    def test_stop_before_or_during_capture_prevents_creation(self):
        marker=self.home/'STOP';marker.touch();marker.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'stop-requested'):self.run_prepare()
        marker.unlink()
        def change(q,v):
            if q['method']=='getMultipleAccounts':marker.touch();marker.chmod(0o600)
            return v
        with self.assertRaisesRegex(ValueError,'stop-requested'):self.run_prepare(change)
        self.assertFalse((self.home/c.CYCLE).exists())

    def test_interruption_never_overwrites_or_repeats_preparation(self):
        write=c.write_new
        def crash(path,value):
            if path.name=='complete.json':raise KeyboardInterrupt('power loss')
            write(path,value)
        with patch.object(c,'write_new',side_effect=crash),self.assertRaises(KeyboardInterrupt):self.run_prepare()
        before=(self.home/c.CYCLE/'preparation.json').read_bytes()
        t=Transport(self.home,self.wallet)
        r=c.run(self.home,self.wallet,self.pool,prepare=True,opener=t)
        self.assertEqual(r['state'],'preparation-incomplete');self.assertEqual(t.calls,[])
        self.assertEqual((self.home/c.CYCLE/'preparation.json').read_bytes(),before)

    def test_malformed_or_changed_preparation_cannot_become_an_execution_permission(self):
        self.run_prepare();path=self.home/c.CYCLE/'preparation.json';original=path.read_bytes()
        for key,value in [('wallet',fake_key('other')),('policy',{}),('budget',{})]:
            v=json.loads(original);v[key]=value;path.write_text(json.dumps(v))
            with self.assertRaises(ValueError):c.run(self.home,self.wallet,self.pool)
        path.write_bytes(original);seal=self.home/c.CYCLE/'complete.json';seal.write_text('{}')
        with self.assertRaisesRegex(ValueError,'cycle-seal-mismatch'):c.run(self.home,self.wallet,self.pool)

    def test_cumulative_caps_do_not_reset_on_returned_tokens_or_calendar(self):
        source,allocation=c.local(self.home,self.wallet,self.pool)
        p=source['position']; p['returnedOriginalAtomic']='999999'; p['netOriginalTokenAtomic']='998999'
        self.assertEqual(c.budget(p)['cumulativeEntryWithAllocationAtomic'],'2000')
        for policy in (dict(c.POLICY,maximumCycles=1), dict(c.POLICY,maximumCumulativeEntryAtomic='1999'),
                       dict(c.POLICY,maximumCumulativeSwapFeeLamports='29999')):
            with patch.object(c,'POLICY',policy),self.assertRaisesRegex(ValueError,'cumulative-budget-exceeded'):c.budget(p)

    def test_existing_accounting_must_match_and_is_never_mutated(self):
        c.controlled.sync(self.home,self.wallet,self.pool);before=self.old_files()
        self.run_prepare();self.assertEqual(before,self.old_files())
        ledger=c.controlled.Ledger(self.home,create=False)
        try:ledger.apply(source_error=True)
        finally:ledger.close()
        with self.assertRaisesRegex(ValueError,'historical-ledger-not-reconciled'):c.run(self.home,self.wallet,self.pool)

    def test_shared_lock_wrong_identity_and_unsafe_paths_refuse(self):
        with c.controlled.source_lock(self.home,self.wallet),self.assertRaises(BlockingIOError):
            c.run(self.home,self.wallet,self.pool,prepare=True)
        with self.assertRaises(ValueError):c.run(self.home,fake_key('wrong'),self.pool)
        (self.home/c.CYCLE).symlink_to(self.home)
        with self.assertRaises(ValueError):c.run(self.home,self.wallet,self.pool)

    def test_rpc_allowlist_and_request_cap_exclude_send_sign_and_retry(self):
        rpc=c.ReadRpc('devnet',Transport(self.home,self.wallet))
        for name in ('sendTransaction','simulateTransaction','requestAirdrop'):
            with self.assertRaisesRegex(ValueError,'method not allowed'):rpc.request(name,[])
        for _ in range(7):rpc.request('getGenesisHash',[])
        with self.assertRaisesRegex(ValueError,'request cap'):rpc.request('getGenesisHash',[])

    def test_record_cap_prevents_partial_directory_creation(self):
        with patch.object(c,'LIMIT',1),self.assertRaisesRegex(ValueError,'cycle-record-size-cap'):self.run_prepare()
        self.assertFalse((self.home/c.CYCLE).exists())
