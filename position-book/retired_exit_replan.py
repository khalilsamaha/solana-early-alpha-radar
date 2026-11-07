"""Read-only reconciliation requirements for one retired, still-held devnet exit.

This produces review evidence, never a replacement capability or new generation.
"""
from copy import deepcopy
from datetime import datetime, timezone
import time

import exit_retirement as retirement
from contract import atomic, digest, uint
from core import check
from journal import read_only_journals

VERSION='retired-exit-replan-review-1'
expiry=retirement.expiry
history=retirement.history
view=retirement.view
REQUIREMENTS=['fresh-reverse-quote-and-simulation',
    'durable-successor-bound-to-retirement-and-original-reservation',
    'separate-signing-generation-with-old-attempt-denied',
    'cumulative-attempt-budget-and-exact-receipt-recovery',
    'explicit-controlled-devnet-execution-approval']


def identity(value):
    check(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),
          'replan-expected-identity')


def budget(policy,amounts):
    """Conservative proposed ceiling, not a change to ledger attempt accounting."""
    count=policy['maximumExitAttempts'];uint(count,3,'replan-attempt-cap',minimum=1)
    total=atomic(policy['maximumTotalFeeLamports'],'replan-total-cap',positive=True)
    cap=atomic(policy['maximumExitFeeLamports'],'replan-exit-cap',positive=True)
    paid=atomic(amounts['feePaidLamports'],'replan-fees-paid')
    held=atomic(amounts['feeHeldLamports'],'replan-fees-held')
    quantity=atomic(amounts['ownedAcquiredHeldAtomic'],'replan-owned',positive=True)
    protected=atomic(amounts['protectedAcquiredInventoryAtomic'],'replan-protected')
    check(amounts['basis']=='entry-settled-exit-not-settled' and
          amounts['scopedClosureRecorded'] is False and
          all(amounts[k]=='0' for k in ('sourceProceedsReleasedAtomic','unusedFeeReleasedLamports',
              'protectedInventoryReleasedAtomic')),'replan-held-accounting')
    check(paid+held<=total,'replan-fee-conservation')
    blockers=[]
    if count<=1:blockers.append('conservative-attempt-cap-exhausted')
    if held<cap:blockers.append('reserved-exit-fee-cap-not-covered')
    return dict(quantityAtomic=str(quantity),protectedInventoryAtomic=str(protected),
        feeHeldLamports=str(held),feePaidLamports=str(paid),maximumTotalFeeLamports=str(total),
        originalExitFeeCapLamports=str(cap),proposedMaximumFeeLamports=str(min(cap,held)),
        maximumExitAttempts=count,retiredSignaturesChargedForReview=1,
        conservativeRemainingAttemptSlots=max(0,count-1),attemptCounterChanged=False,
        feeReserveIncreased=False,blockers=blockers,
        basis='proposed-ceilings-with-retired-signature-counted-not-an-allocation')


def base():
    return dict(format=VERSION,state='retired-exit-review-unavailable',identity=None,
        observation=None,budget=None,blockingReasons=[],requiredIntegration=list(REQUIREMENTS),
        scopedAccounting=None,diagnosticCode=None,networkRequests=0,requestMethods=[],
        databaseConnectionsReadOnly=True,sourceStateChanged=False,privateKeyAccessed=False,
        signaturesCreated=0,transactionsSent=0,reservationsReleasedThisRun=False,
        replacementAuthorized=False,executionApproved=False,nonExecutionProven=False,
        mainnetSupported=False,automaticNextAction=False,nextAction='preserve-holds-and-investigate',
        limitations=['One fixed devnet provider; absence is not proof of global non-execution.',
            'Exact account equality is required; external credits or withdrawals need reconciliation.',
            'Proposed budget counts the retired signature conservatively, without changing ledger counters.',
            'No pool quote, simulation, replacement generation, signing or submission is produced.',
            'This public report is review evidence, never accepted as execution authority.'])


