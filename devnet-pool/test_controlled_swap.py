import base64
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import controlled_swap as bridge
import pool_workflow as pool
import swap_rehearsal as swap
from core import initialize, Session, write_new
from pool_contract import ROLES, PROGRAM, addresses
from pool_fixtures import Transport as PoolTransport, BASE, DEPLOY_ROW, POINTER, Response, fake_key
from pair_fixtures import Transport as PairTransport
from pair_workflow import execute as execute_pair
from swap_rehearsal_fixtures import simulation
from recorded_capture import GENESIS


class SwapTransport:
    """Exercise the real packet builder, account collector, signer and simulation reader."""
    def __init__(self, home, change=None):
        self.home = home
        self.calls = []
        self.change = change
        intent = pool.read(home / pool.CHILD, 'plan.json')
        last = pool.observations(home / pool.CHILD)[-1]
        self.rows = dict(zip((intent['accounts'][r] for r in ROLES), last['accountEvidence']))
        self.rows[POINTER] = copy.deepcopy(DEPLOY_ROW)
    def open(self, request, timeout=None):
        q = json.loads(request.data)
        self.calls.append(q)
        assert request.full_url == 'https://api.devnet.solana.com'
        method = q['method']
        if method == 'getGenesisHash':
            value = GENESIS['devnet']
        elif method == 'getLatestBlockhash':
            value = dict(context={'slot': 104}, value=dict(blockhash=fake_key('controlled-swap-hash'), lastValidBlockHeight=2000))
        elif method == 'getFeeForMessage':
            value = dict(context={'slot': 104}, value=5000)
        elif method == 'getMultipleAccounts':
            value = dict(context={'slot': 104}, value=[copy.deepcopy(self.rows[k]) for k in q['params'][0]])
        elif method == 'getBlockTime':
            value = time.time_ns() // 1000000000
        elif method == 'isBlockhashValid':
            value = dict(context={'slot': 104}, value=True)
        elif method == 'simulateTransaction':
            capture = json.loads((self.home / swap.CHILD / 'preflight.json').read_text())
            value = simulation(capture)
            value['context']['slot'] = 105
        else:
            raise AssertionError('No send method supported: ' + method)
        if self.change:
            value = self.change(q, value)
        return Response(json.dumps(dict(jsonrpc='2.0', id=q['id'], result=value)).encode())


class ControlledSwapCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = tempfile.TemporaryDirectory()
        cls.template = Path(cls.source.name) / 'wallet'
        cls.wallet = initialize(cls.template)['wallet']
        result = execute_pair(cls.template, cls.wallet, opener=PairTransport(cls.template), sleeper=lambda _: None)
        assert result['state'] == 'finalized-success'
        # Preserve a realistic large legacy executable in the finalized setup journal.
        def large_ata(q, v, _):
            if q['method'] == 'getMultipleAccounts':
                v['value'][ROLES.index('associatedTokenProgram')]['data'] = [base64.b64encode(bytes(105033)).decode(), 'base64']
            return v
        with patch('pool_workflow.BASELINE', BASE), patch('pool_contract.BASELINE', BASE):
            result = pool.execute(cls.template, cls.wallet, opener=PoolTransport(cls.template, change=large_ata), sleeper=lambda _: None)
        assert result['state'] == 'finalized-success', result
        cls.pool = result['intent']['accounts']['pool']
    @classmethod
    def tearDownClass(cls):
        cls.source.cleanup()
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / 'wallet'
        shutil.copytree(self.template, self.home)
        baseline = dict(copy.deepcopy(BASE), network='devnet', kind='observed-devnet-deployment', observedAtMs=0)
        self.patches = [patch('preflight.BASELINE', baseline), patch('preflight_capture.BASELINE', baseline)]
        for p in self.patches:
            p.start()
    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()
    def run_sim(self, change=None):
        t = SwapTransport(self.home, change)
        return bridge.simulate(self.home, self.wallet, self.pool, opener=t), t
    def edit_observation(self, edit):
        path = self.home / pool.CHILD / 'observation-000.json'
        value = json.loads(path.read_text())
        edit(value)
        path.write_text(json.dumps(value))
    def test_local_inspection_replays_large_journal_and_fixed_scope_without_rpc_or_signing(self):
        r = bridge.inspect(self.home, self.wallet, self.pool)
        self.assertEqual(r['state'], 'controlled-scope-ready')
        self.assertEqual(r['rehearsal']['networkRequests'], 0)
        self.assertFalse((self.home / swap.CHILD).exists())
        self.assertEqual(r['scope']['amountIn'], '1000')
        self.assertEqual(r['scope']['minimumAmountOut'], '990')
        self.assertEqual(r['scope']['maxMicroLamportsPerCU'], '0')
        self.assertGreater((self.home / pool.CHILD / 'plan.json').stat().st_size, 131072)
        a = pool.read(self.home / pool.CHILD, 'plan.json')['accounts']
        for dest, src in [('inputMint', 'mint0'), ('outputMint', 'mint1'), ('source', 'holder0'), ('inputVault', 'vault0')]:
            self.assertEqual(r['scope']['accounts'][dest], a[src])
    def test_live_path_with_fake_transport_uses_real_collectors_signer_and_exact_token_deltas(self):
        r, t = self.run_sim()
        self.assertEqual(r['state'], 'signed-simulation-consistent', r)
        self.assertEqual(len(t.calls), 14)
        self.assertEqual(r['networkRequests'], 14)
        self.assertEqual(r['rehearsal']['signaturesCreatedThisRun'], 1)
        self.assertEqual(r['rehearsal']['simulation']['inputAtomic'], '1000')
        self.assertEqual(r['rehearsal']['simulation']['simulatedOutputAtomic'], '990')
        self.assertEqual(r['transactionsSent'], 0)
        q = next(q for q in t.calls if q['method'] == 'simulateTransaction')
        self.assertTrue(q['params'][1]['sigVerify'])
        self.assertFalse(q['params'][1]['replaceRecentBlockhash'])
        self.assertNotIn(q['params'][0], json.dumps(r))
        self.assertNotIn('sendTransaction', [q['method'] for q in t.calls])
    def test_repeat_and_status_never_create_second_signature_or_requests(self):
        r, t = self.run_sim()
        self.assertEqual(r['state'], 'signed-simulation-consistent', r)
        path = self.home / swap.CHILD
        before = {p.name: p.read_bytes() for p in path.iterdir()}
        t.calls.clear()
        repeated = bridge.simulate(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(repeated['state'], r['state'])
        self.assertEqual(t.calls, [])
        self.assertEqual(bridge.status(self.home, self.wallet)['state'], r['state'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in path.iterdir()})
    def test_wrong_explicit_pool_or_wallet_refused_before_requests(self):
        for wallet, pool_key in [(self.wallet, fake_key('otherpool')), (fake_key('otherwallet'), self.pool)]:
            t = SwapTransport(self.home)
            with self.assertRaises(ValueError):
                bridge.simulate(self.home, wallet, pool_key, opener=t)
            self.assertEqual(t.calls, [])
    def test_unfinalized_or_quarantined_setup_refused(self):
        for state in ['submission-unknown', 'finalized-failure', 'quarantined', 'finalized-success-accounts-unverified']:
            self.edit_observation(lambda v: v.update(state=state))
            with self.assertRaises(ValueError):
                bridge.inspect(self.home, self.wallet, self.pool)
    def test_receipt_identity_or_accounting_mismatch_refused(self):
        path = self.home / pool.CHILD / 'observation-000.json'
        original = path.read_bytes()
        for field, value in [('signature', 'wrong'), ('messageSha256', 'wrong'), ('wireSha256', 'wrong'),
                             ('walletAfterLamports', '1'), ('feeLamports', True), ('slot', 0)]:
            path.write_bytes(original)
            self.edit_observation(lambda v: v['receipt'].update({field: value}))
            with self.assertRaises(ValueError):
                bridge.inspect(self.home, self.wallet, self.pool)
    def test_raw_vault_or_pool_evidence_tampering_refused(self):
        self.edit_observation(lambda v: v['accountEvidence'][ROLES.index('vault0')].update(lamports=1))
        with self.assertRaises(ValueError):
            bridge.inspect(self.home, self.wallet, self.pool)
    def test_stop_blocks_preparation_but_status_and_inspect_work(self):
        (self.home / 'STOP').write_text('stop')
        t = SwapTransport(self.home)
        with self.assertRaises(ValueError):
            bridge.simulate(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(t.calls, [])
        self.assertTrue(bridge.inspect(self.home, self.wallet, self.pool)['rehearsal']['stopRequested'])
        self.assertEqual(bridge.status(self.home, self.wallet)['state'], 'not-started')
    def test_existing_different_scope_refused_without_reset(self):
        scope = bridge.inspect(self.home, self.wallet, self.pool)['scope']
        scope['amountIn'] = '999'
        child = self.home / swap.CHILD
        child.mkdir(mode=0o700)
        write_new(child / 'plan.json', dict(format='swap-signing-plan-1', scope=scope))
        t = SwapTransport(self.home)
        with self.assertRaises(ValueError):
            bridge.simulate(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(t.calls, [])
        self.assertEqual(json.loads((child / 'plan.json').read_text())['scope']['amountIn'], '999')
    def test_interrupted_empty_child_is_not_reused_and_status_remains_readable(self):
        (self.home / swap.CHILD).mkdir(mode=0o700)
        t = SwapTransport(self.home)
        with self.assertRaises((ValueError, OSError)):
            bridge.simulate(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(t.calls, [])
        self.assertEqual(bridge.status(self.home, self.wallet)['rehearsal']['networkRequests'], 0)
        self.assertEqual(bridge.status(self.home, self.wallet)['state'], 'preparation-incomplete')
    def test_program_drift_refuses_signing_and_keeps_failed_plan(self):
        def change(q, v):
            if q['method'] == 'getMultipleAccounts' and len(q['params'][0]) == 12:
                raw = bytearray(base64.b64decode(v['value'][-1]['data'][0])); raw[-1] ^= 1
                v['value'][-1]['data'][0] = base64.b64encode(raw).decode()
            return v
        r, t = self.run_sim(change)
        self.assertEqual(r['state'], 'preparation-incomplete')
        self.assertFalse((self.home / swap.CHILD / 'signing-attempt.json').exists())
        self.assertNotIn('simulateTransaction', [q['method'] for q in t.calls])
    def test_changed_holder_authority_refuses_signing(self):
        def change(q, v):
            if q['method'] == 'getMultipleAccounts' and len(q['params'][0]) == 12:
                raw = bytearray(base64.b64decode(v['value'][9]['data'][0])); raw[32:64] = bytes(32)
                v['value'][9]['data'][0] = base64.b64encode(raw).decode()
            return v
        r, _ = self.run_sim(change)
        self.assertEqual(r['state'], 'preparation-incomplete')
        self.assertFalse((self.home / swap.CHILD / 'signed.json').exists())
    def test_expired_blockhash_refuses_signing(self):
        r, _ = self.run_sim(lambda q, v: dict(context={'slot': 104}, value=False) if q['method'] == 'isBlockhashValid' else v)
        self.assertEqual(r['state'], 'preparation-incomplete')
        self.assertFalse((self.home / swap.CHILD / 'signed.json').exists())
    def test_simulation_token_mismatch_preserves_signed_failure_without_retry(self):
        def change(q, v):
            if q['method'] == 'simulateTransaction':
                v['value']['postTokenBalances'][0]['uiTokenAmount']['amount'] = '1'
            return v
        r, t = self.run_sim(change)
        self.assertEqual(r['state'], 'preparation-incomplete')
        self.assertTrue((self.home / swap.CHILD / 'signed.json').exists())
        t.calls.clear()
        self.assertEqual(bridge.simulate(self.home, self.wallet, self.pool, opener=t)['state'], 'preparation-incomplete')
        self.assertEqual(t.calls, [])
    def test_lost_signer_acknowledgement_reports_durable_signature_and_never_resigns(self):
        # The default signer is bound when _prepare is defined; intercept subprocess instead.
        original_run = swap.subprocess.run
        def after_sign(*args, **kwargs):
            result = original_run(*args, **kwargs)
            if str(args[0][-1]).endswith('swap_signer.mjs'):
                raise OSError('lost signer acknowledgement')
            return result
        with patch.object(swap.subprocess, 'run', side_effect=after_sign):
            r, t = self.run_sim()
        self.assertEqual(r['state'], 'preparation-incomplete')
        self.assertTrue((self.home / swap.CHILD / 'signed.json').exists())
        self.assertEqual(r['signaturesCreatedThisRun'], 1)
        t.calls.clear()
        bridge.simulate(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(t.calls, [])
    def test_interrupted_signing_marker_without_result_remains_unknown(self):
        original_run = swap.subprocess.run
        def interrupted(*args, **kwargs):
            if str(args[0][-1]).endswith('swap_signer.mjs'):
                write_new(self.home / swap.CHILD / 'signing-attempt.json', {'interrupted': True})
                raise OSError('lost signing result')
            return original_run(*args, **kwargs)
        with patch.object(swap.subprocess, 'run', side_effect=interrupted):
            r, t = self.run_sim()
        self.assertEqual(r['state'], 'preparation-incomplete')
        self.assertIsNone(r['signaturesCreatedThisRun'])
        self.assertTrue(r['rehearsal']['signatureOutcomeUnknown'])
        t.calls.clear()
        bridge.simulate(self.home, self.wallet, self.pool, opener=t)
        self.assertEqual(t.calls, [])
    def test_cli_requires_explicit_sign_flag_and_rejects_sender_actions(self):
        cli = Path(__file__).with_name('swap_cli.py')
        for extra in [['--action', 'simulate'], ['--action', 'inspect', '--allow-devnet-sign'], ['--action', 'execute']]:
            result = subprocess.run([sys.executable, str(cli), *extra, '--output', str(self.home / 'report.json.gz')], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((self.home / swap.CHILD).exists())


if __name__ == '__main__':
    unittest.main()
