"""Separate durable successor signer handoff; internal adapter, no live backend.

The retired generation is never rewritten. A committed unknown boundary consumes
this generation's only adapter call, including when its response is lost.
"""
from copy import deepcopy
import json

import retired_exit_successor as successor
import exit_signing_handoff as original
from contract import digest, fields, uint
from core import check
from journal import read_only_journals

VERSION='successor-signing-handoff-1'
TABLE='admission_successor_signing'
MAX_ROW=12288
MAX_EVENTS=3
view=successor.view
preparation=successor.preparation
encoded=preparation.encoded


def present(book):
    return book.db.execute('SELECT type FROM sqlite_master WHERE name=?',(TABLE,)).fetchone()


def request_for(record):
    check(record is not None and record['format']==successor.VERSION,'successor-signing-candidate-required')
    candidate=record['candidate'];b=candidate['binding']
    check(candidate['format']==successor.VERSION+'-unsigned' and b['attemptNumber']==2 and
          b['attemptsConsumed']==1,'successor-signing-generation')
    return dict(format=VERSION+'-request',successorSha256=digest(record),
        retirementSha256=record['retirementSha256'],retiredPreparationSha256=record['retiredPreparationSha256'],
        contextSha256=record['contextSha256'],entryAccountingSha256=b['entryAccountingSha256'],
        collectionSha256=b['collectionSha256'],messageSha256=b['messageSha256'],
        validUntilExclusiveMs=b['validUntilExclusiveMs'],quantityAtomic=b['quantityAtomic'],
        protectedInventoryAtomic=b['protectedInventoryAtomic'],feeCapLamports=b['feeCapLamports'],
        feeCommitmentRemainingLamports=b['feeCommitmentRemainingLamports'],
        retiredFeeExposureHeldLamports=b['retiredFeeExposureHeldLamports'],
        additionalFeeReservationLamports='0',attemptNumber=2,attemptsConsumed=1,
        packet=deepcopy(candidate['evidence']['packet']))


def read(book,record,now):
    """Replay only after caller semantically validates the saved successor."""
    exists=present(book)
    if not exists:return None
    check(exists[0]=='table','successor-signing-table')
    request=request_for(record)
    rows=book.db.execute('SELECT seq,at_ms,CASE WHEN length(value)<=? THEN value ELSE NULL END value,previous_hash,hash FROM admission_successor_signing ORDER BY seq LIMIT ?',
                        (MAX_ROW,MAX_EVENTS+1)).fetchall()
    check(1<=len(rows)<=MAX_EVENTS,'successor-signing-event-cap')
    previous='';stamp=record['recordedAtMs'];state=None;signed=None;head=None
    for seq,row in enumerate(rows,1):
        check(row['seq']==seq and type(row['value']) is str,'successor-signing-event-shape')
        uint(row['at_ms'],now,'successor-signing-clock',minimum=stamp)
        v=json.loads(row['value']);check(encoded(v)==row['value'],'successor-signing-canonical')
        h=digest(dict(seq=seq,atMs=row['at_ms'],value=v,previousHash=previous))
        check(row['previous_hash']==previous and row['hash']==h,'successor-signing-integrity')
        if seq==1:
            fields(v,{'state','request','requestSha256','admissionHeadSha256'},'successor-signing-boundary-schema')
            check(v['state']=='successor-signing-unknown' and v['request']==request and
                  v['requestSha256']==digest(request),'successor-signing-request-binding')
            check(row['at_ms']<request['validUntilExclusiveMs'],'successor-signing-boundary-clock')
            source=book.db.execute('SELECT value,at_ms FROM admission_events WHERE hash=?',(v['admissionHeadSha256'],)).fetchone()
            check(source is not None and source['at_ms']<=row['at_ms'] and
                  json.loads(source['value'])['state']=='signed-recorded' and
                  digest(json.loads(source['value']))==record['candidate']['collection']['provenance']['identity']['admissionStateSha256'],
                  'successor-signing-admission-binding')
            head=v['admissionHeadSha256']
        elif v.get('state')=='successor-signed-recorded':
            fields(v,{'state','signedWireBase64','wireSha256','signature'},'successor-signed-schema')
            check(seq==2 and state=='successor-signing-unknown','successor-signing-transition')
            checked=original.signed_check(v['signedWireBase64'],request)
            check(all(v[k]==x for k,x in checked.items()),'successor-signed-integrity');signed=v
        else:
            fields(v,{'state','reason'},'successor-quarantine-schema')
            check(v==dict(state='successor-signing-quarantined',reason='signed-response-rejected') and
                  state in ('successor-signing-unknown','successor-signed-recorded'),'successor-signing-transition')
        state=v['state'];previous=h;stamp=row['at_ms']
    return dict(state=state,request=request,requestSha256=digest(request),admissionHeadSha256=head,
                eventCount=len(rows),headSha256=previous,lastAtMs=stamp,signed=signed)


