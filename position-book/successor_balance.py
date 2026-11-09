"""Internal four-read successor balance observation; never release retired exposure.

Uses the existing account, RPC and freshness contracts with an exact-successor
accounting context. No default provider or operational CLI is exposed.
"""
import base64
from copy import deepcopy
import time

import successor_accounting as accounting
import exit_balance as original
from contract import digest, NATIVE
from core import check
from journal import read_only_journals

VERSION = 'successor-balance-1'
view = original.view
CODES = original.ERRORS | {'successor-balance-accounting-required', 'successor-balance-flat-required',
    'successor-balance-identity', 'successor-balance-exposure', 'successor-balance-total-budget'}


def context(book, root, wallet, pool, expected, clock):
    check(not accounting.submission.handoff.original.stopped(root, book), 'balance-stopped')
    reviewed = accounting.replay(root, book, wallet, pool, expected, clock)
    check(reviewed['accountingUsable'], 'successor-balance-accounting-required')
    check(reviewed['state'] == 'successor-accounted-flat-held', 'successor-balance-flat-required')
    saved = accounting.saved(book, clock()); effects = saved['effects']
    record, _, retired, signed, _ = accounting.submission.load(root, book, wallet, pool, expected, clock)
    check(effects['successorSha256'] == expected == digest(record) and
          effects['retirementSha256'] == digest(retired), 'successor-balance-identity')
    private, scope = accounting.receipts.original.private_intent(book, signed, record['candidate'])
    roles = scope['accounts']
    keys = [wallet, roles['destination'], roles['source'], roles['outputMint'], roles['inputMint']]
    check(roles['wallet'] == wallet and roles['pool'] == pool and len(set(keys)) == 5, 'balance-scope')
    check(NATIVE not in keys[3:], 'balance-unsupported-native')
    capture = record['candidate']['evidence']['capture']
    rows = dict(zip(capture['accountKeys'], capture['evidence']['accounts']['result']['value']))
    accounts = deepcopy([rows[key] for key in keys])
    accounts[0]['lamports'] -= int(effects['successorFeePaidLamports'])
    amounts = (int(private['intent']['destination']['preAmountAtomic']) + int(effects['sourceProceedsObservedAtomic']),
               int(effects['protectedAcquiredInventoryAtomic']) + int(effects['ownedAcquiredResidualAtomic']))
    for row, amount in zip(accounts[1:3], amounts):
        raw = bytearray(base64.b64decode(row['data'][0], validate=True))
        raw[64:72] = amount.to_bytes(8, 'little'); row['data'] = [base64.b64encode(raw).decode(), 'base64']
    held = effects['projectedFeeHoldAfterKnownFeesLamports']
    exposure = effects['retiredFeeExposureHeldLamports']
    check(int(held) >= int(exposure) > 0, 'successor-balance-exposure')
    admission = book.read()
    local = view.read_locked(root, wallet, pool, clock)
    check(local['wallet'] == wallet and local['pool'] == pool and local['phase'] == 'closed' and
          local['nativeHeldLamports'] == '0' and all(row['heldAtomic'] == '0' for row in local['tokenAccounts']) and
          local['ledgerHeadSha256'] == admission[0]['ledgerHeadSha256'] and
          local['cycleBindingSha256'] == admission[0]['cycleBindingSha256'], 'balance-source-changed')
    identity = dict(accountingSha256=digest(saved), successorSha256=expected,
        retirementSha256=digest(retired), admissionSha256=digest(admission),
        sourceLedgerHeadSha256=local['ledgerHeadSha256'], sourceCycleBindingSha256=local['cycleBindingSha256'],
        policySha256=digest(book.policy), captureSha256=saved['captureSha256'])
    return dict(identity=identity, accountKeys=keys, expectedAccounts=accounts,
        receiptSlot=effects['receiptSlot'], recordedAtMs=saved['recordedAtMs'],
        feeHeldLamports=held, retiredFeeExposureHeldLamports=exposure,
        proceedsHeldAtomic=effects['sourceProceedsObservedAtomic'],
        protectedInventoryAtomic=effects['protectedAcquiredInventoryAtomic'])


