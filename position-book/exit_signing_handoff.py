"""One durable exit signer-adapter boundary, with no default key backend or sender.

Only collected private evidence may reach the injected in-process adapter. Public
reports cannot authorize signing. Unknown signatures retain every commitment.
"""
from copy import deepcopy
import json

import admission_exit as preparation
from contract import digest, fields, validate, uint
from core import check
from pre_sign_admission import encoded, Admission
from journal import read_only_journals
from wire import verify_wire

VERSION='exit-signing-handoff-1'
TABLE='admission_exit_signing'
MAX_ROW=8192
MAX_EVENTS=3
view=preparation.view


def request_for(record):
    check(record is not None and record['format']==preparation.COLLECTED_FORMAT,'exit-collected-preparation-required')
    b=record['binding']
    return dict(format=VERSION+'-request',preparationSha256=digest(record),
        entryAccountingSha256=b['entryAccountingSha256'],collectionSha256=b['collectionSha256'],
        messageSha256=b['messageSha256'],validUntilExclusiveMs=b['validUntilExclusiveMs'],
        quantityAtomic=b['quantityAtomic'],feeCapLamports=b['feeCapLamports'],
        packet=deepcopy(record['evidence']['packet']))


def signed_check(wire,request):
    check(type(wire) is str and len(wire)<=1644,'exit-signed-size')
    signed=verify_wire(wire)
    check(signed['requiredSignatures']==1 and signed['wallet']==request['packet']['policy']['accounts']['wallet']
          and signed['wireMessageSha256']==request['messageSha256'],'exit-signed-binding')
    return dict(signedWireBase64=wire,wireSha256=signed['wireSha256'],signature=signed['signatures'][0])


def read(book,now,*,_preparation_sink=None):
    """Bounded semantic replay; a hash match alone never authenticates a wire."""
    check(_preparation_sink is None or callable(_preparation_sink),
          'exit-preparation-sink')
    exists=book.db.execute('SELECT type FROM sqlite_master WHERE name=?',(TABLE,)).fetchone()
    if not exists:return None
    check(exists[0]=='table','exit-signing-table')
    rows=book.db.execute('SELECT seq,at_ms,CASE WHEN length(value)<=? THEN value ELSE NULL END value,previous_hash,hash FROM admission_exit_signing ORDER BY seq LIMIT ?',
                        (MAX_ROW,MAX_EVENTS+1)).fetchall()
    check(1<=len(rows)<=MAX_EVENTS,'exit-signing-event-cap')
    prepared=preparation.saved(book,now);request=request_for(prepared)
    state=None;previous='';stamp=0;head=None
    for seq,row in enumerate(rows,1):
        check(row['seq']==seq and type(row['value']) is str,'exit-signing-event-shape')
        uint(row['at_ms'],now,'exit-signing-clock',minimum=max(1,stamp))
        v=json.loads(row['value']);check(encoded(v)==row['value'],'exit-signing-canonical')
        h=digest(dict(seq=seq,atMs=row['at_ms'],value=v,previousHash=previous))
        check(row['previous_hash']==previous and row['hash']==h,'exit-signing-integrity')
        if seq==1:
            fields(v,{'state','request','requestSha256','admissionHeadSha256'},'exit-signing-boundary-schema')
            check(v['state']=='exit-signing-unknown' and v['request']==request and
                  v['requestSha256']==digest(request),'exit-signing-request-binding')
            check(prepared['recordedAtMs']<=row['at_ms']<request['validUntilExclusiveMs'],'exit-signing-boundary-clock')
            source=book.db.execute('SELECT value,at_ms FROM admission_events WHERE hash=?',(v['admissionHeadSha256'],)).fetchone()
            check(source is not None and source['at_ms']<=row['at_ms'] and
                  json.loads(source['value'])['state']=='signed-recorded' and
                  digest(json.loads(source['value']))==prepared['collection']['provenance']['identity']['admissionStateSha256'],
                  'exit-signing-admission-binding')
            head=v['admissionHeadSha256']
        elif v.get('state')=='exit-signed-recorded':
            fields(v,{'state','signedWireBase64','wireSha256','signature'},'exit-signed-schema')
            check(seq==2 and state['state']=='exit-signing-unknown','exit-signing-transition')
            checked=signed_check(v['signedWireBase64'],request)
            check(all(v[k]==x for k,x in checked.items()),'exit-signed-integrity')
        else:
            fields(v,{'state','reason'},'exit-quarantine-schema')
            check(v==dict(state='exit-signing-quarantined',reason='signed-response-rejected') and
                  state['state'] in ('exit-signing-unknown','exit-signed-recorded'),'exit-signing-transition')
        state=v;previous=h;stamp=row['at_ms']
    result=dict(state=state['state'],request=request,requestSha256=digest(request),
                admissionHeadSha256=head,eventCount=len(rows),headSha256=previous,lastAtMs=stamp,
                signed=next((json.loads(r['value']) for r in rows if json.loads(r['value']).get('state')=='exit-signed-recorded'),None))
    # The transport consumes this exact already-replayed generation in this call.
    # No cache survives the read; failures above never publish partial evidence.
    if _preparation_sink is not None:_preparation_sink(prepared)
    return result


