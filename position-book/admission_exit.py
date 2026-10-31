"""One immutable fresh exit preparation in the entry's own admission ledger.

Internal raw-evidence seam only. No new collector, signer, sender, retry or release.
Public reports are not input capabilities. Historical preparation is not a permit.
"""
from copy import deepcopy
import json

import entry_accounting as entry
import preflight
import quote_binding
import unsigned_simulation
from pre_sign_admission import MAX_EVIDENCE_BYTES, encoded
from simulation_baseline import BASELINE
from contract import atomic, digest, fields, uint
from core import check
from cpmm_quote import derive
from fresh_packet import scope_check
from swap_rehearsal import scope_for
from state import audit
from journal import read_only_journals

VERSION='admission-exit-preparation-1'
TABLE='admission_exit_preparation'
MAX_RECORD=MAX_EVIDENCE_BYTES+16384
view=entry.submission.handoff.bridge.view


def owner(book, now):
    source=entry.review(book);record=entry.saved(book.db,now)
    result=entry.public(source,record)
    check(result['accountingUsable'] and result['state']=='entry-position-open','exit-open-accounting-required')
    a=record['accounting']
    check(a['exitAttemptsConsumed']==0 and int(a['ownedAcquiredAtomic'])>0,'exit-first-attempt-only')
    return record,source['reservation']


