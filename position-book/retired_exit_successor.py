"""One separate unsigned successor contract after retirement; internal API only.

No live producer or signer is wired. The old active preparation and sender stay
retired. Public reports are never accepted as a source of candidate evidence.
"""
from copy import deepcopy
import json
import time

import retired_exit_replan as replan
import admission_exit_collection as collection
from contract import digest,fields,uint
from core import check
from journal import read_only_journals

VERSION='retired-exit-successor-1'
TABLE='admission_exit_successor'
retirement=replan.retirement
expiry=replan.expiry
history=replan.history
view=replan.view
preparation=collection.exit
MAX_RECORD=preparation.MAX_RECORD+retirement.MAX_RECORD+8192


def present(book):
    return book.db.execute('SELECT type FROM sqlite_master WHERE name=?',(TABLE,)).fetchone()


def row(book):
    found=present(book)
    if found is None:return None
    check(found[0]=='table','successor-table')
    rows=book.db.execute('SELECT id,CASE WHEN length(value)<=? THEN value ELSE NULL END value,hash FROM admission_exit_successor LIMIT 2',(MAX_RECORD,)).fetchall()
    check(len(rows)==1 and rows[0]['id']==1 and type(rows[0]['value']) is str,'successor-row')
    value=json.loads(rows[0]['value'])
    check(preparation.encoded(value)==rows[0]['value'] and digest(value)==rows[0]['hash'],'successor-integrity')
    return value


def fresh_review(ctx,retired,proof,now):
    fields(proof,{'contextSha256','startedAtMs','observedAtMs','rpcEvidence'},'successor-expiry-proof')
    check(proof['contextSha256']==digest(ctx),'successor-expiry-context')
    uint(proof['startedAtMs'],proof['observedAtMs'],'successor-expiry-start',minimum=retired['recordedAtMs'])
    uint(proof['observedAtMs'],now,'successor-expiry-observed',minimum=proof['startedAtMs'])
    check(now-proof['observedAtMs']<=30000,'successor-expiry-age')
    # Reuse the exact eight-response schema and semantic retirement validator.
    at=dict(format=retirement.VERSION,recordedAtMs=proof['observedAtMs'],
        preparationSha256=ctx['identity']['preparationSha256'],**deepcopy(proof))
    retirement.validate(at,ctx,now)
    observed=expiry.assess(ctx,proof['rpcEvidence'],proof['startedAtMs'],now)
    prior=retirement.validate(retired,ctx,now)
    for key in ('blockhashContextSlot','signatureStatusContextSlot'):
        check(observed['chainObservation'][key]>=prior['chainObservation'][key],'successor-chain-regressed')
    for key in ('accountSnapshotSlot','accountBlockTime','finalizedBlockHeight'):
        check(observed[key]>=prior[key],'successor-chain-regressed')
    check(observed['blockers']==[],'successor-expiry-conflict')
    return observed


def previous_blockhashes(book):
    result=set()
    for table,key in (('admission_exit_preparation',None),('admission_exit_replacement','replacement'),
                      ('admission_exit_continuation','continuation')):
        if book.db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone():
            # Full historical preparation replay is required by the caller first.
            r=book.db.execute('SELECT CASE WHEN length(value)<=? THEN value ELSE NULL END FROM '+table+' WHERE id=1',
                              (MAX_RECORD,)).fetchone()
            check(r is not None and type(r[0]) is str,'successor-parent-record')
            item=json.loads(r[0]);item=item if key is None else item[key]
            result.add(item['evidence']['packet']['policy']['blockhash'])
    return result


