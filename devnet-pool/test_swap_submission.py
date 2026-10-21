import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import urllib.error
import test_controlled_swap as fixture
import swap_submission as submit
from core import write_new
from pool_fixtures import fake_key, Response
from swap_rehearsal_fixtures import simulation


class Transport(fixture.SwapTransport):
    def __init__(self, home, change=None, *, pending=False, failure=False, lost_ack=False):
        super().__init__(home, change)
        self.sent = False; self.simulated = False
        self.pending = pending; self.failure = failure; self.lost_ack = lost_ack
        self.old = json.loads((home / fixture.swap.CHILD / 'plan.json').read_text())['packet']['policy']['blockhash']
    def signature(self):
        wallet = fixture.pool.read(self.home / fixture.pool.CHILD, 'plan.json')['pairAccounts']['wallet']
        return submit.bound(self.home / submit.CHILD, wallet)[2]['signatures'][0]
    def tx(self):
        child = self.home / submit.CHILD
        wire = submit.read(child, 'signed.json')['wire']
        v = simulation(submit.read(child, 'presend-preflight.json', 4 * 1024 * 1024))['value']
        err = {'InstructionError': [2, {'Custom': 1}]} if self.failure else None
        if self.failure: v['postTokenBalances'] = copy.deepcopy(v['preTokenBalances'])
        return dict(slot=110, version='legacy', transaction=[wire, 'base64'], meta=dict(
            err=err, fee=v['fee'], preBalances=v['preBalances'], postBalances=v['postBalances'],
            preTokenBalances=v['preTokenBalances'], postTokenBalances=v['postTokenBalances'],
            loadedAddresses=dict(writable=[], readonly=[])))
    def open(self, request, timeout=None):
        q = json.loads(request.data); method = q['method']
        if method not in ('getLatestBlockhash', 'getFeeForMessage', 'getMultipleAccounts', 'isBlockhashValid',
                          'simulateTransaction', 'sendTransaction', 'getSignatureStatuses', 'getTransaction', 'getBlockHeight'):
            return super().open(request, timeout)
        self.calls.append(q)
        assert request.full_url == 'https://api.devnet.solana.com'
        slot = 110 if self.simulated else 108
        if method == 'getLatestBlockhash':
            value = dict(context={'slot': slot}, value=dict(blockhash=fake_key('execution-fresh-hash'), lastValidBlockHeight=2000))
        elif method == 'getFeeForMessage': value = dict(context={'slot': slot}, value=5000)
        elif method == 'getMultipleAccounts':
            value = dict(context={'slot': slot}, value=[copy.deepcopy(self.rows[k]) for k in q['params'][0]])
        elif method == 'isBlockhashValid': value = dict(context={'slot': slot}, value=q['params'][0] != self.old)
        elif method == 'getBlockHeight': value = 1100
        elif method == 'simulateTransaction':
            value = simulation(submit.read(self.home / submit.CHILD, 'preflight.json', 4 * 1024 * 1024))
            value['context']['slot'] = 109; self.simulated = True
        elif method == 'sendTransaction':
            assert (self.home / submit.CHILD / 'submission-boundary.json').exists()
            assert q['params'][1]['maxRetries'] == 0 and q['params'][1]['skipPreflight'] is False
            self.sent = True
            if self.lost_ack: raise urllib.error.URLError('synthetic lost acknowledgement')
            value = self.signature()
        elif method == 'getSignatureStatuses':
            row = None
            if self.sent and not self.pending and q['params'][0][0] == self.signature():
                row = dict(slot=110, confirmationStatus='finalized', confirmations=None, err=self.tx()['meta']['err'])
            value = dict(context={'slot': 111}, value=[row])
        else: value = self.tx() if self.sent and q['params'][0] == self.signature() else None
        if self.change: value = self.change(q, value)
        return Response(json.dumps(dict(jsonrpc='2.0', id=q['id'], result=value)).encode())