def review(book,evidence,now):
    """Recompute current reverse economics, account bytes, deployment and effects."""
    uint(now,2**53-1,'exit-clock',minimum=1)
    check(len(encoded(evidence).encode())<=MAX_EVIDENCE_BYTES,'exit-evidence-cap')
    fields(evidence,{'initialPool','packet','capture','price','simulationItem',
                     'simulationStartedAtMs','simulationReceivedAtMs','completedAtMs'},'exit-evidence-schema')
    record,reservation=owner(book,now);a=record['accounting']
    packet=evidence['packet'];capture=evidence['capture'];price=evidence['price']
    scope=scope_for(packet['policy']);scope_check(scope)
    expected=deepcopy(book.policy['scope'])
    for left,right in (('source','destination'),('inputMint','outputMint'),('inputVault','outputVault')):
        expected['accounts'][left],expected['accounts'][right]=expected['accounts'][right],expected['accounts'][left]
    expected['amountIn']=a['ownedAcquiredAtomic']
    expected['minimumAmountOut']=scope['minimumAmountOut']
    expected['maxTotalFeeLamports']=scope['maxTotalFeeLamports']
    check(scope==expected,'exit-exact-reverse-scope')
    check(scope['accounts']['source']==a['acquiredAccount'] and scope['accounts']['destination']==a['sourceAccount'],
          'exit-owned-account-binding')
    cap=atomic(scope['maxTotalFeeLamports'],'exit-fee-cap',positive=True)
    held=atomic(a['feeCommitmentRemainingLamports'],'exit-held-fees',positive=True)
    attempt_cap=atomic(reservation['exitFeeCapLamports'],'exit-attempt-cap',positive=True)
    check(cap<=attempt_cap and held>=int(a['exitAttemptFeeHeldLamports'])>=attempt_cap,'exit-budget-shortfall')
    # Decode the signed entry itself; never infer its blockhash from a report.
    from contract import decode_wire
    old_hash=decode_wire(reservation['signedWireBase64'])[4]['transaction']['message']['recentBlockhash']
    check(packet['policy']['blockhash']!=old_hash,'exit-entry-blockhash-reused')
    for key in ('simulationStartedAtMs','simulationReceivedAtMs','completedAtMs'):
        uint(evidence[key],2**53-1,'exit-clock',minimum=1)
    check(record['recordedAtMs']<=evidence['initialPool']['startedAtMs'] and
          capture['finishedAtMs']<=evidence['simulationStartedAtMs']<=evidence['simulationReceivedAtMs']
          <=evidence['completedAtMs']<=now,'exit-observation-order')
    computed=derive(evidence['initialPool'],scope,slippage_bps=100,now_ms=now)
    check(computed==price,'exit-price-binding')
    check(capture['packet']==packet,'exit-packet-binding')
    checked=preflight._review(capture,deepcopy(BASELINE),now)
    check(checked['state']=='preflight-evidence-consistent','exit-preflight')
    raw,_=preflight.split_capture(capture);state=audit(raw)
    check(state['state']=='policy-state-consistent','exit-account-state')
    check(price['quote']['contextSlot']>=a['receiptSlot'] and state['snapshotSlot']>=a['receiptSlot'],
          'exit-state-before-entry')
    # Protect preexisting inventory and all surplus. The exact acquired delta is
    # the only quantity allocated to this exit; external withdrawals fail closed.
    balance=int(state['sourceBalanceAtomic']);quantity=int(a['ownedAcquiredAtomic'])
    check(balance>=quantity+int(a['preexistingDestinationAtomic']),'exit-owned-inventory-shortfall')
    mints={state['poolState']['mint'+str(i)]:row for i,row in enumerate(state['mints'])}
    check(mints[a['acquiredMint']]['decimals']==a['acquiredDecimals'] and
          mints[a['sourceMint']]['decimals']==a['sourceDecimals'],'exit-mint-decimals')
    r=dict(wallet=a['wallet'],source=a['acquiredAccount'],inputMint=a['acquiredMint'],
           otherTokenAtomic=str(balance-quantity),otherNativeLamports=str(held-cap),asOfMs=now)
    binding=quote_binding._review(dict(format=quote_binding.VERSION,quote=price['quote'],capture=raw,
        reservations=r,maxSlippageBps=100),now_ms=now,current_local_reservations=True)
    check(binding['state']=='declared-quote-state-consistent','exit-funding-or-quote-binding')
    effects=unsigned_simulation.review(packet,capture,price,evidence['simulationItem'],now_ms=now)
    b=binding['binding']
    check(effects['messageSha256']==b['messageSha256']==checked['wireMessageSha256'] and
          effects['simulationSlot']>=a['receiptSlot'] and effects['feeLamports']==b['rpcMessageFeeLamports'] and
          int(effects['feeLamports'])<=cap,'exit-simulation-binding')
    deadline=min(checked['validUntilExclusiveMs'],b['validUntilExclusiveMs'])
    check(now<deadline,'exit-deadline-elapsed')
    return dict(format=VERSION,entryAccountingSha256=digest(record),entryReceiptIdentity=a['receiptIdentity'],
        evidenceSha256=digest(evidence),messageSha256=b['messageSha256'],scopeSha256=digest(scope),
        quantityAtomic=str(quantity),protectedInventoryAtomic=str(balance-quantity),
        minimumOutputAtomic=scope['minimumAmountOut'],quotedOutputAtomic=price['quote']['outAmount'],
        feeCapLamports=str(cap),observedFeeLamports=effects['feeLamports'],
        feeCommitmentRemainingLamports=str(held),otherFeeCommitmentsHeldLamports=str(held-cap),
        attemptNumber=1,attemptsConsumed=0,validUntilExclusiveMs=deadline)


def saved(book,now):
    exists=book.db.execute('SELECT type FROM sqlite_master WHERE name=?',(TABLE,)).fetchone()
    if not exists:return None
    check(exists[0]=='table','exit-preparation-table')
    rows=book.db.execute('SELECT id,CASE WHEN length(value)<=? THEN value ELSE NULL END AS value,hash FROM admission_exit_preparation LIMIT 2',(MAX_RECORD,)).fetchall()
    check(len(rows)==1 and rows[0]['id']==1 and type(rows[0]['value']) is str,'exit-preparation-record')
    v=json.loads(rows[0]['value']);fields(v,{'format','recordedAtMs','evidence','binding'},'exit-record-schema')
    check(v['format']==VERSION+'-record' and encoded(v)==rows[0]['value'] and digest(v)==rows[0]['hash'],
          'exit-record-integrity')
    uint(v['recordedAtMs'],now,'exit-record-clock',minimum=1)
    check(review(book,v['evidence'],v['recordedAtMs'])==v['binding'],'exit-record-source-conflict')
    return v


