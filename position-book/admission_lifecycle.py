"""Read-only scoped admission lifecycle. No allocation, RPC or execution capability."""
import time

import exit_closure as closure
from admission_recovery import admission_read_lock
from contract import atomic, digest, uint
from core import check
from journal import read_only_journals
from wire import verify_wire

VERSION='admission-lifecycle-1'
view=closure.view
entry=closure.balance.accounting.entry
exit_accounting=closure.balance.accounting
preparation=exit_accounting.submission.handoff.preparation
signing=exit_accounting.submission.handoff
MAX_READ_MS=120000
ENTRY_TABLES={'admission_submission','admission_submission_ack','admission_rpc_captures',
              'admission_receipt_events','admission_receipt_raw','admission_entry_accounting'}
EXIT_TRANSPORT={'admission_exit_submission','admission_exit_submission_ack','admission_exit_rpc_captures'}
EXIT_TABLES=EXIT_TRANSPORT|{'admission_successor_transport','admission_successor_signing','admission_exit_successor','admission_exit_retirement','admission_exit_continuation','admission_exit_replacement','admission_exit_preparation','admission_exit_signing','admission_exit_accounting','admission_exit_closure'}
KNOWN={'admission_policy','admission_events'}|ENTRY_TABLES|EXIT_TABLES


def base():
    return dict(format=VERSION,state='lifecycle-unavailable',coherent=False,phase=None,blockingReasons=[],
        capturedAtMs=None,elapsedMs=None,stopRequested=None,admissionEvidenceExpired=None,
        originalAdmission=None,scopedAccounting=None,stages=None,recordIdentity=None,
        sourceStateChanged=False,databaseConnectionsReadOnly=True,networkRequests=0,
        privateKeyAccessed=False,signaturesCreated=0,transactionsSent=0,
        reservationsReleasedThisRun=False,allocationTransferred=False,fundsAvailableForNewEntry=False,
        walletWideReservationsKnown=False,currentWalletBalanceEstablished=False,
        nextCycleAuthorized=False,executionApproved=False,runtimeIntegrated=False,
        limitations=['Historical scoped ledger accounting, not a live wallet or portfolio balance.',
            'Amounts are atomic units; different tokens and native fees are never added together.',
            'Original reservation caps are history, not additional current holds.',
            'Missing settlement keeps commitments held; unknown quantities remain null.',
            'A recorded scoped release is not an allocator credit or new-entry permission.'])


def original(book,state):
    principal=atomic(state['reservedPrincipalAtomic'],'lifecycle-principal',positive=True)
    fee=atomic(state['reservedFeeLamports'],'lifecycle-fee',positive=True)
    entry_cap=atomic(state['entryFeeCapLamports'],'lifecycle-entry-cap',positive=True)
    exit_cap=atomic(state['exitFeeCapLamports'],'lifecycle-exit-cap',positive=True)
    attempts=state['maximumExitAttempts'];uint(attempts,3,'lifecycle-attempts',minimum=1)
    p=book.policy
    check(principal==int(p['scope']['amountIn']) and attempts==p['maximumExitAttempts'] and
          exit_cap==int(p['maximumExitFeeLamports']) and fee==entry_cap+attempts*exit_cap and
          fee<=int(p['maximumTotalFeeLamports']),'lifecycle-original-conservation')
    a=p['scope']['accounts']
    return dict(sourceAccount=a['source'],sourceMint=a['inputMint'],acquiredAccount=a['destination'],
        acquiredMint=a['outputMint'],principalAtomic=str(principal),feeCommitmentLamports=str(fee),
        maximumExitAttempts=attempts,basis='original-reservation-history-not-extra-holds')


