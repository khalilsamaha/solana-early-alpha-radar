"""Prepare one subsequent controlled cycle, preserving all earlier private journals.

No signer, transaction builder or send method. Allocation is preparation-only;
future execution must bind this record and reserve before signing independently.
"""
import copy
from decimal import Decimal
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import swap_submission as submit
from core import check, directory, private_file, loads, write_new, sync_directory, account_value
from recorded_capture import Client, GENESIS
sys.path.insert(0, str(submit.bridge.ROOT / 'position-book'))
import controlled

VERSION = 'controlled-cycle-preparation-1'
CYCLE = 'controlled-cycle-0002'
LIMIT = 512 * 1024
POLICY = dict(network='devnet', maximumCycles=2, maximumCumulativeEntryAtomic='2000',
              maximumCumulativeSwapFeeLamports='40000', nextEntryAtomic='1000',
              nextMinimumOutputAtomic='990', nextRoundTripFeeAllowanceLamports='20000')


class ReadRpc(Client):
    METHODS = ('getGenesisHash', 'getSignatureStatuses', 'getTransaction', 'getMultipleAccounts')
    REQUEST_CAP = 7


def clock(): return time.time_ns() // 1000000


def budget(position):
    principal = submit.atomic(position['originalSpentAtomic'], 'historical-input', positive=True)
    fees = submit.atomic(position['confirmedFeeLamports'], 'historical-fees', positive=True)
    check(principal == 1000 and fees <= 20000, 'historical-budget-outside-policy')
    gross = principal + int(POLICY['nextEntryAtomic'])
    allocated = fees + int(POLICY['nextRoundTripFeeAllowanceLamports'])
    check(2 <= POLICY['maximumCycles'] and gross <= int(POLICY['maximumCumulativeEntryAtomic'])
          and allocated <= int(POLICY['maximumCumulativeSwapFeeLamports']), 'cumulative-budget-exceeded')
    return dict(historicalCycles=1, allocatedCycles=2, historicalEntryAtomic=str(principal),
                historicalSwapFeeLamports=str(fees), nextEntryAllocationAtomic=POLICY['nextEntryAtomic'],
                nextFeeAllocationLamports=POLICY['nextRoundTripFeeAllowanceLamports'],
                cumulativeEntryWithAllocationAtomic=str(gross), cumulativeSwapFeesWithAllocationLamports=str(allocated),
                historicalNetOriginalTokenAtomic=position['netOriginalTokenAtomic'],
                historicalResidualAcquiredAtomic=position['lastReconciledResidualAtomic'],
                allocationOnly=True, signerEnforcementConnected=False,
                feeScope='Controlled swap entry/reverse receipts only; setup, rent and other wallet activity excluded')


def local(home, wallet, pool):
    scope, proof = submit.bridge.source_scope(SimpleNamespace(home=home, wallet=wallet), pool)
    first = submit.forward_evidence(home, wallet)
    last = submit.report(home, wallet, reverse=True)
    check(last['state'] == 'finalized-success' and last['submissionBoundaryRecorded']
          and not last['signatureOutcomeUnknown'], 'prior-round-trip-not-closed')
    position = controlled.snapshot(first, last, proof)
    check(first['scope'] == scope and position['state'] == 'closed'
          and position['lastReconciledResidualAtomic'] == '0', 'prior-position-not-closed')
    # If an accounting book already exists, it must agree; do not rewrite it here.
    if os.path.lexists(home / controlled.NAME):
        ledger = controlled.Ledger(home, create=False)
        try:
            check(ledger.read()[0] == position, 'historical-ledger-not-reconciled')
        finally:
            ledger.close()
    if os.path.lexists(home / submit.spend_guard.NAME):
        with submit.spend_guard.Guard(home) as g:
            state = g.read()[0]
            check(g.summary()['state'] == 'closed' and state['legs']['entry']['receipt'] == first['observation']['receipt']
                  and state['legs']['exit']['receipt'] == last['observation']['receipt'], 'prior-spending-not-reconciled')
    binding = dict(scope=scope, setupProof=proof, position=position,
                   entryReceipt=first['observation']['receipt'], exitReceipt=last['observation']['receipt'])
    return binding, budget(position)


