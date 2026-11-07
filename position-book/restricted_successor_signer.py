"""Internal opt-in successor key process and keyless saved-ACK recovery.

No live CLI, RPC, submission, automatic re-signing or reservation release.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import successor_signing_handoff as handoff
from contract import digest,fields,uint
from core import check,private_file
from journal import read_only_journals

VERSION='restricted-successor-signer-1'
ATTEMPT='successor-signer-attempt.json'
ACK='successor-signer-ack.json'


def _marker(root,book,state):
    check(state is not None,'successor-signer-boundary-required')
    path=handoff.preparation.entry.submission.handoff.storage(root).parent
    v=json.loads(private_file(path/ATTEMPT,1024))
    fields(v,{'format','requestSha256','signingHeadSha256','successorSha256','retirementSha256','atMs'},'successor-signer-attempt-schema')
    boundary=book.db.execute('SELECT hash,at_ms FROM admission_successor_signing WHERE seq=1').fetchone()
    req=state['request']
    check(boundary is not None and v['format']=='successor-signer-attempt-1' and
          v['requestSha256']==state['requestSha256'] and v['signingHeadSha256']==boundary['hash'] and
          v['successorSha256']==req['successorSha256'] and v['retirementSha256']==req['retirementSha256'],
          'successor-signer-attempt-binding')
    uint(v['atMs'],min(book.j.now(),req['validUntilExclusiveMs']-1),'successor-signer-attempt-clock',minimum=boundary['at_ms'])
    return v


def _ack(root,book,state):
    _marker(root,book,state)
    path=handoff.preparation.entry.submission.handoff.storage(root).parent
    v=json.loads(private_file(path/ACK,4096))
    fields(v,{'format','requestSha256','signedTransactionBase64','wireSha256'},'successor-signer-ack-schema')
    check(v['format']=='successor-signer-ack-1' and v['requestSha256']==state['requestSha256'],'successor-signer-ack-binding')
    raw=base64.b64decode(v['signedTransactionBase64'],validate=True)
    check(hashlib.sha256(raw).hexdigest()==v['wireSha256'],'successor-signer-ack-hash')
    handoff.original.signed_check(v['signedTransactionBase64'],state['request'])
    check(state['signed'] is None or state['signed']['signedWireBase64']==v['signedTransactionBase64'],
          'successor-signer-ack-conflict')
    return v['signedTransactionBase64']


def inspect_markers(root,book,state):
    """Caller replays the successor in the same pinned source/ledger snapshot."""
    path=handoff.preparation.entry.submission.handoff.storage(root).parent
    attempt=os.path.lexists(path/ATTEMPT);ack=os.path.lexists(path/ACK)
    if attempt or ack:
        _marker(root,book,state)
        if ack:_ack(root,book,state)
    return dict(successorBackendAttemptPresent=attempt,successorBackendAcknowledgmentPresent=ack)


def _invoke(root,wallet,pool,expected,request,clock):
    """Internal child/ACK adapter, only within handoff._dispatch's locked phases.

    The parent fully replays before the child and again after this adapter returns,
    before appending its acknowledgment. Here re-read the committed candidate and
    signing boundary and bind the child ACK to the exact request. Repeating the
    complete historical replay here adds no intervening write/transport boundary.
    This return is a signed response, not a validated position or send permission.
    """
    check(request['successorSha256']==expected,'successor-backend-request-mismatch')
    node=shutil.which('node');check(node is not None,'node-runtime-unavailable')
    r=subprocess.run([str(Path(node).resolve()),str(Path(__file__).with_name('successor_signer.mjs'))],
        input=json.dumps(dict(directory=str(root),requestSha256=digest(request))),text=True,
        capture_output=True,timeout=5,env={'PATH':os.defpath})
    check(r.returncode==0 and r.stdout=='{"state":"successor-signed-recorded"}','restricted-successor-signer-refused')
    with read_only_journals():
        b=handoff.preparation.entry.submission._open(root,wallet,pool,clock)
        try:
            with handoff.successor.history.lifecycle.admission_read_lock(b.j.path):
                record=handoff.successor.row(b)
                check(record is not None and digest(record)==expected,'successor-backend-candidate-mismatch')
                state=handoff.read(b,record,clock())
                check(state is not None and state['state']=='successor-signing-unknown' and
                      state['request']==request and state['requestSha256']==digest(request),
                      'successor-backend-boundary-mismatch')
                return _ack(root,b,state)
        finally:b.close()


def _public(r,invoked=False):
    # Invocation can fail after durable attempt: never imply every call signed.
    r.update(format=VERSION,backendConfigured=True,backendInvokedThisRun=invoked,
             privateKeyAccessPossibleThisRun=invoked,liveKeyBackendConnected=True)
    return r


def _dispatch(home,wallet,pool,expected,*,allow_private_key_signing=False,clock=handoff.view.now):
    check(allow_private_key_signing is True,'explicit-successor-private-key-opt-in-required')
    root=Path(home).absolute()
    r=handoff._dispatch(root,wallet,pool,expected,
        signer_adapter=lambda request:_invoke(root,wallet,pool,expected,request,clock),clock=clock)
    return _public(r,r['signerAdapterCallsThisRun']==1)


@handoff.view.cycles.binding.operation
@handoff.successor.history.fresh_signing.timing.signature_replay
def _recover(home,wallet,pool,expected,*,clock=handoff.view.now):
    """Semantically replay and acknowledge existing backend files, without a key."""
    with handoff.view.cycles.c.source_lock(home,wallet) as root:
        b=handoff.preparation.entry.submission._open(root,wallet,pool,clock)
        try:
            with b.j.transaction():
                record,_,_,state=handoff.load(root,b,wallet,pool,expected,clock)
                wire=_ack(root,b,state)
                state=handoff.acknowledge(b,record,wire,clock)
            return _public(handoff.public(state,record,clock(),handoff.original.stopped(root,b)))
        finally:b.close()
