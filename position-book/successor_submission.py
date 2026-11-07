"""Internal one-attempt successor transport; injected provider required.

No execution CLI or default network adapter. Finalized RPC claims do not settle
balances or release any original commitment. Every read replays the bound source.
"""
import base64
from copy import deepcopy
import json
import time

import successor_signing_handoff as handoff
import restricted_successor_signer as backend
import exit_submission as original
from contract import digest, fields, uint
from core import check
from journal import read_only_journals

VERSION='successor-submission-1'
TABLE='admission_successor_transport'
MAX_CAPTURES=8
MAX_ROW=4*1024*1024
MAX_EVENTS=2+MAX_CAPTURES
transport=original.transport
encoded=handoff.encoded


def present(book):
    return book.db.execute('SELECT type FROM sqlite_master WHERE name=?',(TABLE,)).fetchone()


def signing_state(record,signed):
    check(signed is not None and signed['state']=='successor-signed-recorded' and signed['signed'] is not None,
          'successor-transport-signed-required')
    e=record['candidate']['evidence']
    slots=[e['simulationItem']['result']['context']['slot'],e['capture']['evidence']['accounts']['result']['context']['slot'],e['price']['quote']['contextSlot']]
    for slot in slots:uint(slot,2**53-1,'successor-transport-context')
    return dict(signed,minimumContextSlot=max(slots))


def replay(book,record,signed,now):
    """Caller validates source/record/signing first in the same locked snapshot."""
    exists=present(book)
    if not exists:return None
    check(exists[0]=='table','successor-transport-table')
    state=signing_state(record,signed)
    rows=book.db.execute('SELECT seq,at_ms,CASE WHEN length(value)<=? THEN value ELSE NULL END value,previous_hash,hash FROM admission_successor_transport ORDER BY seq LIMIT ?',
                        (MAX_ROW,MAX_EVENTS+1)).fetchall()
    check(1<=len(rows)<=MAX_EVENTS,'successor-transport-event-cap')
    previous='';stamp=signed['lastAtMs'];boundary=None;ack=None;captures=[];terminal=None;identity=None;quarantined=False
    for seq,row in enumerate(rows,1):
        check(row['seq']==seq and type(row['value']) is str,'successor-transport-row')
        uint(row['at_ms'],now,'successor-transport-clock',minimum=stamp)
        v=json.loads(row['value'])
        check(encoded(v)==row['value'] and len(row['value'].encode())<=MAX_ROW,'successor-transport-canonical')
        h=digest(dict(seq=seq,atMs=row['at_ms'],value=v,previousHash=previous))
        check(row['previous_hash']==previous and row['hash']==h,'successor-transport-integrity')
        if seq==1:
            fields(v,{'kind','format','successorSha256','retirementSha256','requestSha256','signingHeadSha256','wireSha256','signature','endpoint','preflight'},'successor-transport-boundary-schema')
            check(v['kind']=='boundary' and v['format']==VERSION and v['successorSha256']==digest(record) and
                  v['retirementSha256']==record['retirementSha256'] and v['requestSha256']==signed['requestSha256'] and
                  v['signingHeadSha256']==signed['headSha256'] and v['wireSha256']==signed['signed']['wireSha256'] and
                  v['signature']==signed['signed']['signature'] and v['endpoint']==transport.ENDPOINT,
                  'successor-transport-boundary-binding')
            check(row['at_ms']<signed['request']['validUntilExclusiveMs'],'successor-transport-boundary-expired')
            original.proof_check(v['preflight'],state);boundary=v
        elif v.get('kind')=='ack':
            fields(v,{'kind','boundarySha256','state'},'successor-transport-ack-schema')
            check(seq==2 and ack is None and v['boundarySha256']==digest(boundary) and
                  v['state'] in ('rpc-acknowledged','transport-unknown','quarantined'),'successor-transport-ack-binding')
            ack=v;quarantined|=v['state']=='quarantined'
        else:
            fields(v,{'kind','boundarySha256','startedAtMs','rpcEvidence'},'successor-transport-capture-schema')
            check(v['kind']=='capture' and v['boundarySha256']==digest(boundary),'successor-transport-capture-binding')
            uint(v['startedAtMs'],row['at_ms'],'successor-transport-capture-clock',minimum=stamp)
            fields(v['rpcEvidence'],{'genesisBefore','signatureStatus','transaction','genesisAfter'},'successor-transport-evidence')
            check(all(type(x) is dict for x in v['rpcEvidence'].values()),'successor-transport-evidence')
            captures.append(v);check(len(captures)<=MAX_CAPTURES,'successor-transport-capture-cap')
            kind,summary=original.classify(v,state,original.proof_check(boundary['preflight'],state))
            quarantined|=kind=='quarantined'
            if kind in original.TERMINAL:
                sha=digest(summary)
                if identity is not None and identity!=sha:quarantined=True
                else:terminal=kind;identity=sha
        previous=h;stamp=row['at_ms']
    result='successor-submission-unknown'
    if ack and ack['state']=='rpc-acknowledged':result='rpc-acknowledged'
    if terminal:result='successor-'+terminal.removeprefix('exit-')
    if quarantined:result='quarantined'
    return dict(state=result,eventCount=len(rows),headSha256=previous,lastAtMs=stamp,boundary=boundary,
                acknowledgment=ack,captures=captures,terminalEvidenceSha256=identity)