def append(book,value,state,now):
    check(len(encoded(value).encode())<=MAX_ROW,'successor-signing-row-cap')
    count=0 if state is None else state['eventCount'];previous='' if state is None else state['headSha256']
    check(count<MAX_EVENTS,'successor-signing-event-cap')
    if state is None:
        book.db.execute('CREATE TABLE admission_successor_signing (seq INTEGER PRIMARY KEY,at_ms INTEGER NOT NULL,value TEXT NOT NULL,previous_hash TEXT NOT NULL,hash TEXT NOT NULL)')
    h=digest(dict(seq=count+1,atMs=now,value=value,previousHash=previous))
    book.db.execute('INSERT INTO admission_successor_signing VALUES(?,?,?,?,?)',(count+1,now,encoded(value),previous,h))
    check(book.db.execute('PRAGMA page_count').fetchone()[0]*book.db.execute('PRAGMA page_size').fetchone()[0]<=64*1024*1024,
          'successor-signing-ledger-cap')


def load(root,book,wallet,pool,expected,clock):
    successor.replan.identity(expected)
    record=successor.row(book)
    check(record is not None and digest(record)==expected,'successor-signing-candidate-mismatch')
    # Includes all historical source, retired backend files and original holds;
    # lifecycle replay checks the separate signing table without recursing here.
    phase,_,amounts,_,_,_=successor.history.lifecycle._projection(book,root,wallet,pool,clock)
    check(phase=='exit-signed-not-submitted' and amounts is not None,'successor-signing-original-position')
    ctx=successor.retirement.position_context(book,root,wallet,pool,clock,amounts)
    retired=successor.retirement.row(book)
    check(retired is not None,'successor-signing-retirement-required')
    successor.retirement.validate(retired,ctx,clock())
    successor.validate(book,ctx,retired,record,clock())
    return record,ctx,retired,read(book,record,clock())


def current(book,record,ctx,retired,clock):
    now=clock();b=record['candidate']['binding']
    check(record['recordedAtMs']<=now<b['validUntilExclusiveMs'],'successor-signing-expired')
    expected=successor.binding(book,ctx,retired,record['expiryProof'],record['candidate']['evidence'],record['candidate']['collection'],now)
    check(expected==b,'successor-signing-current-binding')
    state,_,head,_=book.read()
    check(state['state']=='signed-recorded' and digest(state)==record['candidate']['collection']['provenance']['identity']['admissionStateSha256'],
          'successor-signing-source-changed')
    return request_for(record),head,now


def live_guard(root,book,request,stamp,clock):
    check(stamp<=clock()<request['validUntilExclusiveMs'] and not original.stopped(root,book),
          'successor-signing-expired-or-stopped')


def public(state,record,now,stop=False,calls=0):
    return dict(format=VERSION,state='successor-signing-not-started' if state is None else state['state'],
        successorSha256=digest(record),retirementSha256=record['retirementSha256'],
        headSha256=None if state is None else state['headSha256'],boundaryRecorded=state is not None,
        eventCount=0 if state is None else state['eventCount'],acknowledgmentRecorded=bool(state and state['signed']),
        stopRequested=stop,evidenceExpired=now>=record['candidate']['binding']['validUntilExclusiveMs'],
        signerAdapterCallsThisRun=calls,attemptNumber=2,retiredAttemptStillHeld=True,
        generationSigningAttemptsHeld=int(state is not None),additionalFeeReservationLamports='0',
        networkRequests=0,transactionsSent=0,liveKeyBackendConnected=False,liveSenderIntegrated=False,
        executionApproved=False,validForSubmission=False,automaticResigningAllowed=False,
        reservationsReleasedThisRun=False,scannerRuntimeChanged=False)