def _projection(book,root,wallet,pool,clock):
    """Caller holds source lock and a separate shared SQLite read lock."""
    state,count,head,at=book.read();now=clock()
    check(state is not None and state.get('reservedAtMs') is not None,'lifecycle-funded-admission-required')
    uint(now,2**53-1,'lifecycle-clock',minimum=at)
    tables=book.db.execute("SELECT name,type FROM sqlite_master WHERE name LIKE 'admission_%' LIMIT 65").fetchall()
    check(len(tables)<=64 and all(r['name'] in KNOWN and r['type']=='table' for r in tables),'lifecycle-unsupported-schema')
    present={r['name'] for r in tables}
    source=view.read_locked(root,wallet,pool,clock,_closed_history=True)
    check(source['phase']=='closed' and source['nativeHeldLamports']=='0' and
          all(t['heldAtomic']=='0' for t in source['tokenAccounts']) and
          source['ledgerHeadSha256']==state['ledgerHeadSha256'] and
          source['cycleBindingSha256']==state['cycleBindingSha256'],'lifecycle-source-conflict')
    orig=original(book,state)
    amounts=dict(sourcePrincipalHeldAtomic=orig['principalAtomic'],sourcePrincipalSpentAtomic=None,
        sourceProceedsHeldAtomic=None,ownedAcquiredHeldAtomic=None,protectedAcquiredInventoryAtomic=None,
        feeHeldLamports=orig['feeCommitmentLamports'],feePaidLamports=None,
        sourceProceedsReleasedAtomic='0',unusedFeeReleasedLamports='0',
        protectedInventoryReleasedAtomic='0',scopedClosureRecorded=False,
        basis='reservation-accounting-before-entry-settlement')
    stages=dict(admission=state['state'],entryTransport=None,entryAccounting=None,
        exitPreparation=None,exitSigning=None,exitTransport=None,exitAccounting=None,closure=None)
    ids=dict(admissionHeadSha256=head,entryAccountingSha256=None,exitAccountingSha256=None,closureSha256=None)
    phase={'reserved':'entry-reserved','signing-unknown':'entry-signing-unresolved',
           'signed-recorded':'entry-signed-not-submitted','stopped':'admission-stopped',
           'quarantined':'quarantined'}[state['state']]
    if phase=='quarantined':return phase,orig,None,stages,ids,state
    if state.get('signingRequest') is not None:
        check(digest(state['signingRequest'])==state.get('signingRequestSha256'),'lifecycle-signing-request')
    if state.get('signedWireBase64') is not None:
        wire=verify_wire(state['signedWireBase64'])
        check(wire['requiredSignatures']==1 and wire['wallet']==wallet and
              wire['wireMessageSha256']==state['messageSha256'] and
              wire['wireSha256']==state['signedWireSha256'] and wire['signatures'][0]==state['signature'],'lifecycle-signed-binding')
    if state.get('accountingHandoff') is None:
        check(not present.intersection(ENTRY_TABLES|EXIT_TABLES),'lifecycle-orphan-evidence')
        return phase,orig,amounts,stages,ids,state
    esource=entry.review(book);erecord=entry.saved(book.db,clock());er=entry.public(esource,erecord)
    stages.update(entryTransport=esource['transportState'],entryAccounting=er['state'])
    if esource['transportState']=='quarantined':return 'quarantined',orig,None,stages,ids,state
    phase='entry-not-submitted' if esource['transportState']=='not-attempted' else 'entry-unresolved'
    if esource['accounting'] is not None:phase='entry-receipt-awaiting-accounting'
    if not er['accountingUsable']:
        check(not present.intersection(EXIT_TABLES),'lifecycle-exit-before-entry')
        return phase,orig,amounts,stages,ids,state
    a=erecord['accounting'];ids['entryAccountingSha256']=digest(erecord)
    amounts.update(sourcePrincipalHeldAtomic=a['sourcePrincipalHeldAtomic'],sourcePrincipalSpentAtomic=a['sourcePrincipalSpentAtomic'],
        sourceProceedsHeldAtomic='0',ownedAcquiredHeldAtomic=a['ownedAcquiredAtomic'],
        protectedAcquiredInventoryAtomic=a['preexistingDestinationAtomic'],feeHeldLamports=a['feeCommitmentRemainingLamports'],
        feePaidLamports=a['entryFeePaidLamports'],basis='entry-settled-exit-not-settled')
    phase='entry-open' if a['state']=='entry-position-open' else 'entry-failed-held'
    if phase=='entry-failed-held':
        check(not present.intersection(EXIT_TABLES),'lifecycle-exit-after-failed-entry')
        return phase,orig,amounts,stages,ids,state
    prepared=preparation.saved(book,clock())
    if prepared is not None:stages['exitPreparation']='recorded';phase='exit-prepared'
    signed=signing.read(book,clock())
    if signed is not None:
        stages['exitSigning']=signed['state'];phase=signed['state']
        if signed['state']=='exit-signing-quarantined':return 'quarantined',orig,None,stages,ids,state
    if signed is None or signed['signed'] is None:
        check(not present.intersection(EXIT_TRANSPORT|{'admission_exit_accounting','admission_exit_closure'}),'lifecycle-exit-before-signing')
        return phase,orig,amounts,stages,ids,state
    xsource=exit_accounting.review(book);xrecord=exit_accounting.saved(book.db,clock())
    xr=exit_accounting.public(xsource,xrecord)
    stages.update(exitTransport=xsource['transportState'],exitAccounting=xr['state'])
    if xr['state']=='quarantined':return 'quarantined',orig,None,stages,ids,state
    phase='exit-signed-not-submitted' if xsource['transportState']=='not-attempted' else 'exit-unresolved'
    if xsource['accounting'] is not None:phase='exit-receipt-awaiting-accounting'
    if not xr['accountingUsable']:
        check('admission_exit_closure' not in present,'lifecycle-closure-before-accounting')
        return phase,orig,amounts,stages,ids,state
    x=xrecord['accounting'];ids['exitAccountingSha256']=digest(xrecord)
    amounts.update(sourceProceedsHeldAtomic=x['sourceProceedsHeldAtomic'],ownedAcquiredHeldAtomic=x['ownedAcquiredResidualAtomic'],
        protectedAcquiredInventoryAtomic=x['protectedAcquiredInventoryAtomic'],feeHeldLamports=x['feeCommitmentRemainingLamports'],
        feePaidLamports=x['totalFeePaidLamports'],basis='exit-settled-commitments-held')
    phase=x['state']
    record=closure.replay(book,root,wallet,pool,clock)
    if record is not None:
        c=record['settlement'];ids['closureSha256']=digest(record);stages['closure']=c['state'];phase='closed'
        amounts.update(sourceProceedsHeldAtomic=c['remainingProceedsHeldAtomic'],feeHeldLamports=c['remainingFeeHeldLamports'],
            sourceProceedsReleasedAtomic=c['sourceProceedsReleasedAtomic'],unusedFeeReleasedLamports=c['unusedFeeReleasedLamports'],
            scopedClosureRecorded=True,basis='historical-scoped-closure-not-wallet-spendability')
    # Independent aggregate checks reject contradictory projections, including a
    # future change that accidentally adds old reservation caps to current holds.
    check(int(orig['feeCommitmentLamports'])==sum(int(amounts[k]) for k in
        ('feePaidLamports','feeHeldLamports','unusedFeeReleasedLamports')),'lifecycle-fee-conservation')
    check(int(x['sourceProceedsHeldAtomic'])==int(amounts['sourceProceedsHeldAtomic'])+
          int(amounts['sourceProceedsReleasedAtomic']),'lifecycle-proceeds-conservation')
    return phase,orig,amounts,stages,ids,state