class SwapSubmissionCase(unittest.TestCase):
    setUpClass = classmethod(fixture.ControlledSwapCase.setUpClass.__func__)
    tearDownClass = classmethod(fixture.ControlledSwapCase.tearDownClass.__func__)
    setUp = fixture.ControlledSwapCase.setUp
    tearDown = fixture.ControlledSwapCase.tearDown
    def prepare(self):
        r = fixture.bridge.simulate(self.home, self.wallet, self.pool, opener=fixture.SwapTransport(self.home))
        self.assertEqual(r['state'], 'signed-simulation-consistent', r)
    def run_swap(self, **kwargs):
        self.prepare(); t = Transport(self.home, **kwargs)
        return submit.execute(self.home, self.wallet, self.pool, opener=t, sleeper=lambda _: None), t
    def sends(self, t): return sum(q['method'] == 'sendTransaction' for q in t.calls)
    def test_one_send_finalized_exact_accounting_and_old_journal_unchanged(self):
        self.prepare(); old = self.home / fixture.swap.CHILD
        before = {p.name: p.read_bytes() for p in old.iterdir()}; t = Transport(self.home)
        r = submit.execute(self.home, self.wallet, self.pool, opener=t, sleeper=lambda _: None)
        self.assertEqual(r['state'], 'finalized-success', r)
        self.assertEqual(r['networkRequests'], len(t.calls)); self.assertEqual(r['sendRequestsThisRun'], 1)
        self.assertEqual(r['signaturesCreatedThisRun'], 1); self.assertTrue(r['submissionBoundaryRecorded'])
        receipt = r['observation']['receipt']
        self.assertEqual(receipt['inputAtomic'], '1000'); self.assertEqual(receipt['outputAtomic'], '990')
        self.assertEqual(receipt['feeLamports'], '5000')
        self.assertEqual(receipt['tokenEffects']['source']['deltaAtomic'], '-1000')
        self.assertEqual(before, {p.name: p.read_bytes() for p in old.iterdir()})
        self.assertNotIn(submit.read(self.home / submit.CHILD, 'signed.json')['wire'], json.dumps(r))
    def test_repeat_and_terminal_recovery_have_zero_rpc_and_no_signature(self):
        r, t = self.run_swap(); self.assertEqual(r['state'], 'finalized-success', r); t.calls.clear()
        for f in (lambda: submit.execute(self.home, self.wallet, self.pool, opener=t),
                  lambda: submit.recover(self.home, self.wallet, opener=t), lambda: submit.status(self.home, self.wallet)):
            r = f(); self.assertEqual(r['state'], 'finalized-success'); self.assertEqual(r['signaturesCreatedThisRun'], 0)
            self.assertEqual(r['sendRequestsThisRun'], 0)
        self.assertEqual(t.calls, [])
    def test_missing_prior_simulation_refuses_before_rpc(self):
        t = fixture.SwapTransport(self.home)
        with self.assertRaises((ValueError, OSError)): submit.execute(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(t.calls, [])
    def test_wrong_wallet_and_pool_refuse(self):
        self.prepare(); t = Transport(self.home)
        for wallet, pool in [(fake_key('wallet'), self.pool), (self.wallet, fake_key('pool'))]:
            with self.assertRaises(ValueError): submit.execute(self.home, wallet, pool, opener=t)
        self.assertEqual(t.calls, [])
    def test_old_blockhash_must_expire(self):
        self.prepare()
        def change(q, v):
            if q['method'] == 'isBlockhashValid': v['value'] = True
            return v
        t = Transport(self.home, change)
        with self.assertRaises(ValueError): submit.execute(self.home, self.wallet, self.pool, opener=t)
        self.assertFalse((self.home / submit.CHILD).exists()); self.assertEqual(self.sends(t), 0)
    def test_old_signature_observed_refuses_new_signing(self):
        self.prepare()
        def change(q, v):
            if q['method'] == 'getSignatureStatuses': v['value'] = [dict(slot=108, confirmationStatus='finalized', confirmations=None, err=None)]
            return v
        t = Transport(self.home, change)
        with self.assertRaises(ValueError): submit.execute(self.home, self.wallet, self.pool, opener=t)
        self.assertFalse((self.home / submit.CHILD).exists())
    def test_prior_review_tampering_refused(self):
        self.prepare(); p = self.home / fixture.swap.CHILD / 'simulation-review.json'
        v = json.loads(p.read_text()); v['simulatedOutputAtomic'] = '100000'; p.write_text(json.dumps(v)); t = Transport(self.home)
        with self.assertRaises(ValueError): submit.execute(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(t.calls, [])
    def test_failed_transaction_reconciles_fee_only(self):
        r, t = self.run_swap(failure=True); self.assertEqual(r['state'], 'finalized-failure', r)
        self.assertEqual(r['observation']['receipt']['inputAtomic'], '0')
        self.assertTrue(all(v['deltaAtomic'] == '0' for v in r['observation']['receipt']['tokenEffects'].values()))
        self.assertEqual(self.sends(t), 1)
    def test_send_timeout_after_landing_recovers_without_resend(self):
        r, t = self.run_swap(lost_ack=True); self.assertEqual(r['state'], 'finalized-success', r); self.assertEqual(self.sends(t), 1)
    def test_unexpected_send_ack_never_changes_observed_signature(self):
        r, t = self.run_swap(change=lambda q, v: 'untrusted-signature' if q['method'] == 'sendTransaction' else v)
        self.assertEqual(r['state'], 'finalized-success', r)
        self.assertFalse(submit.read(self.home / submit.CHILD, 'send-observation.json')['expectedSignatureAcknowledged'])
        self.assertEqual(self.sends(t), 1)
    def test_pending_recovers_read_only_and_stop_does_not_block_observation(self):
        r, t = self.run_swap(pending=True); self.assertEqual(r['state'], 'submission-unknown', r)
        t.pending = False; t.calls.clear(); (self.home / 'STOP').write_text('stop')
        r = submit.recover(self.home, self.wallet, opener=t, sleeper=lambda _: None)
        self.assertEqual(r['state'], 'finalized-success', r); self.assertEqual(r['sendRequestsThisRun'], 0)
        self.assertTrue(all(q['method'] in submit.RecoveryRpc.METHODS for q in t.calls))
    def test_missing_receipt_remains_unknown_and_can_recover(self):
        r, t = self.run_swap(change=lambda q, v: None if q['method'] == 'getTransaction' else v)
        self.assertEqual(r['state'], 'submission-unknown', r); t.change = None; t.calls.clear()
        self.assertEqual(submit.recover(self.home, self.wallet, opener=t, sleeper=lambda _: None)['state'], 'finalized-success')
        self.assertEqual(self.sends(t), 0)
    def test_missing_token_balances_remain_unknown(self):
        def change(q, v):
            if q['method'] == 'getTransaction' and v: del v['meta']['postTokenBalances']
            return v
        r, t = self.run_swap(change=change); self.assertEqual(r['state'], 'submission-unknown', r); self.assertEqual(self.sends(t), 1)
    def test_wrong_wire_quarantined_and_terminal(self):
        def change(q, v):
            if q['method'] == 'getTransaction' and v: v['transaction'][0] = 'wrong'
            return v
        r, t = self.run_swap(change=change); self.assertEqual(r['state'], 'quarantined', r); t.calls.clear()
        self.assertEqual(submit.recover(self.home, self.wallet, opener=t)['state'], 'quarantined'); self.assertEqual(t.calls, [])
    def test_nonfee_native_effect_quarantined(self):
        def change(q, v):
            if q['method'] == 'getTransaction' and v: v['meta']['postBalances'][1] += 1
            return v
        r, _ = self.run_swap(change=change); self.assertEqual(r['state'], 'quarantined', r)
    def test_wrong_token_amount_quarantined(self):
        def change(q, v):
            if q['method'] == 'getTransaction' and v: v['meta']['postTokenBalances'][1]['uiTokenAmount']['amount'] = '1'
            return v
        r, _ = self.run_swap(change=change); self.assertEqual(r['state'], 'quarantined', r)
    def test_wrong_token_owner_quarantined(self):
        def change(q, v):
            if q['method'] == 'getTransaction' and v: v['meta']['postTokenBalances'][0]['owner'] = fake_key('wrong-owner')
            return v
        r, _ = self.run_swap(change=change); self.assertEqual(r['state'], 'quarantined', r)
    def test_simulation_failure_never_crosses_send_boundary(self):
        def change(q, v):
            if q['method'] == 'simulateTransaction': v['value']['err'] = {'InstructionError': [2, 'invalid']}
            return v
        r, t = self.run_swap(change=change); self.assertEqual(r['state'], 'preparation-incomplete', r)
        self.assertFalse(r['submissionBoundaryRecorded']); self.assertEqual(self.sends(t), 0)
    def test_presend_account_drift_blocks_send(self):
        def change(q, v):
            if q['method'] == 'getMultipleAccounts' and len(q['params'][0]) == 12 and t.simulated: v['value'][8]['lamports'] += 1
            return v
        self.prepare(); t = Transport(self.home, change)
        r = submit.execute(self.home, self.wallet, self.pool, opener=t, sleeper=lambda _: None)
        self.assertEqual(r['failure']['phase'], 'presend-preflight', r)
        self.assertFalse(r['submissionBoundaryRecorded']); self.assertEqual(self.sends(t), 0)
    def test_near_expiry_blocks_send(self):
        r, t = self.run_swap(change=lambda q, v: 1995 if q['method'] == 'getBlockHeight' else v)
        self.assertFalse(r['submissionBoundaryRecorded'], r); self.assertEqual(self.sends(t), 0)
    def test_stop_before_start_has_no_rpc(self):
        (self.home / 'STOP').write_text('stop'); t = fixture.SwapTransport(self.home)
        with self.assertRaises(ValueError): submit.execute(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(t.calls, [])
    def test_crash_after_boundary_before_transport_consumes_boundary(self):
        self.prepare(); t = Transport(self.home); original = submit.write_new
        def crash(path, value):
            original(path, value)
            if path.name == 'submission-boundary.json': raise KeyboardInterrupt('synthetic power loss')
        with patch.object(submit, 'write_new', side_effect=crash):
            with self.assertRaises(KeyboardInterrupt): submit.execute(self.home, self.wallet, self.pool, opener=t, sleeper=lambda _: None)
        self.assertTrue(submit.status(self.home, self.wallet)['submissionBoundaryRecorded']); self.assertEqual(self.sends(t), 0)
        t.calls.clear(); self.assertEqual(submit.execute(self.home, self.wallet, self.pool, opener=t)['state'], 'submission-unknown')
        self.assertEqual(t.calls, [])
        self.assertEqual(submit.recover(self.home, self.wallet, opener=t, sleeper=lambda _: None)['state'], 'submission-unknown')
        self.assertEqual(self.sends(t), 0)
    def test_crash_after_send_recovers_without_second_send(self):
        self.prepare(); t = Transport(self.home); original = submit.write_new
        def crash(path, value):
            if path.name == 'send-observation.json': raise KeyboardInterrupt('synthetic power loss')
            original(path, value)
        with patch.object(submit, 'write_new', side_effect=crash):
            with self.assertRaises(KeyboardInterrupt): submit.execute(self.home, self.wallet, self.pool, opener=t, sleeper=lambda _: None)
        self.assertEqual(self.sends(t), 1); t.calls.clear()
        self.assertEqual(submit.recover(self.home, self.wallet, opener=t, sleeper=lambda _: None)['state'], 'finalized-success')
        self.assertEqual(self.sends(t), 0)
    def test_stop_after_boundary_never_sends(self):
        self.prepare(); t = Transport(self.home); original = submit.write_new
        def stop(path, value):
            original(path, value)
            if path.name == 'submission-boundary.json': (self.home / 'STOP').write_text('stop')
        with patch.object(submit, 'write_new', side_effect=stop): r = submit.execute(self.home, self.wallet, self.pool, opener=t, sleeper=lambda _: None)
        self.assertTrue(r['submissionBoundaryRecorded']); self.assertEqual(self.sends(t), 0)
    def test_lost_signer_ack_preserves_signature_without_retry(self):
        self.prepare(); t = Transport(self.home); original = fixture.swap.invoke_signer
        def lost(*args, **kwargs):
            original(*args, **kwargs); raise OSError('lost acknowledgement')
        with patch.object(fixture.swap, 'invoke_signer', side_effect=lost): r = submit.execute(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(r['signaturesCreatedThisRun'], 1); self.assertFalse(r['submissionBoundaryRecorded'])
        t.calls.clear(); submit.execute(self.home, self.wallet, self.pool, opener=t); self.assertEqual(t.calls, [])
    def test_signing_attempt_without_signature_is_unknown(self):
        self.prepare(); t = Transport(self.home)
        def interrupted(home, **kwargs):
            write_new(home / submit.CHILD / 'signing-attempt.json', dict(interrupted=True)); raise OSError('interrupted')
        with patch.object(fixture.swap, 'invoke_signer', side_effect=interrupted): r = submit.execute(self.home, self.wallet, self.pool, opener=t)
        self.assertTrue(r['signatureOutcomeUnknown']); self.assertIsNone(r['signaturesCreatedThisRun']); self.assertEqual(self.sends(t), 0)
    def test_empty_journal_never_reused(self):
        (self.home / submit.CHILD).mkdir(mode=0o700); t = fixture.SwapTransport(self.home)
        r = submit.execute(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(r['state'], 'preparation-incomplete'); self.assertEqual(t.calls, [])
        self.assertEqual(submit.recover(self.home, self.wallet, opener=t)['networkRequests'], 0)
    def test_recovery_rpc_disallows_send_and_simulate(self):
        rpc = submit.RecoveryRpc()
        for method in ('sendTransaction', 'simulateTransaction', 'requestAirdrop'):
            with self.assertRaises(ValueError): rpc.request(method, [])
        self.assertEqual(rpc.calls, [])
    def test_receipt_mutation_matrix_fails_closed(self):
        r, t = self.run_swap(); self.assertEqual(r['state'], 'finalized-success', r)
        child = self.home / submit.CHILD
        plan, wire, signed, _ = submit.bound(child, self.wallet)
        capture = submit.read(child, 'presend-preflight.json', 4 * 1024 * 1024)
        st = dict(slot=110, confirmationStatus='finalized', confirmations=None, err=None)
        mutations = [
            lambda tx: tx['meta'].update(fee=10000),
            lambda tx: tx.update(version=0),
            lambda tx: tx.update(slot=109),
            lambda tx: tx['meta'].update(loadedAddresses=dict(writable=[fake_key('alt')], readonly=[])),
            lambda tx: tx['meta']['postTokenBalances'][0].update(accountIndex=99),
            lambda tx: tx['meta']['postTokenBalances'][0].update(mint=fake_key('mint')),
            lambda tx: tx['meta']['postTokenBalances'][0].update(programId=fake_key('program')),
            lambda tx: tx['meta']['postTokenBalances'][0]['uiTokenAmount'].update(decimals=9),
            lambda tx: tx['meta']['postTokenBalances'][0]['uiTokenAmount'].update(amount='01'),
            lambda tx: tx['meta']['postTokenBalances'][0].update(accountIndex=tx['meta']['postTokenBalances'][1]['accountIndex']),
            lambda tx: tx['meta'].update(err={'InstructionError': [2, 'failed']}),
        ]
        for i, mutation in enumerate(mutations):
            tx = t.tx(); mutation(tx)
            with self.subTest(case=i), self.assertRaises(ValueError):
                submit.receipt(tx, st, plan, wire, signed, capture)
    def test_terminal_receipt_replay_detects_stored_summary_tampering(self):
        r, t = self.run_swap(); self.assertEqual(r['state'], 'finalized-success', r)
        p = self.home / submit.CHILD / 'observation-000.json'
        value = json.loads(p.read_text()); value['receipt']['outputAtomic'] = '999999'; p.write_text(json.dumps(value))
        t.calls.clear()
        with self.assertRaises(ValueError): submit.recover(self.home, self.wallet, opener=t)
        self.assertEqual(t.calls, [])
    def test_actual_output_can_differ_from_simulation_above_fixed_minimum(self):
        def change(q, v):
            if q['method'] == 'getTransaction' and v:
                rows = v['meta']['postTokenBalances']
                rows[1]['uiTokenAmount']['amount'] = str(int(rows[1]['uiTokenAmount']['amount']) + 8)
                rows[3]['uiTokenAmount']['amount'] = str(int(rows[3]['uiTokenAmount']['amount']) - 8)
            return v
        r, _ = self.run_swap(change=change)
        self.assertEqual(r['state'], 'finalized-success', r)
        self.assertEqual(r['simulation']['simulatedOutputAtomic'], '990')
        self.assertEqual(r['observation']['receipt']['outputAtomic'], '998')
    def test_expiry_after_boundary_consumes_attempt_without_sending(self):
        self.prepare(); t = Transport(self.home); original = submit.write_new
        expires = [None]
        clock = submit.now
        def write(path, value):
            original(path, value)
            if path.name == 'submission-boundary.json':
                expires[0] = submit.read(path.parent, 'plan.json')['packet']['policy']['expiresAtMs']
        with patch.object(submit, 'write_new', side_effect=write), patch.object(submit, 'now', side_effect=lambda: expires[0] or clock()):
            r = submit.execute(self.home, self.wallet, self.pool, opener=t, sleeper=lambda _: None)
        self.assertTrue(r['submissionBoundaryRecorded']); self.assertEqual(self.sends(t), 0)
    def test_recovery_expired_unknown_does_not_infer_no_fill_or_retry(self):
        r, t = self.run_swap(pending=True); self.assertEqual(r['state'], 'submission-unknown', r)
        t.change = lambda q, v: 2001 if q['method'] == 'getBlockHeight' else v
        t.calls.clear()
        r = submit.recover(self.home, self.wallet, opener=t, sleeper=lambda _: None)
        self.assertEqual(r['state'], 'expired-outcome-unknown'); self.assertEqual(self.sends(t), 0)
    def test_restricted_signer_rejects_changed_fixed_policy_and_unknown_purpose(self):
        self.prepare(); t = Transport(self.home); original = fixture.swap.invoke_signer
        def altered(home, **kwargs):
            child = home / submit.CHILD
            plan = submit.read(child, 'plan.json'); plan['scope']['minimumAmountOut'] = '1'
            plan['packet']['policy']['minimumAmountOut'] = '1'
            (child / 'plan.json').write_text(json.dumps(plan))
            request = submit.read(child, 'signing-request.json'); request['planSha256'] = fixture.pool.digest(plan)
            (child / 'signing-request.json').write_text(json.dumps(request))
            original(home, **kwargs)
        with patch.object(fixture.swap, 'invoke_signer', side_effect=altered):
            r = submit.execute(self.home, self.wallet, self.pool, opener=t)
        self.assertFalse((self.home / submit.CHILD / 'signing-attempt.json').exists())
        self.assertEqual(self.sends(t), 0)
        signer = Path(fixture.swap.__file__).with_name('swap_signer.mjs')
        result = subprocess.run(['node', str(signer)], input=json.dumps(dict(directory=str(self.home), purpose='arbitrary')),
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
    def test_cli_requires_explicit_flag_and_pool(self):
        cli = Path(__file__).with_name('swap_submit_cli.py')
        for args in (['--action', 'execute'], ['--action', 'recover', '--allow-devnet-submit'], ['--action', 'simulate']):
            r = subprocess.run([sys.executable, str(cli), *args, '--output', str(self.home / 'report.json.gz')], capture_output=True)
            self.assertNotEqual(r.returncode, 0); self.assertFalse((self.home / submit.CHILD).exists())


if __name__ == '__main__': unittest.main()