def review_capture(home, wallet, source, capture):
    """Validate raw evidence first; expose differences without accepting continuity."""
    check(capture['genesisBefore'] == capture['genesisAfter'] == GENESIS['devnet'], 'wrong-cluster')
    receipts = capture['receipts']
    check(type(receipts) is list and len(receipts) == 2, 'receipt-count')
    for name, expected, observed in zip((submit.CHILD, submit.REVERSE_CHILD),
            (source['entryReceipt'], source['exitReceipt']), receipts):
        plan, wire, signed, _ = submit.bound(home / name, wallet)
        actual = submit.receipt(observed['transaction'], observed['status'], plan, wire, signed,
                               submit.read(home / name, 'presend-preflight.json', 4 * 1024 * 1024))
        check(actual == expected, 'historical-chain-receipt-mismatch')
    slot, rows = submit.context_value(capture['accounts'], source['exitReceipt']['slot'])
    a = source['scope']['accounts']
    check(capture['accountKeys'] == [a['wallet'], a['source'], a['destination']]
          and type(rows) is list and len(rows) == 3, 'balance-snapshot-shape')
    native = account_value(rows[0])
    original = submit.swap.token(rows[1], a['inputMint'], wallet)
    acquired = submit.swap.token(rows[2], a['outputMint'], wallet)
    authorities = {name: t['delegate'] is None and t['delegatedAmount'] == '0' and t['closeAuthority'] is None
                   for name,t in (('original',original),('acquired',acquired))}
    last = source['exitReceipt']
    check(type(capture['accountsReceivedAtMs']) is int and type(capture['finishedAtMs']) is int
          and 0 < capture['accountsReceivedAtMs'] <= capture['finishedAtMs']
          <= capture['accountsReceivedAtMs'] + 10000, 'balance-observation-expired')
    balances = dict(slot=slot, walletLamports=str(native), originalTokenAtomic=original['amount'],
                    backgroundAcquiredAtomic=acquired['amount'], receivedAtMs=capture['accountsReceivedAtMs'])
    def difference(expected, observed):
        return dict(expected=str(expected), observed=str(observed), delta=str(int(observed)-int(expected)),
                    matches=int(expected)==int(observed))
    native_diff = difference(last['walletAfterLamports'],native)
    native_diff['deltaDevnetSol'] = format(Decimal(native_diff['delta'])/Decimal(1000000000),'f')
    comparison = dict(nativeLamports=native_diff,
        originalTokenAtomic=difference(last['tokenEffects']['destination']['afterAtomic'],original['amount']),
        acquiredTokenAtomic=difference(last['tokenEffects']['source']['afterAtomic'],acquired['amount']),
        tokenAuthoritiesIntact=authorities,
        nextCycleFundingSufficient=native >= int(POLICY['nextRoundTripFeeAllowanceLamports'])
                                  and int(original['amount']) >= int(POLICY['nextEntryAtomic']))
    return balances, comparison


def validate_capture(home, wallet, source, capture):
    balances, comparison = review_capture(home, wallet, source, capture)
    check(all(comparison['tokenAuthoritiesIntact'].values()), 'token-authority-changed-since-close')
    check(comparison['nativeLamports']['matches'], 'wallet-balance-changed-since-close')
    check(comparison['originalTokenAtomic']['matches'] and comparison['acquiredTokenAtomic']['matches'],
          'token-balance-changed-since-close')
    check(comparison['nextCycleFundingSufficient'], 'next-cycle-funding-required')
    return balances


def collect_evidence(source, rpc, now):
    result = dict(genesisBefore=submit.received(rpc.request('getGenesisHash', [])), receipts=[])
    check(result['genesisBefore'] == GENESIS['devnet'], 'wrong-cluster')
    for expected in (source['entryReceipt'], source['exitReceipt']):
        st = submit.signature_status(rpc, expected['signature'], expected['slot'])
        check(st is not None and st['confirmationStatus'] == 'finalized', 'historical-finality-unavailable')
        tx = submit.transaction(rpc, expected['signature'])
        check(tx is not None, 'historical-transaction-unavailable')
        result['receipts'].append(dict(status=st, transaction=tx))
    a = source['scope']['accounts']; keys = [a['wallet'], a['source'], a['destination']]
    result.update(accountKeys=keys, accounts=rpc.request('getMultipleAccounts',
        [keys, dict(encoding='base64', commitment='finalized', minContextSlot=source['exitReceipt']['slot'])]),
        accountsReceivedAtMs=now())
    result['genesisAfter'] = submit.received(rpc.request('getGenesisHash', []))
    result['finishedAtMs'] = now()
    return result


def capture_now(home, wallet, source, rpc, now):
    result = collect_evidence(source, rpc, now)
    validate_capture(home, wallet, source, result)
    return result


def diagnose(home, wallet, pool, *, opener=None, now=clock):
    """Read-only chain comparison; never creates/updates a preparation or budget."""
    with controlled.source_lock(home, wallet) as home:
        source, _ = local(home, wallet, pool)
        rpc = ReadRpc('devnet', opener)
        capture = collect_evidence(source, rpc, now)
        balances, comparison = review_capture(home, wallet, source, capture)
        check(capture['finishedAtMs'] <= now() <= capture['accountsReceivedAtMs']+10000,
              'balance-observation-expired')
        matching = all(comparison[k]['matches'] for k in ('nativeLamports','originalTokenAtomic','acquiredTokenAtomic'))
        matching = matching and all(comparison['tokenAuthoritiesIntact'].values())
        result = public('balance-comparison-match' if matching else 'balance-comparison-mismatch', calls=len(rpc.calls))
        result.update(diagnosticVersion='cycle-balance-diagnostic-1',wallet=wallet,pool=pool,
            priorReceiptsReverified=True,priorClosingSlot=source['exitReceipt']['slot'],
            priorExitSignature=source['exitReceipt']['signature'],snapshot=balances,comparison=comparison,
            causeEstablished=False,preparationDirectoryPresent=os.path.lexists(home/CYCLE),
            journalFilesChanged=False,
            attributionNote='Net balance differences do not establish their cause or enumerate intervening activity; no rebase or override performed.')
        return result


