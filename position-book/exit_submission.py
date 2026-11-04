"""Internal devnet exit transport and bounded finality evidence, no execution CLI.

A committed application attempt is uncertainty, never proof of chain delivery.
Receipt effects, residual balances and allocation release remain separate gates.
"""
import base64
from copy import deepcopy
from contextlib import contextmanager
import json

import admission_submission as transport
import exit_signing_handoff as handoff
import restricted_exit_signer as backend
from contract import digest, fields, uint
from core import check
from journal import read_only_journals
from pre_sign_admission import encoded, Admission
from wire import decode_wire

VERSION='exit-submission-1'
BOUNDARY='admission_exit_submission'
ACK='admission_exit_submission_ack'
CAPTURES='admission_exit_rpc_captures'
MAX_CAPTURES=8
MAX_CAPTURE_BYTES=4*1024*1024
TERMINAL=('exit-finalized-evidence','exit-failed-evidence')
view=handoff.view


def proof_check(proof,state):
    fields(proof,{'genesisBefore','blockhash','fee','genesisAfter'},'exit-preflight-schema')
    check(transport.received(proof['genesisBefore'])==transport.received(proof['genesisAfter'])==transport.GENESIS['devnet'],'exit-wrong-cluster')
    slot,valid=transport.context(proof['blockhash'],state['minimumContextSlot']);check(valid is True,'exit-blockhash-unavailable')
    fee_slot,fee=transport.context(proof['fee'],slot)
    uint(fee,int(state['request']['feeCapLamports']),'exit-fee-cap',minimum=1)
    return fee_slot


def classify(capture,state,minimum):
    """Exact-wire finalized RPC observation only; does not apply token effects."""
    ev=capture['rpcEvidence']
    for k in ('genesisBefore','genesisAfter'):
        item=ev[k]
        if item.get('state')=='received' and item.get('result')!=transport.GENESIS['devnet']:return 'quarantined',None
    if any(ev[k].get('state')!='received' for k in ev):return 'collection-unknown',None
    statuses=ev['signatureStatus'].get('result');tx=ev['transaction'].get('result')
    if type(statuses) is not dict or type(statuses.get('value')) is not list or len(statuses['value'])!=1:return 'quarantined',None
    context=statuses.get('context')
    if type(context) is not dict or type(context.get('slot')) is not int or not minimum<=context['slot']<=2**53-1:return 'quarantined',None
    status=statuses['value'][0]
    if status is None or tx is None:return 'collection-unknown',None
    if type(status) is not dict or type(tx) is not dict:return 'quarantined',None
    if tx.get('transaction')!=[state['signed']['signedWireBase64'],'base64']:return 'quarantined',None
    slot=tx.get('slot');meta=tx.get('meta')
    if type(slot) is not int or not minimum<=slot<=context['slot'] or type(status.get('slot')) is not int or status['slot']!=slot or type(meta) is not dict:return 'quarantined',None
    if 'err' not in meta or 'err' not in status or meta['err']!=status['err']:return 'quarantined',None
    decoded=decode_wire(state['signed']['signedWireBase64'])[4]
    if tx.get('version') not in (None,decoded['version']):return 'quarantined',None
    if status.get('confirmationStatus')!='finalized' or 'confirmations' not in status or status['confirmations'] is not None:return 'collection-unknown',None
    failed=meta['err'] is not None
    return ('exit-failed-evidence' if failed else 'exit-finalized-evidence'),dict(
        slot=slot,failed=failed,wireSha256=state['signed']['wireSha256'],
        signature=state['signed']['signature'],transactionSha256=digest(tx))