def public(record,now,*,stopped=False,created=False):
    state='exit-not-prepared'
    if record is not None:
        state='exit-preparation-expired' if now>=record['binding']['validUntilExclusiveMs'] else 'exit-prepared-research-only'
        if stopped:state='exit-preparation-stopped'
    return dict(format=VERSION,state=state,recorded=record is not None,createdThisRun=created,
        recordSha256=None if record is None else digest(record),
        binding=None if record is None else deepcopy(record['binding']),stopRequested=stopped,
        rawEvidenceReplayed=record is not None,allocationOwner='same-admission-ledger',
        attemptsConsumed=0,reservationReleased=False,allocationTransferred=False,
        signingApproved=False,executionApproved=False,validForSubmission=False,
        networkRequests=0,signaturesCreated=0,transactionsSent=0,privateKeyAccessed=False,
        runtimeIntegrated=False,productionLedgerUpdated=False,nextCycleAuthorized=False,
        walletWideReservationsKnown=False,
        limitations=['One immutable first-exit preparation; no refresh, retry, signer or sender.',
          'Raw captures are supplied by an internal caller; live collection and provenance integration remain pending.',
          'Historical evidence expires; a passed preparation is not a current execution permit.',
          'Controlled devnet direct pool only; no profitability or deployed-source equivalence claim.'])


@view.cycles.binding.operation
def prepare(home,wallet,pool,evidence,*,clock=view.now):
    check(len(encoded(evidence).encode())<=MAX_EVIDENCE_BYTES,'exit-evidence-cap');evidence=deepcopy(evidence)
    with view.cycles.c.source_lock(home,wallet) as root:
        check(not view.cycles.c.submit.swap.stop(root),'stop-marker-present')
        book=entry.submission._open(root,wallet,pool,clock)
        try:
            with book.j.transaction():
                with read_only_journals():
                    reader=entry.submission._open(root,wallet,pool,clock)
                    try:
                        check(reader.read()[0]['state']=='signed-recorded','exit-admission-stopped')
                        record=saved(reader,clock())
                        if record is not None:
                            check(record['evidence']==evidence,'exit-already-prepared')
                            return public(record,clock())
                        source=view.read_locked(root,wallet,pool,clock)
                        _,reservation=owner(reader,clock())
                        check(source['wallet']==wallet and source['pool']==pool and
                              source['phase']=='closed' and source['nativeHeldLamports']=='0' and
                              all(x['heldAtomic']=='0' for x in source['tokenAccounts']) and
                              source['ledgerHeadSha256']==reservation['ledgerHeadSha256'] and
                              source['cycleBindingSha256']==reservation['cycleBindingSha256'],'exit-historical-source-changed')
                        now=clock();binding=review(reader,evidence,now)
                    finally:reader.close()
                check(now<=clock()<binding['validUntilExclusiveMs'],'exit-deadline-elapsed')
                check(not view.cycles.c.submit.swap.stop(root),'stop-marker-present')
                record=dict(format=VERSION+'-record',recordedAtMs=now,evidence=evidence,binding=binding)
                check(len(encoded(record).encode())<=MAX_RECORD,'exit-record-cap')
                book.db.execute('CREATE TABLE admission_exit_preparation (id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL,hash TEXT NOT NULL)')
                book.db.execute('INSERT INTO admission_exit_preparation VALUES(1,?,?)',(encoded(record),digest(record)))
                # Deadline includes serialization and writing, before commit.
                end=clock();check(now<=end<binding['validUntilExclusiveMs'],'exit-deadline-elapsed')
                check(not view.cycles.c.submit.swap.stop(root),'stop-marker-present')
                return public(record,end,created=True)
        finally:book.close()


def status(home,wallet,pool,*,clock=view.now):
    with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
        book=entry.submission._open(root,wallet,pool,clock)
        try:return public(saved(book,clock()),clock(),stopped=view.cycles.c.submit.swap.stop(root) or book.read()[0]['state']=='stopped')
        finally:book.close()
