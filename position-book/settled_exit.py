"""Collected entry settlement -> separately collected unsigned exit preparation.

Internal coordinator only. No signer, sender, scheduling, refresh or allocation
release. Successful intermediate commits survive later failures for inspection.
"""
import entry_accounting as entry
import admission_exit_collection as exits
import fresh_signing
from core import check
from journal import read_only_journals

VERSION='settled-exit-integration-1'
view=exits.exit.view


def base():
    return dict(format=VERSION,state='inspection-required',stage='receipt',diagnosticCode=None,
        receipt=None,accounting=None,exitPreparation=None,exitCollection=None,
        receiptRequestsThisRun=0,exitRequestsThisRun=0,networkRequests=0,
        accountingAppliedThisRun=False,exitCreatedThisRun=False,
        signaturesCreated=0,transactionsSent=0,privateKeyAccessed=False,
        automaticRetryAllowed=False,automaticResigningAllowed=False,
        allocationTransferred=False,reservationReleased=False,fundsAvailableForNewEntry=False,
        runtimeIntegrated=False,executionApproved=False,signingApproved=False,nextCycleAuthorized=False,
        preparedExitUsableForSigning=False,sourceStateChanged=False,
        limitations=[
            'Internal devnet composition; public CLI is synthetic only.',
            'At most four receipt and twenty unsigned exit requests per invocation; no polling loop.',
            'The exit is a new observation after entry settlement, never reused entry market evidence.',
            'Only the acquired delta is owned; preexisting inventory and remaining fee commitments stay protected.',
            'Intermediate receipt/accounting commits survive later failure. Inspect before further action.',
            'Existing exit preparation is immutable even when expired; no replacement or execution capability.',
            'No signer, sender, allocation reuse, automatic delay policy, mainnet or profitability approval.'])


def _snapshot(home,wallet,pool,clock):
    """One locked read-only projection; report objects never authorize a write."""
    with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
        book=entry.submission._open(root,wallet,pool,clock)
        try:
            stopped=view.cycles.c.submit.swap.stop(root) or book.read()[0]['state']=='stopped'
            accounting=entry.public(entry.review(book),entry.saved(book.db,clock()),stopped=stopped)
            prepared=exits.exit.public(exits.exit.saved(book,clock()),clock(),stopped=stopped)
            if prepared['recorded'] and accounting['accountingUsable']:
                b=prepared['binding'];a=accounting['accounting']
                check(accounting['state']=='entry-position-open' and
                      b['entryAccountingSha256']==accounting['recordSha256'] and
                      b['entryReceiptIdentity']==a['receiptIdentity'] and
                      b['quantityAtomic']==a['ownedAcquiredAtomic'] and
                      b['feeCommitmentRemainingLamports']==a['feeCommitmentRemainingLamports'],
                      'settled-exit-binding')
            return accounting,prepared
        finally:book.close()


def project(r,accounting,prepared):
    r.update(accounting=accounting,exitPreparation=prepared)
    if not accounting['accountingUsable'] or accounting['state']!='entry-position-open':
        r['state']=accounting['state']
    elif prepared['recorded']:r['state']=prepared['state']
    elif accounting['stopRequested']:r['state']='entry-settled-exit-stopped'
    else:r['state']='entry-settled-exit-not-prepared'


@view.cycles.binding.operation
@fresh_signing.timing.signature_replay
def status(home,wallet,pool,*,clock=view.now):
    """No RPC or writes. Replay both records under one cooperating lock."""
    r=base();r['stage']='status'
    project(r,*_snapshot(home,wallet,pool,clock))
    return r


@view.cycles.binding.operation
@fresh_signing.timing.signature_replay
def advance(home,wallet,pool,*,prepare_exit=False,receipt_opener=None,exit_opener=None,
            clock=view.now,monotonic=fresh_signing.timing.time.monotonic):
    """Reconcile existing entry; only explicit True requests a fresh unsigned exit.

    No entry collection, signer or sender is called. Re-entry can observe an
    unresolved receipt but cannot resend it or replace an existing exit record.
    """
    check(type(prepare_exit) is bool,'explicit-exit-preparation-choice')
    r=base();clients=[];observations=[]
    try:
        r['receipt']=entry.submission.recover(home,wallet,pool,opener=receipt_opener,
            clock=clock,_rpc_sink=clients.append)
        r['stage']='accounting'
        settled=entry.apply(home,wallet,pool,clock=clock)
        r['accountingAppliedThisRun']=settled['appliedThisRun']
        project(r,*_snapshot(home,wallet,pool,clock))
        if (not prepare_exit or r['accounting']['state']!='entry-position-open' or
                not r['accounting']['accountingUsable'] or r['accounting']['stopRequested'] or
                r['exitPreparation']['recorded']):return r
        r['stage']='exit-collection'
        prepared=exits.collect_and_prepare(home,wallet,pool,opener=exit_opener,clock=clock,
            monotonic=monotonic,_observation_sink=observations.append)
        r['exitCreatedThisRun']=prepared.get('createdThisRun',False)
        project(r,*_snapshot(home,wallet,pool,clock))
        if not r['exitPreparation']['recorded']:
            r.update(state='entry-settled-exit-unavailable',diagnosticCode='exit-collection-unavailable')
        r['stage']='complete'
    except view.ERRORS:
        # Do not infer rollback of the earlier receipt or accounting from a later
        # exception; status separately replays the durable facts without RPC.
        r.update(state='inspection-required',diagnosticCode='settled-exit-evidence-unavailable')
    finally:
        r['receiptRequestsThisRun']=sum(len(c.calls) for c in clients)
        r['exitRequestsThisRun']=sum(x['networkRequests'] for x in observations)
        if observations:r['exitCollection']=observations[-1]
        r['networkRequests']=r['receiptRequestsThisRun']+r['exitRequestsThisRun']
    return r
