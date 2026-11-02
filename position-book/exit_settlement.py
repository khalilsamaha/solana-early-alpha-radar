"""Collected exit effects -> fresh balances -> durable scoped closure.

Internal coordinator only. No signer, sender, allocator or live execution CLI.
Stages commit separately; later failure never implies earlier commits rolled back.
"""
import time
import admission_lifecycle as lifecycle
import fresh_signing
from contract import uint
from core import check
from journal import read_only_journals

VERSION='exit-settlement-integration-1'
closure=lifecycle.closure
accounting=closure.balance.accounting
submission=accounting.submission
view=closure.view


def base():
    return dict(format=VERSION,state='inspection-required',stage='status',coherent=False,
        diagnosticCode=None,phase=None,stopRequested=None,observedAtMs=None,
        accounting=None,closure=None,scopedAccounting=None,recordIdentity=None,
        receipt=None,balanceObservation=None,receiptRequestsThisRun=0,balanceRequestsThisRun=0,
        networkRequests=0,accountingAppliedThisRun=False,closureAppliedThisRun=False,
        closureRecorded=None,scopedCommitmentsReleased=None,
        privateKeyAccessed=False,signaturesCreated=0,transactionsSent=0,
        automaticRetryAllowed=False,automaticResigningAllowed=False,allocationTransferred=False,
        fundsAvailableForNewEntry=False,walletWideReservationsKnown=False,
        currentWalletBalanceEstablished=False,nextCycleAuthorized=False,
        runtimeIntegrated=False,executionApproved=False,
        limitations=[
            'Internal devnet integration; public CLI uses only synthetic evidence.',
            'At most four existing-signature receipt reads and four fresh balance reads; no polling or resubmission.',
            'Accounting and closure commit separately. Inspect durable state after any ambiguous response.',
            'Scoped closure releases only recorded proceeds and unused fees; protected inventory is excluded.',
            'Closed is a historical ledger state, not current solvency or permission for a new trade.',
            'No wallet-wide allocator, mainnet integration, runtime deployment or profitability claim.'])


def _snapshot(home,wallet,pool,clock,monotonic):
    """One pinned read-only view; cross-check accounting, closure and aggregate holds."""
    started=monotonic();wall=clock()
    with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
        book=submission.transport._open(root,wallet,pool,clock)
        try:
            with lifecycle.admission_read_lock(book.j.path):
                phase,original,amounts,stages,ids,state=lifecycle.projection(book,root,wallet,pool,clock)
                stop=submission.handoff.stopped(root,book)
                closed=closure.public(closure.replay(book,root,wallet,pool,clock))
                settled=None
                if stages['exitTransport'] is not None:
                    settled=accounting.public(accounting.review(book),accounting.saved(book.db,clock()),stop=stop)
                    check(settled['recordSha256']==ids['exitAccountingSha256'] or
                          not settled['accountingUsable'],'exit-settlement-accounting-binding')
                if closed['closureRecorded']:
                    check(phase=='closed' and settled is not None and settled['accountingUsable'] and
                          closed['settlement']['exitAccountingSha256']==settled['recordSha256'] and
                          closed['recordSha256']==ids['closureSha256'] and amounts['scopedClosureRecorded'] and
                          amounts['feeHeldLamports']==amounts['sourceProceedsHeldAtomic']=='0',
                          'exit-settlement-closure-binding')
                stamp=clock();uint(stamp,2**53-1,'exit-settlement-clock',minimum=wall)
                check(0<=monotonic()-started<=lifecycle.MAX_READ_MS/1000,'exit-settlement-read-budget')
                return dict(state=closed['state'] if closed['closureRecorded'] else
                    ('exit-settled-closure-stopped' if stop and settled is not None and settled['state']=='exit-position-flat-held'
                     else settled['state'] if settled is not None else phase),
                    phase=phase,coherent=phase!='quarantined',stopRequested=stop,observedAtMs=stamp,
                    accounting=settled,closure=closed,scopedAccounting=amounts,recordIdentity=ids,
                    closureRecorded=closed['closureRecorded'],scopedCommitmentsReleased=closed['scopedCommitmentsReleased'])
        finally:book.close()


@view.cycles.binding.operation
@fresh_signing.timing.signature_replay
def status(home,wallet,pool,*,clock=view.now,monotonic=time.monotonic):
    """Read-only recovery of durable facts, including after STOP or expiry."""
    result=base();result.update(_snapshot(home,wallet,pool,clock,monotonic));return result


@view.cycles.binding.operation
@fresh_signing.timing.signature_replay
def advance(home,wallet,pool,*,close_exit=False,receipt_opener=None,balance_opener=None,
            clock=view.now,monotonic=time.monotonic):
    """Observe existing exit, settle effects, optionally collect and close.

    No report importer. Exact True requests the independent fresh-balance closure
    gate; default reconciliation keeps all scoped commitments held.
    """
    check(type(close_exit) is bool,'explicit-exit-closure-choice')
    r=base();clients=[];observations=[]
    try:
        r.update(_snapshot(home,wallet,pool,clock,monotonic))
        # No exit signer/send boundary can be manufactured by reconciliation.
        if r['closureRecorded'] or not r['coherent'] or r['accounting'] is None:return r
        r['stage']='receipt'
        r['receipt']=submission.recover(home,wallet,pool,opener=receipt_opener,clock=clock,_rpc_sink=clients.append)
        r['stage']='accounting';r['accountingAppliedThisRun']=None
        applied=accounting.apply(home,wallet,pool,clock=clock)
        r['accountingAppliedThisRun']=applied['appliedThisRun']
        r.update(_snapshot(home,wallet,pool,clock,monotonic))
        if (not close_exit or not r['coherent'] or not r['accounting']['accountingUsable'] or
                r['accounting']['state']!='exit-position-flat-held' or r['stopRequested'] or r['closureRecorded']):return r
        r['stage']='balance-and-closure';r['closureAppliedThisRun']=None
        closed=closure.collect_and_close(home,wallet,pool,opener=balance_opener,clock=clock,
            monotonic=monotonic,_observation_sink=observations.append)
        r['closureAppliedThisRun']=closed['appliedThisRun']
        r.update(_snapshot(home,wallet,pool,clock,monotonic))
        if not r['closureRecorded']:
            r.update(state='exit-settled-closure-unavailable',diagnosticCode=closed.get('diagnosticCode') or 'exit-closure-unavailable')
        r['stage']='complete'
    except view.ERRORS:
        # Do not present a prior projection as current or assert rollback across
        # independent stages; read-only status can recover a completed close.
        r.update(state='inspection-required',coherent=False,diagnosticCode='exit-settlement-evidence-unavailable',
            closureRecorded=None,scopedCommitmentsReleased=None,phase=None,observedAtMs=None,
            scopedAccounting=None,recordIdentity=None,accounting=None,closure=None)
    finally:
        r['receiptRequestsThisRun']=sum(len(c.calls) for c in clients)
        r['balanceRequestsThisRun']=sum(o['networkRequests'] for o in observations)
        r['networkRequests']=r['receiptRequestsThisRun']+r['balanceRequestsThisRun']
        if observations:r['balanceObservation']=observations[-1]
    return r