def binding(book,ctx,retired,proof,evidence,collected,now):
    observed=fresh_review(ctx,retired,proof,now)
    old=preparation.saved(book,now)
    check(old is not None and digest(old)==ctx['identity']['preparationSha256'],'successor-parent-mismatch')
    limits=replan.budget(book.policy,ctx['identity']['scopedAccounting'])
    check(limits['blockers']==[],'successor-budget-blocked')
    b=preparation.review(book,evidence,now)
    b=collection.review(book,evidence,collected,now,b)
    check(collected['provenance']['startedAtMs']>=proof['observedAtMs'],'successor-observation-order')
    check(evidence['packet']['policy']['blockhash'] not in previous_blockhashes(book),'successor-reused-blockhash')
    cap=int(b['feeCapLamports']);old_cap=int(old['binding']['feeCapLamports']);held=int(limits['feeHeldLamports'])
    check(b['quantityAtomic']==limits['quantityAtomic'] and
          int(b['protectedInventoryAtomic'])>=int(limits['protectedInventoryAtomic']) and
          b['feeCommitmentRemainingLamports']==limits['feeHeldLamports'],'successor-ownership-conflict')
    check(0<cap<=min(old_cap,int(limits['proposedMaximumFeeLamports'])) and held>=old_cap+cap,
          'successor-unresolved-fee-exposure')
    captured=evidence['capture'];raw=captured['evidence']['accounts']['result']
    check(raw['context']['slot']>=observed['accountSnapshotSlot'],'successor-account-slot-regressed')
    current=dict(zip(captured['accountKeys'],raw['value']))
    for key,prior in zip(ctx['accountKeys'],ctx['expectedAccounts']):
        check(key in current and all(current[key][k]==prior[k] for k in ('owner','executable','lamports','data')),
              'successor-scoped-account-changed')
    # This is its own candidate schema; generic first-exit preparation readers
    # must not silently activate it or interpret its attempt count as zero.
    return dict(b,attemptNumber=2,attemptsConsumed=1,
        retiredFeeExposureHeldLamports=str(old_cap),
        otherHeldFeeLamports=str(held-cap),additionalFeeReservationLamports='0',
        retirementSha256=digest(retired),retiredPreparationSha256=digest(old))


def validate(book,ctx,retired,record,now):
    fields(record,{'format','recordedAtMs','contextSha256','retirementSha256',
        'retiredPreparationSha256','expiryProof','candidate'},'successor-schema')
    check(record['format']==VERSION and record['contextSha256']==digest(ctx) and
          record['retirementSha256']==digest(retired) and
          record['retiredPreparationSha256']==ctx['identity']['preparationSha256'],'successor-parent-binding')
    stamp=record['recordedAtMs'];uint(stamp,now,'successor-record-time',minimum=retired['recordedAtMs'])
    candidate=record['candidate']
    fields(candidate,{'format','evidence','collection','binding'},'successor-candidate-schema')
    check(candidate['format']==VERSION+'-unsigned','successor-candidate-format')
    expected=binding(book,ctx,retired,record['expiryProof'],candidate['evidence'],candidate['collection'],stamp)
    check(candidate['binding']==expected,'successor-binding-conflict')
    return record


def replay(book,root,wallet,pool,clock,amounts):
    record=row(book)
    if record is None:return None
    retired=retirement.row(book);check(retired is not None,'successor-retirement-required')
    ctx=retirement.position_context(book,root,wallet,pool,clock,amounts)
    retirement.validate(retired,ctx,clock())
    return validate(book,ctx,retired,record,clock())


def public(record,now,created=False):
    b=record['candidate']['binding']
    return dict(format=VERSION,state='unsigned-successor-expired-held' if now>=b['validUntilExclusiveMs'] else 'unsigned-successor-prepared-held',
        recordSha256=digest(record),retirementSha256=record['retirementSha256'],
        retiredPreparationSha256=record['retiredPreparationSha256'],createdThisRun=created,
        binding=deepcopy(b),sourceStateChanged=created,oldAttemptStillRetired=True,
        additionalFeeReservationLamports='0',reservationsReleasedThisRun=False,
        signaturesCreated=0,transactionsSent=0,privateKeyAccessed=False,
        replacementAuthorized=False,signingApproved=False,executionApproved=False,
        liveCollectorConnected=False,liveSignerConnected=False,liveSenderConnected=False)