def append(book,value,state,now):
    check(len(encoded(value).encode())<=MAX_ROW,'exit-signing-row-cap')
    count=0 if state is None else state['eventCount'];previous='' if state is None else state['headSha256']
    check(count<MAX_EVENTS,'exit-signing-event-cap')
    if state is None:
        book.db.execute('CREATE TABLE admission_exit_signing (seq INTEGER PRIMARY KEY,at_ms INTEGER NOT NULL,value TEXT NOT NULL,previous_hash TEXT NOT NULL,hash TEXT NOT NULL)')
    h=digest(dict(seq=count+1,atMs=now,value=value,previousHash=previous))
    book.db.execute('INSERT INTO admission_exit_signing VALUES(?,?,?,?,?)',(count+1,now,encoded(value),previous,h))
    check(book.db.execute('PRAGMA page_count').fetchone()[0]*book.db.execute('PRAGMA page_size').fetchone()[0]<=64*1024*1024,'exit-ledger-size-cap')


def stopped(root,book):return view.cycles.c.submit.swap.stop(root) or book.read()[0]['state']!='signed-recorded'


def public(state,now,stop=False,calls=0):
    name='exit-signing-not-started' if state is None else state['state']
    if stop and name!='exit-signing-quarantined':name='exit-signing-stopped'
    return dict(format=VERSION,state=name,boundaryRecorded=state is not None,
        eventCount=0 if state is None else state['eventCount'],
        headSha256=None if state is None else state['headSha256'],
        preparationSha256=None if state is None else state['request']['preparationSha256'],
        acknowledgmentRecorded=bool(state and state['signed']),stopRequested=stop,
        evidenceExpired=bool(state and now>=state['request']['validUntilExclusiveMs']),
        signerAdapterCallsThisRun=calls,signingAttemptsHeld=int(state is not None),
        networkRequests=0,transactionsSent=0,liveKeyBackendConnected=False,liveSenderIntegrated=False,
        executionApproved=False,validForSubmission=False,automaticResigningAllowed=False,
        reservationReleased=False,allocationTransferred=False,runtimeIntegrated=False,
        walletWideReservationsKnown=False,nextCycleAuthorized=False)