class ExitSubmission:
    def __init__(self,book):self.b=book;self.db=book.db

    @contextmanager
    def reader(self):
        with read_only_journals():
            book=Admission(self.b.j.path,clock=self.b.j.clock)
            try:yield ExitSubmission(book)
            finally:book.close()

    def signing(self):
        active=[]
        state=handoff.read(self.b,self.b.j.now(),_preparation_sink=active.append)
        check(state is not None and state['signed'] is not None,'exit-signed-ack-required')
        # Use the same active generation as the signing request. An expired
        # original can have older slots than the linked replacement.
        check(len(active)==1 and digest(active[0])==state['request']['preparationSha256'],
              'exit-preparation-required')
        e=active[0]['evidence']
        slots=[e['simulationItem']['result']['context']['slot'],e['capture']['evidence']['accounts']['result']['context']['slot'],e['price']['quote']['contextSlot']]
        for slot in slots:uint(slot,2**53-1,'exit-minimum-context')
        state['minimumContextSlot']=max(slots)
        return state

    def row(self,table,cap):
        found=self.db.execute('SELECT type FROM sqlite_master WHERE name=?',(table,)).fetchone()
        if not found:return None
        check(found[0]=='table','exit-transport-table')
        rows=self.db.execute(f'SELECT id,CASE WHEN length(value)<=? THEN value ELSE NULL END value FROM {table} LIMIT 2',(cap,)).fetchall()
        check(len(rows)==1 and rows[0]['id']==1 and type(rows[0]['value']) is str,'exit-transport-record')
        v=json.loads(rows[0]['value']);check(encoded(v)==rows[0]['value'],'exit-transport-canonical');return v

    def boundary(self):
        state=self.signing();v=self.row(BOUNDARY,16384)
        if v is None:return None
        fields(v,{'format','requestSha256','signingHeadSha256','wireSha256','signature','endpoint','atMs','preflight'},'exit-boundary-schema')
        check(v['format']==VERSION and v['requestSha256']==state['requestSha256'] and
              v['wireSha256']==state['signed']['wireSha256'] and v['signature']==state['signed']['signature'] and
              v['endpoint']==transport.ENDPOINT,'exit-boundary-binding')
        signed=self.db.execute('SELECT hash,at_ms FROM admission_exit_signing WHERE seq=2').fetchone()
        check(signed is not None and v['signingHeadSha256']==signed['hash'],'exit-boundary-head')
        uint(v['atMs'],min(self.b.j.now(),state['request']['validUntilExclusiveMs']-1),'exit-boundary-clock',minimum=signed['at_ms'])
        proof_check(v['preflight'],state)
        return v

    def mark(self,proof,root,wallet,pool,clock):
        with self.b.j.transaction():
            # The writer reservation excludes a concurrent ledger writer. A second
            # read-only connection replays source and raw evidence before commit.
            with read_only_journals():
                reader=transport._open(root,wallet,pool,clock)
                try:
                    check(ExitSubmission(reader).boundary() is None,'exit-already-attempted')
                    state=ExitSubmission(reader).signing()
                    check(state['state']=='exit-signed-recorded','exit-signing-not-usable')
                    request,_,_=handoff.current(root,reader,wallet,pool,clock)
                    check(request==state['request'],'exit-request-changed')
                    check(backend.acknowledgment(root,reader)==state['signed']['signedWireBase64'],'exit-backend-ack')
                finally:reader.close()
            proof_check(proof,state);now=clock()
            check(state['lastAtMs']<=now<request['validUntilExclusiveMs'] and not handoff.stopped(root,self.b),'exit-boundary-expired-or-stopped')
            v=dict(format=VERSION,requestSha256=state['requestSha256'],signingHeadSha256=state['headSha256'],
                wireSha256=state['signed']['wireSha256'],signature=state['signed']['signature'],endpoint=transport.ENDPOINT,
                atMs=now,preflight=deepcopy(proof))
            check(len(encoded(v).encode())<=16384,'exit-boundary-cap')
            self.db.execute(f'CREATE TABLE {BOUNDARY} (id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
            self.db.execute(f'INSERT INTO {BOUNDARY} VALUES(1,?)',(encoded(v),))
            check(now<=clock()<request['validUntilExclusiveMs'] and not handoff.stopped(root,self.b),'exit-boundary-expired-or-stopped')
        return v

    def acknowledge(self,item):
        with self.b.j.transaction():
            with self.reader() as reader:
                boundary=reader.boundary();check(boundary is not None,'exit-boundary-required')
                check(reader.row(ACK,1024) is None,'exit-ack-exists')
            state='transport-unknown'
            if item.get('state')=='received':state='rpc-acknowledged' if item.get('result')==boundary['signature'] else 'quarantined'
            now=self.b.j.now();check(now>=boundary['atMs'],'exit-ack-clock')
            v=dict(state=state,boundarySha256=digest(boundary),atMs=now)
            self.db.execute(f'CREATE TABLE {ACK} (id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL)')
            self.db.execute(f'INSERT INTO {ACK} VALUES(1,?)',(encoded(v),))

    def captures(self):
        boundary=self.boundary();exists=self.db.execute('SELECT type FROM sqlite_master WHERE name=?',(CAPTURES,)).fetchone()
        if not exists:return []
        check(exists[0]=='table' and boundary is not None,'exit-capture-boundary')
        rows=self.db.execute(f'SELECT seq,CASE WHEN length(value)<=? THEN value ELSE NULL END value,hash FROM {CAPTURES} ORDER BY seq LIMIT ?',
                             (MAX_CAPTURE_BYTES,MAX_CAPTURES+1)).fetchall()
        check(len(rows)<=MAX_CAPTURES,'exit-capture-cap')
        previous='';last=boundary['atMs'];result=[]
        for seq,r in enumerate(rows,1):
            check(r['seq']==seq and type(r['value']) is str,'exit-capture-row')
            v=json.loads(r['value']);fields(v,{'format','boundarySha256','previousSha256','startedAtMs','finishedAtMs','rpcEvidence'},'exit-capture-schema')
            check(encoded(v)==r['value'] and digest(v)==r['hash'] and v['format']==VERSION+'-capture' and
                v['boundarySha256']==digest(boundary) and v['previousSha256']==previous,'exit-capture-binding')
            uint(v['startedAtMs'],self.b.j.now(),'exit-capture-clock',minimum=last)
            uint(v['finishedAtMs'],self.b.j.now(),'exit-capture-clock',minimum=v['startedAtMs'])
            fields(v['rpcEvidence'],{'genesisBefore','signatureStatus','transaction','genesisAfter'},'exit-capture-evidence')
            check(all(type(x) is dict for x in v['rpcEvidence'].values()),'exit-capture-items')
            result.append(v);previous=r['hash'];last=v['finishedAtMs']
        return result

    def save_capture(self,started,evidence):
        with self.b.j.transaction():
            with self.reader() as reader:
                boundary=reader.boundary();check(boundary is not None,'exit-boundary-required')
                previous=reader.captures();check(len(previous)<MAX_CAPTURES,'exit-capture-cap')
            finished=self.b.j.now();uint(started,finished,'exit-capture-clock',minimum=previous[-1]['finishedAtMs'] if previous else boundary['atMs'])
            v=dict(format=VERSION+'-capture',boundarySha256=digest(boundary),previousSha256=digest(previous[-1]) if previous else '',
                startedAtMs=started,finishedAtMs=finished,rpcEvidence=deepcopy(evidence))
            check(len(encoded(v).encode())<=MAX_CAPTURE_BYTES,'exit-capture-size')
            self.db.execute(f'CREATE TABLE IF NOT EXISTS {CAPTURES} (seq INTEGER PRIMARY KEY,value TEXT NOT NULL,hash TEXT NOT NULL)')
            self.db.execute(f'INSERT INTO {CAPTURES} VALUES(?,?,?)',(len(previous)+1,encoded(v),digest(v)))
            check(self.db.execute('PRAGMA page_count').fetchone()[0]*self.db.execute('PRAGMA page_size').fetchone()[0]<=64*1024*1024,'exit-ledger-size-cap')

    def status(self,rpc=None):
        signed=self.signing();boundary=self.boundary();ack=self.row(ACK,1024)
        if ack is not None:
            fields(ack,{'state','boundarySha256','atMs'},'exit-ack-schema')
            check(boundary is not None and ack['boundarySha256']==digest(boundary) and ack['state'] in ('rpc-acknowledged','transport-unknown','quarantined'),'exit-ack-binding')
            uint(ack['atMs'],self.b.j.now(),'exit-ack-clock',minimum=boundary['atMs'])
        captures=self.captures();quarantined=signed['state']=='exit-signing-quarantined' or bool(ack and ack['state']=='quarantined')
        outcome=None;identity=None
        minimum=0 if boundary is None else proof_check(boundary['preflight'],signed)
        for c in captures:
            kind,summary=classify(c,signed,minimum)
            if kind=='quarantined':quarantined=True
            if kind in TERMINAL:
                h=digest(summary)
                if identity is not None and h!=identity:quarantined=True
                else:outcome=kind;identity=h
        state='not-attempted' if boundary is None else 'exit-submission-unknown'
        if ack and ack['state']=='rpc-acknowledged':state='rpc-acknowledged'
        if outcome:state=outcome
        if quarantined:state='quarantined'
        calls=[] if rpc is None else rpc.calls
        return dict(format=VERSION,state=state,applicationSendBoundaryRecorded=boundary is not None,
            rpcAcknowledgedSignature=bool(ack and ack['state']=='rpc-acknowledged'),receiptCaptureCount=len(captures),
            finalizedEvidenceObserved=bool(outcome and not quarantined),terminalEvidenceSha256=identity,
            networkRequestsThisRun=len(calls),sendRequestsThisRun=sum(x['method']=='sendTransaction' for x in calls),
            privateKeyAccessed=False,signaturesCreated=0,automaticRetryAllowed=False,executionApproved=False,
            receiptEffectsReconciled=False,residualInventoryVerified=False,reservationReleased=False,
            allocationTransferred=False,nextCycleAuthorized=False,runtimeIntegrated=False,
            provenanceBasis='Fixed devnet endpoint RPC claims and application journal; not cryptographic finality proof')


def submit(home,wallet,pool,*,allow_devnet_submit=False,opener=None,clock=view.now,_guard=None,_rpc_sink=None):
    check(allow_devnet_submit is True,'explicit-devnet-submit-required')
    check(_guard is None or callable(_guard),'exit-transport-guard')
    check(_rpc_sink is None or callable(_rpc_sink),'exit-transport-sink')
    with view.cycles.c.source_lock(home,wallet) as root:
        b=transport._open(root,wallet,pool,clock)
        try:
            s=ExitSubmission(b)
            if s.boundary() is not None:return s.status()
            state=s.signing();check(state['state']=='exit-signed-recorded','exit-signing-not-usable')
            handoff.current(root,b,wallet,pool,clock)
            check(backend.acknowledgment(root,b)==state['signed']['signedWireBase64'],'exit-backend-ack')
            if _guard is not None:_guard('before-preflight',state)
            rpc=transport.SendRpc(opener,guard=None if _guard is None else lambda method:_guard(method,state))
            if _rpc_sink is not None:_rpc_sink(rpc)
            proof={'genesisBefore':rpc.request('getGenesisHash',[])}
            check(transport.received(proof['genesisBefore'])==transport.GENESIS['devnet'],'exit-wrong-cluster')
            proof['blockhash']=rpc.request('isBlockhashValid',[state['request']['packet']['policy']['blockhash'],{'commitment':'confirmed','minContextSlot':state['minimumContextSlot']}])
            slot,valid=transport.context(proof['blockhash'],state['minimumContextSlot']);check(valid is True,'exit-blockhash-unavailable')
            message=base64.b64encode(decode_wire(state['signed']['signedWireBase64'])[1]).decode()
            proof['fee']=rpc.request('getFeeForMessage',[message,{'commitment':'confirmed','minContextSlot':slot}])
            proof['genesisAfter']=rpc.request('getGenesisHash',[])
            minimum=proof_check(proof,state)
            if _guard is not None:_guard('before-boundary',state)
            boundary=s.mark(proof,root,wallet,pool,clock)
            # Once committed, a crash here must never permit a retry.
            check(boundary['atMs']<=clock()<state['request']['validUntilExclusiveMs'] and not handoff.stopped(root,b),'exit-boundary-now-unknown')
            item=rpc.request('sendTransaction',[state['signed']['signedWireBase64'],dict(encoding='base64',skipPreflight=False,preflightCommitment='confirmed',maxRetries=0,minContextSlot=minimum)])
            s.acknowledge(item);return s.status(rpc)
        finally:b.close()


def recover(home,wallet,pool,*,opener=None,clock=view.now,_rpc_sink=None):
    """Observe only the original signature; no key access or sender invocation."""
    check(_rpc_sink is None or callable(_rpc_sink),'exit-recovery-sink')
    with view.cycles.c.source_lock(home,wallet) as root:
        b=transport._open(root,wallet,pool,clock)
        try:
            s=ExitSubmission(b);r=s.status()
            if not r['applicationSendBoundaryRecorded'] or r['state'] in (*TERMINAL,'quarantined'):return r
            check(r['receiptCaptureCount']<MAX_CAPTURES,'exit-capture-cap')
            started=clock();rpc=transport.ReceiptRpc(opener)
            if _rpc_sink is not None:_rpc_sink(rpc)
            ev={k:{'state':'not-requested'} for k in ('genesisBefore','signatureStatus','transaction','genesisAfter')}
            ev['genesisBefore']=rpc.request('getGenesisHash',[])
            if ev['genesisBefore'].get('state')=='received' and ev['genesisBefore'].get('result')==transport.GENESIS['devnet']:
                sig=s.signing()['signed']['signature']
                ev['signatureStatus']=rpc.request('getSignatureStatuses',[[sig],{'searchTransactionHistory':True}])
                ev['transaction']=rpc.request('getTransaction',[sig,dict(encoding='base64',commitment='finalized',maxSupportedTransactionVersion=0)])
                ev['genesisAfter']=rpc.request('getGenesisHash',[])
            s.save_capture(started,ev);return s.status(rpc)
        finally:b.close()


def status(home,wallet,pool,*,clock=view.now):
    with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
        b=transport._open(root,wallet,pool,clock)
        try:return ExitSubmission(b).status()
        finally:b.close()