@view.cycles.binding.operation
@history.fresh_signing.timing.signature_replay
def inspect(home,wallet,pool,expected,expected_retirement,*,opener=None,clock=view.now,monotonic=time.monotonic):
    result=base();transport=None;start=monotonic();stage='local-replay'
    try:
        identity(expected);identity(expected_retirement)
        with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
            book=history.lifecycle.entry.submission._open(root,wallet,pool,clock)
            try:
                with history.lifecycle.admission_read_lock(book.j.path):
                    ctx=expiry.context(root,book,wallet,pool,expected,clock)
                    retired=retirement.row(book)
                    check(retired is not None and digest(retired)==expected_retirement,'replan-retirement-mismatch')
                    prior=retirement.validate(retired,ctx,clock())
                    ceilings=budget(book.policy,ctx['identity']['scopedAccounting'])
                    with history.transport.ExitSubmission(book).snapshot():
                        signed=history.transport.ExitSubmission(book).signing()
                        check(digest(signed)==ctx['identity']['signingStateSha256'],'replan-signing-conflict')
                    stopped=view.cycles.c.submit.swap.stop(root)
                    elapsed=monotonic()-start;check(0<=elapsed<120,'replan-operation-budget')
                    stage='rpc';transport=expiry.chain.BoundedReads([],opener,monotonic,budget=min(30,120-elapsed))
                    proof=expiry.collect_context(ctx,transport,clock)
                    check(0<=monotonic()-transport.started<=transport.budget,'expiry-budget')
                    stage='assessment'
                    # Shared DELETE-mode read lock excludes commits. Independently
                    # reread signer files, which are outside the SQLite lock.
                    history.backend._attempt_record_for_state(root,book,signed)
                    check(history.backend._read_ack(root,book,signed)==ctx['signedWire'],'replan-backend-conflict')
                    check(digest(retirement.row(book))==expected_retirement,'replan-retirement-mismatch')
                    stamp=clock();uint(stamp,proof['observedAtMs']+10000,'replan-observation-age',minimum=proof['observedAtMs'])
                    observed=expiry.assess(ctx,proof['rpcEvidence'],proof['startedAtMs'],stamp)
                    blockers=list(observed['blockers'])+ceilings['blockers']
                    for key in ('blockhashContextSlot','signatureStatusContextSlot'):
                        if observed['chainObservation'][key]<prior['chainObservation'][key]:
                            blockers.append('chain-context-regressed-since-retirement');break
                    if any(observed[k]<prior[k] for k in
                           ('accountSnapshotSlot','accountBlockTime','finalizedBlockHeight')):
                        blockers.append('account-or-height-regressed-since-retirement')
                    if stopped or view.cycles.c.submit.swap.stop(root):blockers.append('stop-requested')
                    check(0<=monotonic()-start<=120,'replan-operation-budget')
                    # Do not inherit the earlier observer's retirement next-action.
                    observed.pop('nextAction',None)
                    result.update(state='retired-exit-review-blocked' if blockers else 'retired-exit-review-consistent-held',
                        identity=dict(preparationSha256=expected,retirementSha256=expected_retirement,
                            signingStateSha256=ctx['identity']['signingStateSha256'],
                            signatureSha256=digest(ctx['identity']['signature'])),
                        observation=observed,budget=ceilings,blockingReasons=blockers,
                        scopedAccounting=deepcopy(ctx['identity']['scopedAccounting']),observedAtMs=stamp,
                        nextAction='preserve-holds-and-reconcile' if blockers else 'implement-bound-unsigned-successor')
                    stage='complete'
            finally:book.close()
    except view.ERRORS as exc:
        result=base()
        allowed={'replan-expected-identity','replan-retirement-mismatch','replan-signing-conflict',
            'replan-backend-conflict','replan-operation-budget','replan-observation-age',
            'replan-fee-conservation','replan-held-accounting','expiry-account-time','expiry-budget'}
        result['diagnosticCode']=str(exc) if str(exc) in allowed else retirement.reason(exc)
    finally:
        result.update(stage=stage,elapsedMs=round(max(0,monotonic()-start)*1000,3))
        if transport is not None:result.update(networkRequests=len(transport.calls),requestMethods=list(transport.calls))
    result['capturedAt']=datetime.now(timezone.utc).isoformat();return result