def current(root,book,wallet,pool,clock):
    from exit_retirement_guard import require_active
    require_active(book)
    check(not stopped(root,book),'exit-signing-stopped')
    now=clock();record=preparation.saved(book,now);request=request_for(record)
    check(record['recordedAtMs']<=now<request['validUntilExclusiveMs'],'exit-signing-expired')
    # Repeat the economic/account evidence review at the current clock; the
    # stored deadline remains the tighter collection deadline, never refreshed.
    b=preparation.review(book,record['evidence'],now)
    check(b['messageSha256']==request['messageSha256'],'exit-signing-message')
    _,reservation=preparation.owner(book,now)
    source=view.read_locked(root,wallet,pool,clock)
    check(source['wallet']==wallet and source['pool']==pool and source['phase']=='closed' and
          source['nativeHeldLamports']=='0' and all(x['heldAtomic']=='0' for x in source['tokenAccounts']) and
          source['ledgerHeadSha256']==reservation['ledgerHeadSha256'] and
          source['cycleBindingSha256']==reservation['cycleBindingSha256'],'exit-signing-source-changed')
    state,_,head,_=book.read()
    check(digest(state)==record['collection']['provenance']['identity']['admissionStateSha256'],'exit-signing-admission-changed')
    checked=validate(request['packet'],now_ms=now)
    check(checked['state']=='instruction-policy-match' and checked['wireMessageSha256']==request['messageSha256'],
          'exit-signing-contract')
    return request,head,now


def acknowledge(book,response,clock):
    """Persist one existing reply after interruption/expiry; never call a signer."""
    with book.j.transaction():
        now=clock()
        with read_only_journals():
            reader=Admission(book.j.path,clock=clock)
            try:state=read(reader,now)
            finally:reader.close()
        check(state is not None,'exit-signing-boundary-required')
        if state['state']=='exit-signing-quarantined':return state
        if state['signed'] and state['signed']['signedWireBase64']==response:return state
        try:
            checked=signed_check(response,state['request'])
            check(state['signed'] is None,'exit-signed-conflict')
            v=dict(state='exit-signed-recorded',**checked)
        except (ValueError,KeyError,TypeError) as exc:
            if isinstance(exc,ValueError) and str(exc)=='node-runtime-unavailable':raise
            v=dict(state='exit-signing-quarantined',reason='signed-response-rejected')
        end=clock();check(end>=now>=state['lastAtMs'],'exit-signing-clock')
        append(book,v,state,end)
    return read(book,clock())


@view.cycles.binding.operation
def dispatch(home,wallet,pool,*,signer_adapter,clock=view.now):
    """Explicit injected adapter only. The committed boundary prevents retries."""
    check(callable(signer_adapter),'explicit-exit-signer-adapter-required')
    with view.cycles.c.source_lock(home,wallet) as root:
        book=preparation.entry.submission._open(root,wallet,pool,clock)
        try:
            with book.j.transaction():
                with read_only_journals():
                    reader=preparation.entry.submission._open(root,wallet,pool,clock)
                    try:
                        existing=read(reader,clock())
                        if existing:return public(existing,clock(),stopped(root,reader))
                        request,head,now=current(root,reader,wallet,pool,clock)
                    finally:reader.close()
                check(now<=clock()<request['validUntilExclusiveMs'] and not stopped(root,book),'exit-signing-boundary-expired-or-stopped')
                append(book,dict(state='exit-signing-unknown',request=request,requestSha256=digest(request),admissionHeadSha256=head),None,now)
                check(now<=clock()<request['validUntilExclusiveMs'] and not stopped(root,book),'exit-signing-boundary-expired-or-stopped')
            # Boundary committed BEFORE entering adapter. An exception or lost
            # reply leaves unknown evidence that dispatch will never retry.
            with read_only_journals():
                state=read(book,clock())
                check(state['state']=='exit-signing-unknown' and not stopped(root,book),'exit-signing-stopped')
                check(now<=clock()<request['validUntilExclusiveMs'],'exit-signing-expired')
                response=signer_adapter(deepcopy(request))
            state=acknowledge(book,response,clock)
            return public(state,clock(),stopped(root,book),1)
        finally:book.close()


def recover(home,wallet,pool,*,signed_response=None,clock=view.now):
    with view.cycles.c.source_lock(home,wallet) as root:
        book=preparation.entry.submission._open(root,wallet,pool,clock)
        try:
            state=read(book,clock()) if signed_response is None else acknowledge(book,signed_response,clock)
            return public(state,clock(),stopped(root,book))
        finally:book.close()


def status(home,wallet,pool,*,clock=view.now):
    with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
        book=preparation.entry.submission._open(root,wallet,pool,clock)
        try:return public(read(book,clock()),clock(),stopped(root,book))
        finally:book.close()