def write_record(book,record):
    check(len(preparation.encoded(record).encode())<=MAX_RECORD,'successor-record-cap')
    book.db.execute('CREATE TABLE admission_exit_successor (id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL,hash TEXT NOT NULL)')
    book.db.execute('INSERT INTO admission_exit_successor VALUES(1,?,?)',(preparation.encoded(record),digest(record)))
    check(book.db.execute('PRAGMA page_count').fetchone()[0]*book.db.execute('PRAGMA page_size').fetchone()[0]<=64*1024*1024,
          'successor-ledger-cap')


@view.cycles.binding.operation
@history.fresh_signing.timing.signature_replay
def _prepare_from_producer(home,wallet,pool,expected,expected_retirement,producer,*,
                           allow_unsigned_successor=False,clock=view.now,monotonic=time.monotonic):
    """Internal producer contract, exercised offline only. No operator live adapter.

    Producer runs after full local replay while the source is pinned, and returns
    private raw expiry and quote/simulation evidence. It is not a public importer.
    """
    check(allow_unsigned_successor is True and callable(producer),'successor-explicit-internal-producer-required')
    replan.identity(expected);replan.identity(expected_retirement);started=monotonic()
    with view.cycles.c.source_lock(home,wallet) as root:
        book=preparation.entry.submission._open(root,wallet,pool,clock)
        try:
            with book.j.transaction():
                with read_only_journals():
                    reader=preparation.entry.submission._open(root,wallet,pool,clock)
                    try:
                        ctx=expiry.context(root,reader,wallet,pool,expected,clock)
                        retired=retirement.row(reader)
                        check(retired is not None and digest(retired)==expected_retirement,'successor-retirement-mismatch')
                        retirement.validate(retired,ctx,clock())
                        existing=row(reader)
                        if existing is not None:
                            validate(reader,ctx,retired,existing,clock());return public(existing,clock())
                        check(not view.cycles.c.submit.swap.stop(root),'successor-stopped')
                        check(replan.budget(reader.policy,ctx['identity']['scopedAccounting'])['blockers']==[],
                              'successor-budget-blocked')
                        with history.transport.ExitSubmission(reader).snapshot():
                            signed=history.transport.ExitSubmission(reader).signing()
                            check(digest(signed)==ctx['identity']['signingStateSha256'],'successor-signing-conflict')
                        check(0<=monotonic()-started<120,'successor-total-budget')
                        item=producer(deepcopy(ctx))
                        fields(item,{'expiryProof','evidence','collection'},'successor-producer-envelope')
                        history.backend._attempt_record_for_state(root,reader,signed)
                        check(history.backend._read_ack(root,reader,signed)==ctx['signedWire'],'successor-backend-conflict')
                        stamp=clock()
                        b=binding(reader,ctx,retired,item['expiryProof'],item['evidence'],item['collection'],stamp)
                        record=dict(format=VERSION,recordedAtMs=stamp,contextSha256=digest(ctx),
                            retirementSha256=expected_retirement,retiredPreparationSha256=expected,
                            expiryProof=deepcopy(item['expiryProof']),candidate=dict(format=VERSION+'-unsigned',
                                evidence=deepcopy(item['evidence']),collection=deepcopy(item['collection']),binding=b))
                    finally:reader.close()
                check(not view.cycles.c.submit.swap.stop(root),'successor-stopped')
                check(0<=monotonic()-started<=120,'successor-total-budget')
                write_record(book,record)
                check(stamp<=clock()<b['validUntilExclusiveMs'],'successor-expired-before-commit')
                fresh_review(ctx,retired,record['expiryProof'],clock())
                check(not view.cycles.c.submit.swap.stop(root),'successor-stopped')
                check(0<=monotonic()-started<=120,'successor-total-budget')
            return public(record,clock(),created=True)
        finally:book.close()