def append(book,value,state,now):
    text=encoded(value);check(len(text.encode())<=MAX_ROW,'successor-transport-row-cap')
    count=0 if state is None else state['eventCount'];previous='' if state is None else state['headSha256']
    check(count<MAX_EVENTS,'successor-transport-event-cap')
    if state is None:
        book.db.execute('CREATE TABLE admission_successor_transport (seq INTEGER PRIMARY KEY,at_ms INTEGER NOT NULL,value TEXT NOT NULL,previous_hash TEXT NOT NULL,hash TEXT NOT NULL)')
    h=digest(dict(seq=count+1,atMs=now,value=value,previousHash=previous))
    book.db.execute('INSERT INTO admission_successor_transport VALUES(?,?,?,?,?)',(count+1,now,text,previous,h))
    check(book.db.execute('PRAGMA page_count').fetchone()[0]*book.db.execute('PRAGMA page_size').fetchone()[0]<=64*1024*1024,'successor-transport-ledger-cap')


def load(root,book,wallet,pool,expected,clock):
    record,ctx,retired,signed=handoff.load(root,book,wallet,pool,expected,clock)
    signing=signing_state(record,signed)
    check(backend._ack(root,book,signed)==signed['signed']['signedWireBase64'],'successor-transport-backend-ack')
    return record,ctx,retired,signing,replay(book,record,signed,clock())


def public(record,state,rpc=None):
    calls=[] if rpc is None else rpc.calls
    return dict(format=VERSION,state='not-attempted' if state is None else state['state'],successorSha256=digest(record),
        applicationSendBoundaryRecorded=state is not None,eventCount=0 if state is None else state['eventCount'],
        receiptCaptureCount=0 if state is None else len(state['captures']),
        transportHeadSha256=None if state is None else state['headSha256'],
        terminalEvidenceSha256=None if state is None else state['terminalEvidenceSha256'],
        networkRequestsThisRun=len(calls),sendRequestsThisRun=sum(c['method']=='sendTransaction' for c in calls),
        automaticRetryAllowed=False,automaticResigningAllowed=False,privateKeyAccessed=False,signaturesCreated=0,
        oldAttemptStillRetired=True,additionalFeeReservationLamports='0',reservationsReleased=False,
        receiptEffectsReconciled=False,scopedClosureRecorded=False,executionApproved=False,runtimeIntegrated=False,
        basis='Application attempt and fixed devnet RPC claims; not settlement or proof of chain finality')


