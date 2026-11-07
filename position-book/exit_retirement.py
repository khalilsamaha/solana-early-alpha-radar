"""Explicit terminal retirement of one expired locally-unsent devnet attempt.

Only new denial metadata is written. Old evidence, signer markers, and every
financial reservation are preserved; this is not settlement or replacement.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import time

import expired_exit_evidence as expiry
import exit_retirement_guard as guard
from contract import digest,fields,uint
from core import check
from journal import read_only_journals
from pre_sign_admission import encoded

VERSION='held-exit-retirement-1'
MAX_RECORD=65536
COMMIT_WINDOW_MS=10000
view=expiry.view
history=expiry.chain.history


def position_context(book,root,wallet,pool,clock,amounts):
    """No lifecycle call: used during the lifecycle's own retirement replay."""
    record=history.lifecycle.preparation.saved(book,clock())
    check(record is not None,'retirement-preparation-required')
    with history.transport.ExitSubmission(book).snapshot():
        sender=history.transport.ExitSubmission(book);state=sender.signing()
        check(sender._boundary(state) is None,'retirement-locally-unsent-required')
        status=sender._status(None)
        check(status['state']=='not-attempted' and not status['receiptCaptureCount'],'retirement-transport-conflict')
        check(state['state']=='exit-signed-recorded' and clock()>=state['request']['validUntilExclusiveMs'],
              'retirement-expired-signature-required')
        history.backend._attempt_record_for_state(root,book,state)
        check(history.backend._read_ack(root,book,state)==state['signed']['signedWireBase64'],'retirement-backend-conflict')
    identity=dict(preparationSha256=digest(record),signingStateSha256=digest(state),
        signature=state['signed']['signature'],blockhash=state['request']['packet']['policy']['blockhash'],
        minimumContextSlot=state['minimumContextSlot'],scopedAccounting=amounts)
    return expiry.scope_context(book,wallet,identity,record)


def validate(record,ctx,now):
    fields(record,{'format','recordedAtMs','preparationSha256','contextSha256','startedAtMs',
        'observedAtMs','rpcEvidence'},'retirement-schema')
    check(record['format']==VERSION and record['preparationSha256']==ctx['identity']['preparationSha256'] and
          record['contextSha256']==digest(ctx),'retirement-context-conflict')
    uint(record['recordedAtMs'],now,'retirement-record-time',minimum=1)
    uint(record['observedAtMs'],record['recordedAtMs'],'retirement-observation-time',minimum=1)
    uint(record['startedAtMs'],record['observedAtMs'],'retirement-start-time',minimum=1)
    check(record['recordedAtMs']-record['observedAtMs']<=COMMIT_WINDOW_MS,'retirement-evidence-stale')
    check(record['observedAtMs']-record['startedAtMs']<=120000,'retirement-observation-duration')
    fields(record['rpcEvidence'],{'genesisBefore','validity','height','status','transaction','accounts',
        'blockTime','genesisAfter'},'retirement-proof-schema')
    for item in record['rpcEvidence'].values():
        fields(item,{'state','result'},'retirement-proof-item')
        check(item['state']=='received','retirement-proof-unavailable')
    a=expiry.assess(ctx,record['rpcEvidence'],record['startedAtMs'],record['recordedAtMs'])
    check(a['state']=='expiry-evidence-consistent-held' and a['blockers']==[],'retirement-evidence-conflict')
    return a


def row(book):
    found=book.db.execute('SELECT type FROM sqlite_master WHERE name=?',(guard.TABLE,)).fetchone()
    if found is None:return None
    check(found[0]=='table','retirement-table')
    rows=book.db.execute('SELECT id,CASE WHEN length(value)<=? THEN value ELSE NULL END value,hash FROM admission_exit_retirement LIMIT 2',(MAX_RECORD,)).fetchall()
    check(len(rows)==1 and rows[0]['id']==1 and type(rows[0]['value']) is str,'retirement-row')
    r=json.loads(rows[0]['value'])
    check(encoded(r)==rows[0]['value'] and digest(r)==rows[0]['hash'],'retirement-integrity')
    return r


def replay_for_projection(book,root,wallet,pool,clock,amounts):
    record=row(book);check(record is not None,'retirement-required')
    ctx=position_context(book,root,wallet,pool,clock,amounts)
    validate(record,ctx,clock());return record


def base():
    return dict(format=VERSION,state='retirement-unavailable',recorded=False,createdThisRun=False,
        retirementSha256=None,preparationSha256=None,scopedAccounting=None,diagnosticCode=None,
        networkRequests=0,sourceStateChanged=False,privateKeyAccessed=False,signaturesCreated=0,transactionsSent=0,
        reservationsReleasedThisRun=False,replacementAuthorized=False,retryAllowed=False,executionApproved=False,
        nonExecutionProven=False,receiptEffectsReconciled=False,
        limitations=['Retirement disables this attempt locally; it is not economic settlement or proof of global non-execution.',
          'All original signatures, preparation generations, and inventory/fee holds remain.',
          'This release cannot create a replacement, reset signing capacity, or release funds.'])