def projection(book,root,wallet,pool,clock):
    result=_projection(book,root,wallet,pool,clock)
    from exit_retirement_guard import present
    from retired_exit_successor import present as successor_present,replay as successor_replay
    import successor_signing_handoff as successor_signing
    import successor_submission as successor_transport
    if not present(book):
        check(not successor_transport.present(book),'lifecycle-orphan-successor-transport')
        check(not successor_signing.present(book),'lifecycle-orphan-successor-signing')
        check(not successor_present(book),'lifecycle-orphan-successor')
        return result
    phase,orig,amounts,stages,ids,state=result
    check(phase=='exit-signed-not-submitted' and amounts is not None,'lifecycle-retirement-conflict')
    from exit_retirement import replay_for_projection
    record=replay_for_projection(book,root,wallet,pool,clock,amounts)
    stages['exitRetirement']='expired-attempt-retired-held'
    ids['exitRetirementSha256']=digest(record)
    successor=successor_replay(book,root,wallet,pool,clock,amounts)
    if successor is not None:
        stages['exitSuccessor']='unsigned-successor-held'
        ids['exitSuccessorSha256']=digest(successor)
        signing=successor_signing.read(book,successor,clock())
        transport=successor_transport.replay(book,successor,signing,clock())
        if transport is not None:
            stages['exitSuccessorTransport']=transport['state']
            ids['exitSuccessorTransportHeadSha256']=transport['headSha256']
            if transport['state']=='quarantined':return 'quarantined',orig,amounts,stages,ids,state
        if signing is not None:
            stages['exitSuccessorSigning']=signing['state']
            ids['exitSuccessorSigningHeadSha256']=signing['headSha256']
            if signing['state']=='successor-signing-quarantined':
                return 'quarantined',orig,amounts,stages,ids,state
    else:
        check(not successor_transport.present(book),'lifecycle-orphan-successor-transport')
        check(not successor_signing.present(book),'lifecycle-orphan-successor-signing')
    return 'exit-retired-held',orig,amounts,stages,ids,state


@view.cycles.binding.operation
def inspect(home,wallet,pool,*,clock=view.now,monotonic=time.monotonic):
    result=base();start=monotonic();wall=clock()
    try:
        with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
            book=entry.submission._open(root,wallet,pool,clock)
            try:
                with admission_read_lock(book.j.path):
                    # A separate read lock pins the file while existing validators
                    # open their own read transactions; no nested BEGIN is needed.
                    book.read()
                    phase,orig,amounts,stages,ids,state=projection(book,root,wallet,pool,clock)
                    stamp=clock();elapsed=(monotonic()-start)*1000
                    uint(stamp,2**53-1,'lifecycle-clock',minimum=wall)
                    check(0<=elapsed<=MAX_READ_MS,'lifecycle-read-deadline')
                    stop=view.cycles.c.submit.swap.stop(root) or state['state']=='stopped'
                    result.update(state='lifecycle-quarantined' if phase=='quarantined' else 'lifecycle-consistent',
                        coherent=phase!='quarantined',phase=phase,originalAdmission=orig,scopedAccounting=amounts,
                        stages=stages,recordIdentity=ids,capturedAtMs=stamp,elapsedMs=round(elapsed,3),
                        stopRequested=stop,admissionEvidenceExpired=stamp>=state['validUntilExclusiveMs'])
                    if phase=='quarantined':result['blockingReasons']=['quarantined-evidence']
            finally:book.close()
    except view.ERRORS:
        result=base();result['blockingReasons']=['lifecycle-evidence-unavailable']
    return result