@handoff.view.cycles.binding.operation
@handoff.successor.history.fresh_signing.timing.signature_replay
def _submit(home,wallet,pool,expected,*,allow_devnet_submit=False,opener=None,clock=handoff.view.now,monotonic=time.monotonic):
    check(allow_devnet_submit is True,'explicit-successor-submit-required')
    check(opener is not None and callable(getattr(opener,'open',None)) and bool(opener),'successor-injected-transport-required')
    start=monotonic();wall=clock()
    with handoff.view.cycles.c.source_lock(home,wallet) as root:
        book=transport._open(root,wallet,pool,clock)
        try:
            with original.ExitSubmission(book).snapshot():
                record,ctx,retired,signed,saved=load(root,book,wallet,pool,expected,clock)
                if saved is not None:return public(record,saved)
                request,_,stamp=handoff.current(book,record,ctx,retired,clock)
            def guard(method=None):
                nonlocal wall
                now=clock();check(wall<=now and 0<=monotonic()-start<120,'successor-transport-clock-budget');wall=now
                handoff.live_guard(root,book,request,stamp,clock)
            guard()
            rpc=transport.SendRpc(opener,guard=guard)
            proof={'genesisBefore':rpc.request('getGenesisHash',[])}
            check(transport.received(proof['genesisBefore'])==transport.GENESIS['devnet'],'successor-transport-wrong-cluster')
            proof['blockhash']=rpc.request('isBlockhashValid',[request['packet']['policy']['blockhash'],dict(commitment='confirmed',minContextSlot=signed['minimumContextSlot'])])
            slot,valid=transport.context(proof['blockhash'],signed['minimumContextSlot']);check(valid is True,'successor-transport-blockhash')
            message=base64.b64encode(original.decode_wire(signed['signed']['signedWireBase64'])[1]).decode()
            proof['fee']=rpc.request('getFeeForMessage',[message,dict(commitment='confirmed',minContextSlot=slot)])
            proof['genesisAfter']=rpc.request('getGenesisHash',[])
            with book.j.transaction():
                fresh,ctx,retired,current,saved=load(root,book,wallet,pool,expected,clock)
                check(fresh==record and current==signed and saved is None,'successor-transport-source-changed')
                handoff.current(book,fresh,ctx,retired,clock)
                minimum=original.proof_check(proof,current);guard()
                boundary=dict(kind='boundary',format=VERSION,successorSha256=expected,retirementSha256=record['retirementSha256'],
                    requestSha256=signed['requestSha256'],signingHeadSha256=signed['headSha256'],
                    wireSha256=signed['signed']['wireSha256'],signature=signed['signed']['signature'],endpoint=transport.ENDPOINT,preflight=deepcopy(proof))
                append(book,boundary,None,clock());guard()
            # A committed boundary consumes the only application send attempt,
            # even if the process stops or the deadline expires before transport.
            guard()
            item=rpc.request('sendTransaction',[signed['signed']['signedWireBase64'],dict(encoding='base64',skipPreflight=False,
                preflightCommitment='confirmed',maxRetries=0,minContextSlot=minimum)])
            with book.j.transaction():
                _,_,_,_,saved=load(root,book,wallet,pool,expected,clock)
                check(saved is not None and saved['eventCount']==1,'successor-transport-ack-order')
                kind='transport-unknown'
                if item.get('state')=='received':kind='rpc-acknowledged' if item.get('result')==boundary['signature'] else 'quarantined'
                append(book,dict(kind='ack',boundarySha256=digest(boundary),state=kind),saved,clock())
                saved=replay(book,record,signed,clock())
            return public(record,saved,rpc)
        finally:book.close()


@handoff.view.cycles.binding.operation
@handoff.successor.history.fresh_signing.timing.signature_replay
def _recover(home,wallet,pool,expected,*,opener=None,clock=handoff.view.now):
    """Read-only RPC on this generation; persist evidence, never send or sign."""
    check(opener is not None and callable(getattr(opener,'open',None)) and bool(opener),'successor-injected-transport-required')
    with handoff.view.cycles.c.source_lock(home,wallet) as root:
        book=transport._open(root,wallet,pool,clock)
        try:
            with original.ExitSubmission(book).snapshot():
                record,_,_,signed,saved=load(root,book,wallet,pool,expected,clock)
            if saved is None or saved['state'] in ('quarantined','successor-finalized-evidence','successor-failed-evidence'):return public(record,saved)
            check(len(saved['captures'])<MAX_CAPTURES,'successor-transport-capture-cap')
            started=clock();rpc=transport.ReceiptRpc(opener)
            ev={k:dict(state='not-requested') for k in ('genesisBefore','signatureStatus','transaction','genesisAfter')}
            ev['genesisBefore']=rpc.request('getGenesisHash',[])
            if ev['genesisBefore'].get('state')=='received' and ev['genesisBefore'].get('result')==transport.GENESIS['devnet']:
                sig=signed['signed']['signature']
                ev['signatureStatus']=rpc.request('getSignatureStatuses',[[sig],dict(searchTransactionHistory=True)])
                ev['transaction']=rpc.request('getTransaction',[sig,dict(encoding='base64',commitment='finalized',maxSupportedTransactionVersion=0)])
                ev['genesisAfter']=rpc.request('getGenesisHash',[])
            with book.j.transaction():
                fresh,_,_,current,state=load(root,book,wallet,pool,expected,clock)
                check(fresh==record and current==signed and state==saved,'successor-transport-source-changed')
                uint(started,clock(),'successor-transport-recovery-clock',minimum=state['lastAtMs'])
                append(book,dict(kind='capture',boundarySha256=digest(state['boundary']),startedAtMs=started,rpcEvidence=ev),state,clock())
                state=replay(book,record,signed,clock())
            return public(record,state,rpc)
        finally:book.close()


@handoff.view.cycles.binding.operation
@handoff.successor.history.fresh_signing.timing.signature_replay
def _status(home,wallet,pool,expected,*,clock=handoff.view.now):
    with handoff.view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
        book=transport._open(root,wallet,pool,clock)
        try:
            with original.ExitSubmission(book).snapshot():
                record,_,_,_,saved=load(root,book,wallet,pool,expected,clock)
                return public(record,saved)
        finally:book.close()