def acknowledge(book,record,response,clock):
    """Accept only the already bound wire; expiry/STOP never erase a late reply."""
    state=read(book,record,clock());check(state is not None,'successor-signing-boundary-required')
    if state['state']=='successor-signing-quarantined':return state
    if state['signed'] and state['signed']['signedWireBase64']==response:return state
    try:
        signed=original.signed_check(response,state['request'])
        check(state['signed'] is None,'successor-signed-conflict')
        value=dict(state='successor-signed-recorded',**signed)
    except (ValueError,KeyError,TypeError) as exc:
        if isinstance(exc,ValueError) and str(exc)=='node-runtime-unavailable':raise
        value=dict(state='successor-signing-quarantined',reason='signed-response-rejected')
    now=clock();check(now>=state['lastAtMs'],'successor-signing-clock')
    append(book,value,state,now)
    return read(book,record,clock())


@view.cycles.binding.operation
@successor.history.fresh_signing.timing.signature_replay
def _dispatch(home,wallet,pool,expected,*,signer_adapter,clock=view.now):
    """Internal injected adapter only. No default backend and no live CLI."""
    check(callable(signer_adapter),'successor-explicit-adapter-required')
    with view.cycles.c.source_lock(home,wallet) as root:
        book=preparation.entry.submission._open(root,wallet,pool,clock)
        try:
            with book.j.transaction():
                record,ctx,retired,state=load(root,book,wallet,pool,expected,clock)
                if state is not None:return public(state,record,clock(),original.stopped(root,book))
                request,head,stamp=current(book,record,ctx,retired,clock)
                live_guard(root,book,request,stamp,clock)
                append(book,dict(state='successor-signing-unknown',request=request,requestSha256=digest(request),admissionHeadSha256=head),None,stamp)
                live_guard(root,book,request,stamp,clock)
            # Never retry a committed boundary even if the adapter was not entered.
            with book.j.transaction():
                # Keep another writer out while rechecking and calling the adapter.
                # Boundary is already durable and readable from another connection.
                record,ctx,retired,state=load(root,book,wallet,pool,expected,clock)
                check(state['state']=='successor-signing-unknown','successor-signing-state')
                current(book,record,ctx,retired,clock)
                live_guard(root,book,request,stamp,clock)
                response=signer_adapter(deepcopy(request))
                # Adapter cannot substitute a different stored generation or marker.
                checked,_,_,_=load(root,book,wallet,pool,expected,clock)
                check(checked==record,'successor-signing-source-changed')
                state=acknowledge(book,record,response,clock)
            return public(state,record,clock(),original.stopped(root,book),1)
        finally:book.close()


@view.cycles.binding.operation
@successor.history.fresh_signing.timing.signature_replay
def _recover(home,wallet,pool,expected,*,signed_response=None,clock=view.now):
    """Internal recovery of an existing response; no signer or network call."""
    with view.cycles.c.source_lock(home,wallet) as root:
        book=preparation.entry.submission._open(root,wallet,pool,clock)
        try:
            with book.j.transaction():
                record,_,_,state=load(root,book,wallet,pool,expected,clock)
                if signed_response is not None:state=acknowledge(book,record,signed_response,clock)
            return public(state,record,clock(),original.stopped(root,book))
        finally:book.close()


@view.cycles.binding.operation
@successor.history.fresh_signing.timing.signature_replay
def _status(home,wallet,pool,expected,*,clock=view.now):
    with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
        book=preparation.entry.submission._open(root,wallet,pool,clock)
        try:
            with successor.history.lifecycle.admission_read_lock(book.j.path):
                record,_,_,state=load(root,book,wallet,pool,expected,clock)
                return public(state,record,clock(),original.stopped(root,book))
        finally:book.close()
