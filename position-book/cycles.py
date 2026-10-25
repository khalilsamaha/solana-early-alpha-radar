"""Historical accounting of exactly two closed controlled devnet cycles.

Replay private source journals under the execution lock. Never accept public
reports as source, repair source state, query RPC, sign, or allocate another cycle.
"""
import copy
import os
import controlled as c
import cycle_binding as binding
import cycle_preparation as preparation
from core import check, directory

VERSION = 'controlled-two-cycle-ledger-1'
NAME = 'controlled.two-cycle-positions.sqlite'


def read_evidence(home, wallet, pool):
    first, _ = preparation.local(home, wallet, pool)
    child = directory(home / binding.CYCLE)
    b = binding.load(child, wallet, pool)
    entry = c.submit.forward_evidence(child, wallet)
    exit_ = c.submit.report(child, wallet, reverse=True)
    check(entry['scope'] == first['scope'] and exit_['state'] == 'finalized-success'
          and exit_['submissionBoundaryRecorded'] and not exit_['signatureOutcomeUnknown'],
          'second-cycle-not-closed')
    second = c.snapshot(entry, exit_, first['setupProof'])
    positions = [dict(first['position'], cycleId='controlled-cycle-0001'),
                 dict(second, cycleId=binding.CYCLE)]
    for p in positions:
        check(p['state'] == 'closed' and p['accountingUsable']
              and p['lastReconciledResidualAtomic'] == '0', 'closed-cycles-required')
    signatures = [p[k] for p in positions for k in ('entrySignature', 'exitSignature')]
    check(len(set(signatures)) == 4, 'duplicate-cycle-receipt')
    a = first['exitReceipt']; e = entry['observation']['receipt']; x = exit_['observation']['receipt']
    check(e['slot'] >= b['balances']['slot'] > a['slot']
          and e['walletBeforeLamports'] == b['balances']['walletLamports']
          and e['tokenEffects']['source']['beforeAtomic'] == a['tokenEffects']['destination']['afterAtomic']
          and e['tokenEffects']['destination']['beforeAtomic'] == a['tokenEffects']['source']['afterAtomic'],
          'cross-cycle-continuity')
    # binding.load replayed the sealed funding proof and its exact balance equation.
    external_credit = int(e['walletBeforeLamports']) - int(a['walletAfterLamports'])
    check(external_credit >= 0, 'negative-between-cycle-credit')
    with c.submit.spend_guard.Guard(child) as guard:
        state, events, head, _ = guard.read()
        summary = guard.summary()
        check(summary['state'] == 'closed' and summary['accountingUsable']
              and summary['reservedFeeLamports'] == '0'
              and summary['heldEntryPrincipalAtomic'] == '0'
              and state['legs']['entry']['receipt'] == e and state['legs']['exit']['receipt'] == x,
              'second-spending-not-reconciled')
        replacement = summary.get('unsignedReplacement')
        check(replacement == exit_['spendingGuard'].get('unsignedReplacement'), 'replacement-ledger-mismatch')
        if replacement:
            check(replacement['manifestSha256'] == exit_['unsignedReplacement']['manifestSha256']
                  and replacement['newPlanSha256'] == summary['legs']['entry']['planSha256'],
                  'replacement-evidence-mismatch')
    fees = sum(int(p['confirmedFeeLamports']) for p in positions)
    spent = sum(int(p['originalSpentAtomic']) for p in positions)
    returned = sum(int(p['returnedOriginalAtomic']) for p in positions)
    check(str(fees) == summary['cumulativeConfirmedFeeLamports']
          and str(spent) == summary['cumulativeGrossEntryAllocatedAtomic']
          and fees <= int(b['cumulativeFeeCapLamports'])
          and spent <= int(b['cumulativeEntryCapAtomic']), 'cumulative-accounting-mismatch')
    before = int(first['entryReceipt']['walletBeforeLamports']); after = int(x['walletAfterLamports'])
    check(before + external_credit - fees == after, 'cumulative-native-reconciliation')
    check(returned - spent == sum(int(p['netOriginalTokenAtomic']) for p in positions), 'cumulative-token-reconciliation')
    return dict(format=VERSION, state='closed', wallet=wallet, pool=pool, positions=positions,
        accountingUsable=True, quarantineReason=None, currentWalletBalancesKnown=False,
        source=dict(preparationSha256=b['preparationSha256'], priorEvidenceSha256=b['priorEvidenceSha256'],
                    spendingLedgerHead=head, spendingEventCount=events, unsignedReplacement=replacement),
        totals=dict(closedCycles=2, grossOriginalSpentAtomic=str(spent), returnedOriginalAtomic=str(returned),
                    netOriginalTokenAtomic=str(returned-spent), residualAcquiredAtomic='0',
                    confirmedSwapFeeLamports=str(fees), reservedFeeLamports='0',
                    verifiedBetweenCycleCreditLamports=str(external_credit),
                    walletBeforeFirstEntryLamports=str(before), walletAfterSecondExitLamports=str(after)))


class Ledger(c.Ledger):
    name = NAME
    version = VERSION
    # Both positions are closed: changed evidence is never a legitimate update.
    conflict = staticmethod(lambda old, new: old != new)

    @staticmethod
    def quarantine(old, reason):
        result = copy.deepcopy(old)
        result.update(state='quarantined', accountingUsable=False, quarantineReason=reason)
        return result

    @staticmethod
    def result(value, count, changed):
        return dict(format=VERSION, state=value['state'], accounting=value, eventCount=count,
                    ledgerChanged=changed, **c.FLAGS, mainnetEnabled=False, nextCycleAuthorized=False,
                    limitations=[
                        'Exactly two closed controlled devnet cycles; no new execution or budget authorization.',
                        'Local finalized receipt replay, not a fresh chain or wallet balance observation.',
                        'External credits are separate from swap returns; setup, rent and unrelated fees excluded.',
                        'The first position ledger, spending ledgers and all execution journals remain unchanged.',
                        'After quarantine, totals are last accepted historical values and are not usable accounting.',
                        'Local ownership and hashes are trust assumptions; no profitability claim.'])


@binding.operation
def sync(home, wallet, pool):
    with c.source_lock(home, wallet) as home:
        ledger = None
        try:
            # Reject a wrong caller identity before quarantine can modify a book.
            if os.path.lexists(home / NAME):
                ledger = Ledger(home, create=False)
                old = ledger.read()[0]
                check(old is None or (old['wallet'] == wallet and old['pool'] == pool), 'explicit-ledger-identity-mismatch')
            try:
                value = read_evidence(home, wallet, pool)
            except (ValueError, KeyError, TypeError, OSError):
                if ledger is None or ledger.read()[0] is None:
                    raise ValueError('source-validation-failed') from None
                return ledger.apply(source_error=True)
            if ledger is None:
                ledger = Ledger(home, create=True)
            return ledger.apply(value)
        finally:
            if ledger is not None:
                ledger.close()
