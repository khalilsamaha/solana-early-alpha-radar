"""Fixed test-pool scope bridged to the existing one-shot swap simulator. No sender."""
import copy
import os
from pathlib import Path
import sys

import pool_workflow as pool
from pool_contract import account_states, rent_total, ROLES
from core import Session, check, directory, private_file, loads, integer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'devnet-setup'))
from fresh_packet import prepare_fresh, scope_check
import swap_rehearsal as swap

VERSION = 'controlled-pool-swap-simulation-1'
INPUT_ATOMIC = '1000'
MINIMUM_OUTPUT_ATOMIC = '990'


def source_scope(session, expected_pool):
    """Replay local finalized setup evidence; it never stands in for fresh preflight."""
    pair = pool.pair_accounts(session)
    child = session.home / pool.CHILD
    directory(child)
    intent, wire, signed = pool.signed_plan(child, session.wallet)
    check(intent['pairAccounts'] == pair, 'controlled-pair-binding')
    a = intent['accounts']
    check(a['pool'] == expected_pool, 'explicit-pool-mismatch')
    history = pool.observations(child)
    check(history and history[-1].get('state') == 'finalized-success', 'finalized-controlled-pool-required')
    last = history[-1]
    receipt = last['receipt']
    check(receipt.get('state') == 'finalized-success', 'controlled-pool-receipt-state')
    for field, value in (('signature', signed['signatures'][0]),
                         ('wireSha256', signed['wireSha256']),
                         ('messageSha256', signed['wireMessageSha256'])):
        check(receipt.get(field) == value, 'controlled-pool-receipt-binding')
    check(integer(receipt.get('slot')) and receipt['slot'] >= intent['contextSlot']
          and integer(last.get('accountSnapshotSlot'))
          and last['accountSnapshotSlot'] >= receipt['slot'], 'controlled-pool-slot-order')
    fee = receipt.get('feeLamports')
    check(type(fee) is int and fee == intent['quotedFeeLamports'], 'controlled-pool-fee')
    rent = rent_total(intent['rents'])
    before = intent['walletObservedLamports']
    after = before - rent - intent['creationFeeLamports'] - fee
    check(receipt.get('creationFeeLamports') == str(intent['creationFeeLamports'])
          and receipt.get('rentLockedLamports') == str(rent)
          and receipt.get('walletBeforeLamports') == str(before)
          and receipt.get('walletAfterLamports') == str(after), 'controlled-pool-native-accounting')
    check(account_states(last['accountEvidence'], intent) == last['poolState'], 'controlled-pool-account-evidence')
    check(last['accountEvidence'][ROLES.index('wallet')]['lamports'] == after, 'controlled-pool-wallet-evidence')
    accounts = {name: a[name] for name in ('wallet', 'authority', 'config', 'pool', 'observation')}
    accounts.update(source=a['holder0'], destination=a['holder1'], inputVault=a['vault0'],
                    outputVault=a['vault1'], inputMint=a['mint0'], outputMint=a['mint1'])
    scope = dict(format='devnet-swap-scope-1', network='devnet', accounts=accounts,
                 amountIn=INPUT_ATOMIC, minimumAmountOut=MINIMUM_OUTPUT_ATOMIC,
                 maxComputeUnits=300000, maxMicroLamportsPerCU='0',
                 maxPriorityFeeLamports='0', maxTotalFeeLamports='10000')
    scope_check(scope)
    proof = dict(pool=expected_pool, poolCreationSignature=signed['signatures'][0],
                 poolIntentSha256=pool.digest(intent), poolObservationSha256=pool.digest(last),
                 receiptSlot=receipt['slot'], accountSnapshotSlot=last['accountSnapshotSlot'],
                 scopeSha256=pool.digest(scope), historicalEvidenceOnly=True,
                 direction='raw-byte-sorted-mint0-to-mint1', tokenDecimals=6)
    return scope, proof


def existing_check(home, scope):
    child = home / swap.CHILD
    if not os.path.lexists(child):
        return
    directory(child)
    plan = loads(private_file(child / 'plan.json', 32768))
    check(plan.get('format') == 'swap-signing-plan-1' and plan.get('scope') == scope,
          'existing-simulation-scope-mismatch')
    # An old or incomplete plan is never deleted, replaced or signed again.


def envelope(scope, proof, rehearsal, action):
    return dict(format=VERSION, action=action, state=rehearsal['state'], scope=scope,
                setupEvidence=proof, rehearsal=rehearsal, network='devnet',
                networkRequests=rehearsal.get('networkRequests', 0) + rehearsal.get('packetBuild', {}).get('networkRequests', 0),
                signaturesCreatedThisRun=rehearsal.get('signaturesCreatedThisRun', 0),
                transactionsSent=0, mainnetEnabled=False, executionApproved=False,
                productionLedgerUpdated=False, privateKeyExported=False, signedBytesExported=False,
                limitations=[
                    'Local finalized setup evidence is historical RPC evidence, not a current account snapshot.',
                    'Simulation recollects current pool, wallet, program identity, fee and blockhash evidence.',
                    'Fixed test policy: 1000 atomic input and at least 990 atomic output; not a route quote or market strategy.',
                    'A returned simulation is not a fill or profitability evidence.',
                    'The software signer is a same-user boundary. Signed bytes remain private but can be submitted by a holder while valid.',
                    'Existing swap-simulation-v1 state is never reset or retried; use status after an interruption.',
                ])


def inspect(home, wallet, expected_pool):
    """Local evidence and policy review only; Session verifies the dedicated wallet identity."""
    with Session(home) as s:
        check(s.wallet == wallet, 'explicit-wallet-mismatch')
        scope, proof = source_scope(s, expected_pool)
        existing_check(s.home, scope)
        result = swap.report(s.home)
        if result['state'] == 'not-started':
            result['state'] = 'stopped' if swap.stop(s.home) else 'controlled-scope-ready'
        result['stopRequested'] = swap.stop(s.home)
        return envelope(scope, proof, result, 'inspect')


def simulate(home, wallet, expected_pool, *, opener=None):
    with Session(home) as s:
        check(s.wallet == wallet, 'explicit-wallet-mismatch')
        scope, proof = source_scope(s, expected_pool)
        existing_check(s.home, scope)
        if os.path.lexists(s.home / swap.CHILD):
            return envelope(scope, proof, swap.report(s.home, reason='existing-plan-use-status-no-retry'), 'simulate')
        check(not swap.stop(s.home), 'stop-requested')
    # The shared routine reacquires the lock and checks existing state and STOP.
    # Scope is derived from fixed reviewed setup, never from an RPC route response.
    result = prepare_fresh(home, wallet, copy.deepcopy(scope), opener=opener)
    check(result.get('scope') == scope, 'simulation-scope-binding')
    return envelope(scope, proof, result, 'simulate')


def status(home, wallet):
    # Remains usable even if setup evidence is unavailable or preparation is incomplete.
    with Session(home) as s:
        check(s.wallet == wallet, 'explicit-wallet-mismatch')
        result = swap.report(s.home)
        if os.path.lexists(s.home / swap.CHILD) and result['state'] == 'not-started':
            result.update(state='preparation-incomplete', reason='existing-empty-simulation-journal')
        result['stopRequested'] = swap.stop(s.home)
        return dict(format=VERSION, action='status', state=result['state'], rehearsal=result,
                    network='devnet', mainnetEnabled=False, transactionsSent=0, networkRequests=0,
                    executionApproved=False, privateKeyExported=False, signedBytesExported=False)