def public(record,ctx,created=False,requests=0):
    r=base();r.update(state='exit-retired-held',recorded=True,createdThisRun=created,
        retirementSha256=digest(record),preparationSha256=record['preparationSha256'],
        recordedAtMs=record['recordedAtMs'],evidenceObservedAtMs=record['observedAtMs'],
        scopedAccounting=deepcopy(ctx['identity']['scopedAccounting']),networkRequests=requests,
        sourceStateChanged=created)
    return r


@view.cycles.binding.operation
@history.fresh_signing.timing.signature_replay
def status(home,wallet,pool,expected,*,clock=view.now):
    r=base()
    try:
        with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
            book=history.lifecycle.entry.submission._open(root,wallet,pool,clock)
            try:
                with history.lifecycle.admission_read_lock(book.j.path):
                    ctx=expiry.context(root,book,wallet,pool,expected,clock)
                    record=row(book)
                    if record is None:r.update(state='retirement-not-recorded',preparationSha256=expected)
                    else:validate(record,ctx,clock());r=public(record,ctx)
            finally:book.close()
    except view.ERRORS:r['diagnosticCode']='retirement-evidence-unavailable'
    r['capturedAt']=datetime.now(timezone.utc).isoformat();return r


def write_record(book,record):
    check(len(encoded(record).encode())<=MAX_RECORD,'retirement-record-cap')
    book.db.execute('CREATE TABLE admission_exit_retirement (id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL,hash TEXT NOT NULL)')
    book.db.execute('INSERT INTO admission_exit_retirement VALUES(1,?,?)',(encoded(record),digest(record)))
    check(book.db.execute('PRAGMA page_count').fetchone()[0]*book.db.execute('PRAGMA page_size').fetchone()[0]<=64*1024*1024,'retirement-ledger-cap')


def _commit(home,wallet,pool,expected,proof,*,clock,monotonic,started):
    with view.cycles.c.source_lock(home,wallet) as root:
        book=history.lifecycle.entry.submission._open(root,wallet,pool,clock)
        try:
            with book.j.transaction():
                with read_only_journals():
                    reader=history.lifecycle.entry.submission._open(root,wallet,pool,clock)
                    try:
                        ctx=expiry.context(root,reader,wallet,pool,expected,clock)
                        old=row(reader)
                        if old is not None:
                            validate(old,ctx,clock());return public(old,ctx)
                        record=dict(format=VERSION,recordedAtMs=clock(),preparationSha256=expected,**deepcopy(proof))
                        validate(record,ctx,clock())
                    finally:reader.close()
                check(0<=monotonic()-started<=120,'retirement-operation-budget')
                write_record(book,record)
                # Revalidate time just before COMMIT; a failed write or deadline
                # rolls back the table and row together, never consuming a slot.
                end=clock();uint(end,record['observedAtMs']+COMMIT_WINDOW_MS,'retirement-commit-time',minimum=record['recordedAtMs'])
                expiry.assess(ctx,record['rpcEvidence'],record['startedAtMs'],end)
                check(0<=monotonic()-started<=120,'retirement-operation-budget')
            return public(record,ctx,created=True)
        finally:book.close()


@view.cycles.binding.operation
@history.fresh_signing.timing.signature_replay
def retire(home,wallet,pool,expected,*,allow_retire=False,opener=None,clock=view.now,monotonic=time.monotonic):
    check(allow_retire is True,'explicit-local-retirement-required')
    started=monotonic();r=status(home,wallet,pool,expected,clock=clock)
    if r['state']!='retirement-not-recorded':return r
    captured=[]
    observation=expiry.inspect(home,wallet,pool,expected,opener=opener,clock=clock,monotonic=monotonic,
        _evidence_sink=captured.append)
    requests=observation['networkRequests'];r=base();r['networkRequests']=requests
    if observation['state']!='expired-exit-evidence-observed' or observation['assessment']['state']!='expiry-evidence-consistent-held':
        r.update(state='retirement-refused-held',diagnosticCode='fresh-expiry-evidence-required');return r
    try:
        check(len(captured)==1,'retirement-private-evidence-required')
        r=_commit(home,wallet,pool,expected,captured[0],clock=clock,monotonic=monotonic,started=started)
        r['networkRequests']=requests
    except view.ERRORS:
        r.update(state='retirement-unconfirmed-held',recorded=None,createdThisRun=None,sourceStateChanged=None,
            diagnosticCode='inspect-retirement-status-before-any-further-action')
    r['capturedAt']=datetime.now(timezone.utc).isoformat();return r