@view.cycles.binding.operation
@accounting.submission.handoff.successor.history.fresh_signing.timing.signature_replay
def collect(home, wallet, pool, expected, *, opener=None, clock=view.now, monotonic=time.monotonic):
    check(opener is not None and bool(opener) and callable(getattr(opener, 'open', None)),
          'successor-balance-injected-provider-required')
    result = dict(format=VERSION, state='successor-balances-unavailable-held', diagnosticCode=None,
        networkRequests=0, requestMethods=[], snapshot=None, balanceReconciliationPassed=False,
        evidencePersisted=False, sourceStateChanged=False, databaseConnectionsReadOnly=True,
        reservationsReleased=False, retiredExposureReleased=False, retiredAttemptNonExecutionProven=False,
        fundsAvailableForNewEntry=False, scopedClosureRecorded=False, nextCycleAuthorized=False,
        executionApproved=False, privateKeyAccessed=False, signaturesCreated=0, transactionsSent=0,
        headroomAtReturnMs=None,
        limitations=['Four fixed devnet reads at most; no retries or public-report imports.',
            'As-of finalized RPC balances, not independent chain proof or future spendability.',
            'Unexplained changes including deposits block the observation.',
            'Matching balances do not resolve the retired attempt or authorize release/closure.'])
    rpc = None; started = monotonic()
    def budget():
        elapsed = monotonic() - started
        check(0 <= elapsed < 120, 'successor-balance-total-budget')
        return 120 - elapsed
    class Provider:
        def open(self, request, timeout):
            return opener.open(request, timeout=min(timeout, budget()))
    class ScopedRpc(original.Rpc):
        def current(self):
            budget(); return super().current()
    try:
        with view.cycles.c.source_lock(home, wallet) as root, read_only_journals():
            book = accounting.submission.transport._open(root, wallet, pool, clock)
            try:
                with accounting.submission.original.ExitSubmission(book).snapshot():
                    ctx = context(book, root, wallet, pool, expected, clock); budget()
                    rpc = ScopedRpc(root, ctx, clock, monotonic, Provider()); evidence = {}
                    evidence['genesisBefore'] = rpc.request('getGenesisHash', [])
                    check(evidence['genesisBefore']['result'] == original.GENESIS['devnet'], 'balance-cluster')
                    evidence['accounts'] = rpc.request('getMultipleAccounts', [ctx['accountKeys'],
                        dict(encoding='base64', commitment='finalized', minContextSlot=ctx['receiptSlot'])])
                    check(rpc.slot >= ctx['receiptSlot'], 'balance-slot')
                    evidence['blockTime'] = rpc.request('getBlockTime', [rpc.slot])
                    evidence['genesisAfter'] = rpc.request('getGenesisHash', [])
                    capture = dict(format=original.VERSION + '-capture', network='devnet', identity=ctx['identity'],
                        accountKeys=ctx['accountKeys'], startedAtMs=rpc.start, finishedAtMs=rpc.current(),
                        evidence=evidence, requestTrace=deepcopy(rpc.calls))
                    after = context(book, root, wallet, pool, expected, clock)
                    check(after == ctx, 'balance-source-changed')
                    checked = original.review(after, capture, rpc.current()); budget()
                    checked.update(successorSha256=expected, retirementSha256=ctx['identity']['retirementSha256'],
                        retiredFeeExposureHeldLamports=ctx['retiredFeeExposureHeldLamports'])
            finally: book.close()
        # Snapshot close, book close and source-lock exit all count toward freshness.
        completed = rpc.current(); budget()
        result.update(state='successor-balances-match-held', snapshot=checked, balanceReconciliationPassed=True,
            headroomAtReturnMs=checked['validUntilExclusiveMs'] - completed)
    except (ValueError, KeyError, TypeError, IndexError, OSError, view.sqlite3.Error) as exc:
        result.update(state='successor-balances-unavailable-held', snapshot=None, balanceReconciliationPassed=False,
            headroomAtReturnMs=None, diagnosticCode=str(exc) if str(exc) in CODES else 'balance-evidence-unavailable')
    finally:
        if rpc is not None:
            result.update(networkRequests=len(rpc.calls), requestMethods=[row['method'] for row in rpc.calls])
        result['totalElapsedMs'] = round((monotonic()-started)*1000, 3)
    return result
