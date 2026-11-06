"""Internal opt-in exit key backend; no execution CLI, RPC or transaction sender."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import exit_signing_handoff as handoff
from pre_sign_admission import Admission
from contract import digest,fields,uint
from core import check,private_file
from journal import read_only_journals

VERSION='restricted-exit-signer-1'
ATTEMPT='exit-signer-attempt.json'
ACK='exit-signer-ack.json'


def attempt(root,book):
    return _attempt_for_state(root,book,handoff.read(book,book.j.now()))


def _attempt_for_state(root,book,state):
    check(state is not None,'exit-signer-boundary-required')
    path=handoff.preparation.entry.submission.handoff.storage(root).parent
    v=json.loads(private_file(path/ATTEMPT,1024))
    fields(v,{'format','requestSha256','signingHeadSha256','preparationSha256','atMs'},'exit-signer-attempt-schema')
    boundary=book.db.execute('SELECT hash,at_ms FROM admission_exit_signing WHERE seq=1').fetchone()
    check(v['format']=='exit-signer-attempt-1' and v['requestSha256']==state['requestSha256'] and
          v['signingHeadSha256']==boundary['hash'] and v['preparationSha256']==state['request']['preparationSha256'],
          'exit-signer-attempt-binding')
    uint(v['atMs'],min(book.j.now(),state['request']['validUntilExclusiveMs']-1),'exit-signer-attempt-clock',minimum=boundary['at_ms'])
    return state


def acknowledgment(root,book):
    return _read_ack(root,book,attempt(root,book))


def _acknowledgment_in_snapshot(root,book,state):
    """Internal transport use with its just-replayed signing state.

    The caller owns one read-only transaction on this book. No state is cached,
    and the attempt/ack files, database boundary and signed wire are rechecked.
    Standalone acknowledgment/recovery always replays the ledger itself.
    """
    check(book.db.in_transaction and book.db.execute('PRAGMA query_only').fetchone()[0]==1,
          'exit-ack-read-snapshot-required')
    return _read_ack(root,book,_attempt_for_state(root,book,state))


def _read_ack(root,book,state):
    path=handoff.preparation.entry.submission.handoff.storage(root).parent
    ack=json.loads(private_file(path/ACK,4096))
    fields(ack,{'format','requestSha256','signedTransactionBase64','wireSha256'},'exit-signer-ack-schema')
    check(ack['format']=='exit-signer-ack-1' and ack['requestSha256']==state['requestSha256'],'exit-signer-ack-binding')
    raw=base64.b64decode(ack['signedTransactionBase64'],validate=True)
    check(hashlib.sha256(raw).hexdigest()==ack['wireSha256'],'exit-signer-ack-hash')
    handoff.signed_check(ack['signedTransactionBase64'],state['request'])
    if state['signed'] is not None:
        check(state['signed']['signedWireBase64']==ack['signedTransactionBase64'],'exit-signer-ack-conflict')
    return ack['signedTransactionBase64']


def _invoke(root,request):
    node=shutil.which('node');check(node is not None,'node-runtime-unavailable')
    r=subprocess.run([str(Path(node).resolve()),str(Path(__file__).with_name('exit_signer.mjs'))],
        input=json.dumps(dict(directory=str(root),requestSha256=digest(request))),text=True,
        capture_output=True,timeout=5,env={'PATH':os.defpath})
    check(r.returncode==0 and r.stdout=='{"state":"exit-signed-recorded"}','restricted-exit-signer-refused')
    with read_only_journals():
        b=Admission(handoff.preparation.entry.submission.handoff.storage(root))
        try:return acknowledgment(root,b)
        finally:b.close()


def dispatch(home,wallet,pool,*,allow_private_key_signing=False,clock=handoff.view.now):
    check(allow_private_key_signing is True,'explicit-exit-private-key-opt-in-required')
    root=Path(home).absolute()
    r=handoff.dispatch(root,wallet,pool,signer_adapter=lambda request:_invoke(root,request),clock=clock)
    calls=r['signerAdapterCallsThisRun']
    r.update(format=VERSION,backendConfigured=True,backendInvokedThisRun=calls==1,
             signaturesCreatedThisRun=calls,privateKeyAccessedThisRun=calls==1,liveKeyBackendConnected=True)
    return r


def recover(home,wallet,pool,*,clock=handoff.view.now):
    """Record the existing backend acknowledgment; never open a key or re-sign."""
    with handoff.view.cycles.c.source_lock(home,wallet) as root:
        b=handoff.preparation.entry.submission._open(root,wallet,pool,clock)
        try:
            wire=acknowledgment(root,b);state=handoff.acknowledge(b,wire,clock)
            r=handoff.public(state,clock(),handoff.stopped(root,b))
            r.update(format=VERSION,backendConfigured=True,backendInvokedThisRun=False,
                     signaturesCreatedThisRun=0,privateKeyAccessedThisRun=False,liveKeyBackendConnected=True)
            return r
        finally:b.close()