def public(state, *, changed=False, calls=0, record=None):
    r = dict(format=VERSION, state=state, cycleId=CYCLE, preparationCreated=changed,
             network='devnet', networkRequests=calls, transactionsSent=0, signaturesCreated=0,
             privateKeyAccessed=False, executionApproved=False, mainnetEnabled=False,
             pretradeBudgetEnforced=False, senderConnected=False, currentWalletBalancesKnown=False,
             requiresFreshExecutionPreflight=True, policy=copy.deepcopy(POLICY),
             limitations=['Preparation allocates one subsequent controlled cycle, but cannot sign or submit it.',
                          'Prior receipts remain historical evidence; no retroactive pretrade enforcement is claimed.',
                          'Balance continuity is as-of the saved finalized RPC snapshot, not a current inventory.',
                          'Gross entry input is cumulative; returned tokens never replenish this allocation cap.',
                          'Setup costs and unrelated wallet activity are outside this two-cycle swap budget.',
                          'Same-user files and a single RPC provider are trusted; this is not a mainnet authorization.'])
    if record:
        r.update(wallet=record['wallet'], pool=record['pool'], preparedAtMs=record['preparedAtMs'],
                 preparationSha256=controlled.digest(record), priorEvidenceSha256=record['priorEvidenceSha256'],
                 budget=record['budget'], balancesAtPreparation=record['balances'],
                 priorEntrySignature=record['source']['entryReceipt']['signature'],
                 priorExitSignature=record['source']['exitReceipt']['signature'])
    return r


def existing(home, wallet, pool, source, allocation):
    child = directory(home / CYCLE)
    names = {p.name for p in child.iterdir()}
    check(names <= {'preparation.json', 'complete.json'}, 'unexpected-cycle-preparation-files')
    if names != {'preparation.json', 'complete.json'}:
        return public('preparation-incomplete')
    record = loads(private_file(child / 'preparation.json', LIMIT))
    seal = loads(private_file(child / 'complete.json', 4096))
    check(record.get('format') == VERSION and record.get('cycleId') == CYCLE and record.get('wallet') == wallet
          and record.get('pool') == pool and record.get('policy') == POLICY and record.get('budget') == allocation
          and record.get('source') == source and record.get('priorEvidenceSha256') == controlled.digest(source),
          'cycle-source-or-policy-changed')
    check(type(record.get('preparedAtMs')) is int and record['preparedAtMs'] == record['capture']['finishedAtMs']
          and record['balances'] == validate_capture(home, wallet, source, record['capture']), 'cycle-capture-changed')
    check(seal == dict(format=VERSION, preparationSha256=controlled.digest(record)), 'cycle-seal-mismatch')
    return public('prepared-not-executable', record=record)


def run(home, wallet, pool, *, prepare=False, opener=None, now=clock):
    # Public identity + common execution lock; deliberately never instantiate key-reading Session.
    with controlled.source_lock(home, wallet) as home:
        source, allocation = local(home, wallet, pool)
        if os.path.lexists(home / CYCLE):
            return existing(home, wallet, pool, source, allocation)
        if not prepare:
            return dict(public('not-prepared'), budget=allocation, wallet=wallet, pool=pool)
        check(not submit.swap.stop(home), 'stop-requested')
        rpc = ReadRpc('devnet', opener)
        capture = capture_now(home, wallet, source, rpc, now)
        balances = validate_capture(home, wallet, source, capture)
        check(not submit.swap.stop(home), 'stop-requested')
        check(capture['finishedAtMs'] <= now() <= capture['accountsReceivedAtMs'] + 10000, 'balance-observation-expired')
        record = dict(format=VERSION, cycleId=CYCLE, wallet=wallet, pool=pool,
                      policy=copy.deepcopy(POLICY), budget=allocation, source=source,
                      priorEvidenceSha256=controlled.digest(source), capture=capture,
                      balances=balances, preparedAtMs=capture['finishedAtMs'])
        check(len(controlled.encoded(record).encode()) <= LIMIT, 'cycle-record-size-cap')
        child = home / CYCLE
        child.mkdir(mode=0o700); sync_directory(home)
        # Once this directory exists, interruptions never reset or silently repeat preparation.
        write_new(child / 'preparation.json', record)
        write_new(child / 'complete.json', dict(format=VERSION, preparationSha256=controlled.digest(record)))
        return public('prepared-not-executable', changed=True, calls=len(rpc.calls), record=record)
