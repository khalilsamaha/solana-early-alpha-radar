"""Disposable wallets, synthetic RPC, real restricted signer and receipt reconciliation."""
import base64
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import urllib.error
import test_controlled_swap as setup
import test_swap_submission as forward
import swap_submission as submit
from pool_fixtures import Response, fake_key, BASE
from swap_rehearsal_fixtures import simulation


def output_change(tx, quantity):
    m = tx['meta']
    for index, delta in ((1, quantity), (3, -quantity)):
        m['postTokenBalances'][index]['uiTokenAmount']['amount'] = str(int(m['preTokenBalances'][index]['uiTokenAmount']['amount']) + delta)
    return tx


class ReverseTransport(setup.SwapTransport):
    def __init__(self, home, change=None, *, pending=False, failure=False, lost_ack=False):
        super().__init__(home, change)
        self.sent = False; self.simulated = False
        self.pending = pending; self.failure = failure; self.lost_ack = lost_ack
        self.original = submit.read(home / submit.CHILD, 'receipt-evidence.json', 131072)
        self.wallet = submit.read(home / submit.CHILD, 'plan.json')['scope']['accounts']['wallet']
        self.first = submit.report(home, self.wallet)['observation']['receipt']
        self.rows[self.wallet]['lamports'] = int(self.first['walletAfterLamports'])
        for effect in self.first['tokenEffects'].values():
            row = self.rows[effect['account']]
            raw = bytearray(base64.b64decode(row['data'][0]))
            raw[64:72] = int(effect['afterAtomic']).to_bytes(8, 'little')
            row['data'][0] = base64.b64encode(raw).decode()
    def signature(self):
        return submit.bound(self.home / submit.REVERSE_CHILD, self.wallet)[2]['signatures'][0]
    def tx(self):
        child = self.home / submit.REVERSE_CHILD
        v = simulation(submit.read(child, 'presend-preflight.json', 4 * 1024 * 1024))['value']
        err = {'InstructionError': [2, {'Custom': 1}]} if self.failure else None
        if self.failure: v['postTokenBalances'] = copy.deepcopy(v['preTokenBalances'])
        tx = dict(slot=130, version='legacy', transaction=[submit.read(child, 'signed.json')['wire'], 'base64'], meta=dict(
            err=err, fee=v['fee'], preBalances=v['preBalances'], postBalances=v['postBalances'],
            preTokenBalances=v['preTokenBalances'], postTokenBalances=v['postTokenBalances'],
            loadedAddresses=dict(writable=[], readonly=[])))
        return tx if self.failure else output_change(tx, 996)
    def open(self, request, timeout=None):
        q = json.loads(request.data); method = q['method']
        if method not in ('getLatestBlockhash', 'getFeeForMessage', 'getMultipleAccounts', 'isBlockhashValid',
                          'simulateTransaction', 'sendTransaction', 'getSignatureStatuses', 'getTransaction', 'getBlockHeight'):
            return super().open(request, timeout)
        self.calls.append(q)
        assert request.full_url == 'https://api.devnet.solana.com'
        slot = 124 if self.simulated else 120
        if method == 'getLatestBlockhash':
            value = dict(context={'slot': slot}, value=dict(blockhash=fake_key('reverse-blockhash'), lastValidBlockHeight=3000))
        elif method == 'getFeeForMessage': value = dict(context={'slot': slot}, value=5000)
        elif method == 'getMultipleAccounts':
            value = dict(context={'slot': slot}, value=[copy.deepcopy(self.rows[k]) for k in q['params'][0]])
        elif method == 'isBlockhashValid': value = dict(context={'slot': slot}, value=True)
        elif method == 'getBlockHeight': value = 2100
        elif method == 'simulateTransaction':
            value = simulation(submit.read(self.home / submit.REVERSE_CHILD, 'preflight.json', 4 * 1024 * 1024))
            value['context']['slot'] = 121; self.simulated = True
        elif method == 'sendTransaction':
            assert (self.home / submit.REVERSE_CHILD / 'submission-boundary.json').exists()
            assert q['params'][1]['maxRetries'] == 0 and q['params'][1]['skipPreflight'] is False
            self.sent = True
            if self.lost_ack: raise urllib.error.URLError('synthetic lost acknowledgement')
            value = self.signature()
        elif method == 'getSignatureStatuses':
            sig = q['params'][0][0]; row = None
            if sig == self.first['signature']: row = copy.deepcopy(self.original['status'])
            elif self.sent and not self.pending and sig == self.signature():
                row = dict(slot=130, confirmationStatus='finalized', confirmations=None, err=self.tx()['meta']['err'])
            value = dict(context={'slot': 132}, value=[row])
        else:
            sig = q['params'][0]
            value = copy.deepcopy(self.original['transaction']) if sig == self.first['signature'] else self.tx() if self.sent and sig == self.signature() else None
        if self.change: value = self.change(q, value)
        return Response(json.dumps(dict(jsonrpc='2.0', id=q['id'], result=value)).encode())


class ReverseCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        setup.ControlledSwapCase.setUpClass.__func__(cls)
        baseline = dict(copy.deepcopy(BASE), network='devnet', kind='observed-devnet-deployment', observedAtMs=0)
        with patch('preflight.BASELINE', baseline), patch('preflight_capture.BASELINE', baseline):
            r = setup.bridge.simulate(cls.template, cls.wallet, cls.pool, opener=setup.SwapTransport(cls.template))
            assert r['state'] == 'signed-simulation-consistent', r
            def change(q, v):
                return output_change(v, 998) if q['method'] == 'getTransaction' and v else v
            r = submit.execute(cls.template, cls.wallet, cls.pool, opener=forward.Transport(cls.template, change), sleeper=lambda _: None)
            assert r['state'] == 'finalized-success', r
            cls.entry_report = r
    tearDownClass = classmethod(setup.ControlledSwapCase.tearDownClass.__func__)
    setUp = setup.ControlledSwapCase.setUp
    tearDown = setup.ControlledSwapCase.tearDown
    def run_exit(self, **kwargs):
        t = ReverseTransport(self.home, **kwargs)
        return submit.execute_reverse(self.home, self.wallet, self.pool, opener=t, sleeper=lambda _: None), t
    def sends(self, t): return sum(q['method'] == 'sendTransaction' for q in t.calls)
    def old_files(self):
        return {(child, p.name): p.read_bytes() for child in (submit.CHILD, setup.swap.CHILD)
                for p in (self.home / child).iterdir()}
    def test_inspect_derives_full_received_quantity_and_reverses_accounts_without_rpc(self):
        r = submit.inspect_reverse(self.home, self.wallet, self.pool)
        self.assertEqual(r['state'], 'reverse-scope-ready'); self.assertEqual(r['networkRequests'], 0)
        self.assertEqual(r['scope']['amountIn'], '998'); self.assertEqual(r['scope']['minimumAmountOut'], '988')
        self.assertEqual(r['scope']['accounts']['source'], self.entry_report['scope']['accounts']['destination'])
        self.assertFalse((self.home / submit.REVERSE_CHILD).exists())
    def test_one_send_round_trip_actual_receipts_and_old_journals_unchanged(self):
        before = self.old_files(); r, t = self.run_exit()
        self.assertEqual(r['state'], 'finalized-success', r)
        self.assertEqual(r['networkRequests'], len(t.calls)); self.assertEqual(r['signaturesCreatedThisRun'], 1)
        self.assertEqual(self.sends(t), 1); self.assertEqual(r['sendRequestsThisRun'], 1)
        rt = r['roundTrip']; self.assertEqual(rt['state'], 'round-trip-reconciled')
        for k, v in dict(entryInputAtomic='1000', acquiredAtomic='998', exitInputAtomic='998', returnedOriginalAtomic='996',
                         netOriginalTokenAtomic='-4', residualAcquiredTokenAtomic='0', totalFeeLamports='10000').items():
            self.assertEqual(rt[k], v)
        self.assertFalse(rt['profitabilityClaim']); self.assertFalse(rt['productionPositionUpdated'])
        self.assertEqual(before, self.old_files())
        self.assertNotIn(submit.read(self.home / submit.REVERSE_CHILD, 'signed.json')['wire'], json.dumps(r))
    def test_repeat_terminal_recovery_status_never_sign_or_send(self):
        first, t = self.run_exit(); self.assertEqual(first['state'], 'finalized-success', first); t.calls.clear()
        for f in (lambda: submit.execute_reverse(self.home, self.wallet, self.pool, opener=t),
                  lambda: submit.recover(self.home, self.wallet, reverse=True, opener=t),
                  lambda: submit.status(self.home, self.wallet, reverse=True)):
            r = f(); self.assertEqual(r['roundTrip'], first['roundTrip'])
            self.assertEqual(r['signaturesCreatedThisRun'], 0); self.assertEqual(r['sendRequestsThisRun'], 0)
        self.assertEqual(t.calls, [])
    def test_forward_entry_remains_distinct_after_reverse(self):
        r, t = self.run_exit(); self.assertEqual(r['state'], 'finalized-success', r); t.calls.clear()
        old = submit.execute(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(old['observation']['receipt'], self.entry_report['observation']['receipt'])
        self.assertNotIn('roundTrip', old); self.assertEqual(t.calls, [])
    def test_failed_reverse_reconciles_fee_but_leaves_acquisition_open(self):
        r, t = self.run_exit(failure=True); self.assertEqual(r['state'], 'finalized-failure', r)
        rt = r['roundTrip']; self.assertEqual(rt['state'], 'exit-failed-position-open')
        self.assertEqual(rt['exitInputAtomic'], '0'); self.assertEqual(rt['residualAcquiredTokenAtomic'], '998')
        self.assertEqual(rt['netOriginalTokenAtomic'], '-1000'); self.assertEqual(rt['totalFeeLamports'], '10000')
        self.assertEqual(self.sends(t), 1)
    def test_pending_has_no_invented_accounting_then_recovers_read_only(self):
        r, t = self.run_exit(pending=True); self.assertEqual(r['state'], 'submission-unknown', r)
        self.assertNotIn('roundTrip', r); t.pending = False; t.calls.clear(); (self.home / 'STOP').write_text('stop')
        r = submit.recover(self.home, self.wallet, reverse=True, opener=t, sleeper=lambda _: None)
        self.assertEqual(r['state'], 'finalized-success', r); self.assertEqual(r['sendRequestsThisRun'], 0)
        self.assertTrue(all(q['method'] in submit.RecoveryRpc.METHODS for q in t.calls))
    def test_lost_send_ack_observes_recorded_signature_once(self):
        r, t = self.run_exit(lost_ack=True); self.assertEqual(r['state'], 'finalized-success', r); self.assertEqual(self.sends(t), 1)
    def test_wrong_wallet_or_pool_blocks_before_rpc(self):
        t = ReverseTransport(self.home)
        for wallet, pool in ((fake_key('other-wallet'), self.pool), (self.wallet, fake_key('other-pool'))):
            with self.assertRaises(ValueError): submit.execute_reverse(self.home, wallet, pool, opener=t)
        self.assertEqual(t.calls, [])
    def test_missing_original_receipt_blocks_before_rpc(self):
        t = ReverseTransport(self.home); (self.home / submit.CHILD / 'receipt-evidence.json').unlink()
        with self.assertRaises((OSError, ValueError)): submit.execute_reverse(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(t.calls, [])
    def test_nonfinalized_entry_not_accepted(self):
        t = ReverseTransport(self.home); p = self.home / submit.CHILD / 'observation-000.json'
        v = json.loads(p.read_text()); v['state'] = 'submission-unknown'; p.write_text(json.dumps(v))
        with self.assertRaises(ValueError): submit.execute_reverse(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(t.calls, [])
    def test_tampered_entry_summary_not_accepted(self):
        t = ReverseTransport(self.home); p = self.home / submit.CHILD / 'observation-000.json'
        v = json.loads(p.read_text()); v['receipt']['outputAtomic'] = '999'; p.write_text(json.dumps(v))
        with self.assertRaises(ValueError): submit.execute_reverse(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(t.calls, [])
    def test_current_entry_receipt_unavailable_does_not_create_reverse_journal(self):
        t = ReverseTransport(self.home, lambda q, v: None if q['method'] == 'getTransaction' else v)
        with self.assertRaises(ValueError): submit.execute_reverse(self.home, self.wallet, self.pool, opener=t)
        self.assertFalse((self.home / submit.REVERSE_CHILD).exists()); self.assertEqual(self.sends(t), 0)
    def test_unrelated_native_activity_blocks_before_signing(self):
        t = ReverseTransport(self.home); t.rows[self.wallet]['lamports'] += 1
        r = submit.execute_reverse(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(r['failure']['phase'], 'entry-to-exit-continuity', r)
        self.assertEqual(r['signaturesCreatedThisRun'], 0); self.assertEqual(self.sends(t), 0)
    def test_unrelated_token_activity_blocks_before_signing(self):
        t = ReverseTransport(self.home); row = t.rows[self.entry_report['scope']['accounts']['destination']]
        raw = bytearray(base64.b64decode(row['data'][0])); raw[64:72] = (500000999).to_bytes(8, 'little'); row['data'][0] = base64.b64encode(raw).decode()
        r = submit.execute_reverse(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(r['failure']['phase'], 'entry-to-exit-continuity', r); self.assertEqual(self.sends(t), 0)
    def test_reverse_below_minimum_is_quarantined(self):
        def change(q, v):
            return output_change(v, 987) if q['method'] == 'getTransaction' and v and v['slot'] == 130 else v
        r, t = self.run_exit(change=change)
        self.assertEqual(r['state'], 'quarantined', r); self.assertNotIn('roundTrip', r); self.assertEqual(self.sends(t), 1)
    def test_stop_before_execution_has_no_rpc(self):
        (self.home / 'STOP').write_text('stop'); t = ReverseTransport(self.home)
        with self.assertRaises(ValueError): submit.execute_reverse(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(t.calls, []); self.assertEqual(submit.inspect_reverse(self.home, self.wallet, self.pool)['state'], 'stopped')
    def test_crash_after_boundary_does_not_allow_resend(self):
        t = ReverseTransport(self.home); original = submit.write_new
        def crash(path, value):
            original(path, value)
            if path.name == 'submission-boundary.json': raise KeyboardInterrupt('synthetic power loss')
        with patch.object(submit, 'write_new', side_effect=crash):
            with self.assertRaises(KeyboardInterrupt): submit.execute_reverse(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(self.sends(t), 0); t.calls.clear()
        r = submit.execute_reverse(self.home, self.wallet, self.pool, opener=t)
        self.assertTrue(r['submissionBoundaryRecorded']); self.assertEqual(t.calls, [])
    def test_crash_after_send_recovers_without_second_send(self):
        t = ReverseTransport(self.home); original = submit.write_new
        def crash(path, value):
            if path.name == 'send-observation.json': raise KeyboardInterrupt('synthetic power loss')
            original(path, value)
        with patch.object(submit, 'write_new', side_effect=crash):
            with self.assertRaises(KeyboardInterrupt): submit.execute_reverse(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(self.sends(t), 1); t.calls.clear()
        r = submit.recover(self.home, self.wallet, reverse=True, opener=t, sleeper=lambda _: None)
        self.assertEqual(r['state'], 'finalized-success', r); self.assertEqual(self.sends(t), 0)
    def test_empty_reverse_journal_is_never_reused(self):
        (self.home / submit.REVERSE_CHILD).mkdir(mode=0o700); t = ReverseTransport(self.home)
        r = submit.execute_reverse(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(r['state'], 'preparation-incomplete'); self.assertEqual(t.calls, [])
    def test_interrupted_signing_marker_remains_unknown(self):
        t = ReverseTransport(self.home)
        def interrupted(home, **kwargs):
            submit.write_new(home / submit.REVERSE_CHILD / 'signing-attempt.json', dict(interrupted=True)); raise OSError('interrupted')
        with patch.object(setup.swap, 'invoke_signer', side_effect=interrupted):
            r = submit.execute_reverse(self.home, self.wallet, self.pool, opener=t)
        self.assertTrue(r['signatureOutcomeUnknown']); self.assertIsNone(r['signaturesCreatedThisRun']); self.assertEqual(self.sends(t), 0)
    def test_node_policy_independently_checks_entry_signature_and_exact_receipt(self):
        child = self.home / submit.CHILD
        args = [setup.pool.read(self.home / setup.pool.CHILD, 'plan.json')['pairAccounts'], submit.read(child, 'plan.json'),
                submit.read(child, 'signed.json')['wire'], submit.read(child, 'receipt-evidence.json', 131072)]
        module = Path(__file__).with_name('reverse_policy.mjs').as_uri()
        js = "import {deriveReverse} from '" + module + "'; import fs from 'node:fs'; console.log(JSON.stringify(deriveReverse(...JSON.parse(fs.readFileSync(0,'utf8')))));"
        def run(v): return subprocess.run(['node', '--input-type=module', '-e', js], input=json.dumps(v), text=True, capture_output=True)
        r = run(args); self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(json.loads(r.stdout)['amountIn'], '998')
        altered = copy.deepcopy(args); wire = bytearray(base64.b64decode(altered[2])); wire[1] ^= 1; altered[2] = base64.b64encode(wire).decode()
        self.assertNotEqual(run(altered).returncode, 0)
        altered = copy.deepcopy(args); altered[3]['transaction']['meta']['postTokenBalances'][1]['uiTokenAmount']['amount'] = '1'
        self.assertNotEqual(run(altered).returncode, 0)
    def test_round_trip_mutations_fail_closed(self):
        r, _ = self.run_exit(); self.assertEqual(r['state'], 'finalized-success', r)
        first = self.entry_report['observation']['receipt']; end = r['observation']['receipt']
        mutations = [lambda v: v.update(inputAtomic='997'), lambda v: v.update(walletBeforeLamports='1'),
                     lambda v: v['tokenEffects']['source'].update(beforeAtomic='1'),
                     lambda v: v.update(signature=first['signature']), lambda v: v.update(feeLamports='1')]
        for mutation in mutations:
            v = copy.deepcopy(end); mutation(v)
            with self.assertRaises(ValueError): submit.round_trip(first, v)
    def test_restricted_signer_rejects_oversell_even_with_rehashed_plan(self):
        t = ReverseTransport(self.home); original = setup.swap.invoke_signer
        def altered(home, **kwargs):
            child = home / submit.REVERSE_CHILD
            plan = submit.read(child, 'plan.json'); plan['scope']['amountIn'] = '1000'
            plan['packet']['policy']['amountIn'] = '1000'
            (child / 'plan.json').write_text(json.dumps(plan))
            request = submit.read(child, 'signing-request.json'); request['planSha256'] = setup.pool.digest(plan)
            (child / 'signing-request.json').write_text(json.dumps(request))
            original(home, **kwargs)
        with patch.object(setup.swap, 'invoke_signer', side_effect=altered):
            r = submit.execute_reverse(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(r['failure']['phase'], 'signing', r)
        self.assertFalse((self.home / submit.REVERSE_CHILD / 'signing-attempt.json').exists()); self.assertEqual(self.sends(t), 0)
    def test_presend_drift_does_not_cross_boundary(self):
        t = ReverseTransport(self.home)
        def change(q, v):
            if q['method'] == 'getMultipleAccounts' and len(q['params'][0]) == 12 and t.simulated:
                v['value'][8]['lamports'] += 1
            return v
        t.change = change
        r = submit.execute_reverse(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(r['failure']['phase'], 'presend-preflight', r)
        self.assertFalse(r['submissionBoundaryRecorded']); self.assertEqual(self.sends(t), 0)
    def test_terminal_reverse_receipt_summary_is_replayed_not_trusted(self):
        r, t = self.run_exit(); self.assertEqual(r['state'], 'finalized-success', r)
        path = self.home / submit.REVERSE_CHILD / 'observation-000.json'
        value = json.loads(path.read_text()); value['receipt']['outputAtomic'] = '1001'; path.write_text(json.dumps(value))
        t.calls.clear()
        with self.assertRaises(ValueError): submit.recover(self.home, self.wallet, reverse=True, opener=t)
        self.assertEqual(t.calls, [])
    def test_missing_reverse_receipt_stays_unknown_until_observed(self):
        def change(q, v):
            return None if q['method'] == 'getTransaction' and v and v['slot'] == 130 else v
        r, t = self.run_exit(change=change)
        self.assertEqual(r['state'], 'submission-unknown', r); self.assertNotIn('roundTrip', r)
        t.change = None; t.calls.clear()
        r = submit.recover(self.home, self.wallet, reverse=True, opener=t, sleeper=lambda _: None)
        self.assertEqual(r['roundTrip']['state'], 'round-trip-reconciled'); self.assertEqual(self.sends(t), 0)
    def test_cli_rejects_implicit_submission_and_custom_amount(self):
        cli = Path(__file__).with_name('reverse_cli.py')
        for args in (['--action', 'execute'], ['--action', 'recover', '--allow-devnet-submit'], ['--amount', '999']):
            r = subprocess.run([sys.executable, str(cli), *args, '--output', str(self.home / 'report.json.gz')], capture_output=True)
            self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.home / submit.REVERSE_CHILD).exists())


if __name__ == '__main__': unittest.main()
