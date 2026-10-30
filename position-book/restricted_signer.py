"""Internal opt-in devnet signer adapter. No live CLI, RPC or sending capability."""
import hashlib
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess

import signer_handoff as handoff
from pre_sign_admission import Admission
from core import check, private_file
from contract import digest, fields
from journal import read_only_journals

VERSION = 'restricted-admission-signer-1'


def acknowledgment(root, book):
    """Read existing private acknowledgment; never call or retry a signer."""
    path = handoff.storage(root).parent
    state, _, _, _ = book.read()
    check(state is not None and state.get('signingRequestSha256'), 'signer-request-missing')
    expected_hash = state['signingRequestSha256']
    boundary = book.db.execute('SELECT hash,at_ms FROM admission_events WHERE seq=3').fetchone()
    check(boundary is not None, 'signer-boundary-missing')
    attempt = json.loads(private_file(path/'signer-attempt.json', 1024))
    fields(attempt, {'format','requestSha256','admissionHeadSha256','atMs'}, 'signer-attempt-schema')
    check(attempt['format'] == 'admission-signer-attempt-1' and attempt['requestSha256'] == expected_hash,
          'signer-attempt-binding')
    check(attempt['admissionHeadSha256'] == boundary['hash'] and type(attempt['atMs']) is int and
          boundary['at_ms'] <= attempt['atMs'] < state['validUntilExclusiveMs'] and
          attempt['atMs'] <= book.j.now(), 'signer-attempt-boundary')
    ack = json.loads(private_file(path/'signer-ack.json', 4096))
    fields(ack, {'format','requestSha256','signedTransactionBase64','wireSha256'}, 'signer-ack-schema')
    check(ack['format'] == 'admission-signer-ack-1' and ack['requestSha256'] == expected_hash,
          'signer-ack-binding')
    raw = base64.b64decode(ack['signedTransactionBase64'], validate=True)
    check(hashlib.sha256(raw).hexdigest() == ack['wireSha256'], 'signer-ack-wire-hash')
    return ack['signedTransactionBase64']


def _invoke(root, request):
    node = shutil.which('node'); check(node is not None, 'node-runtime-unavailable')
    request_hash = digest(request)
    # Caller holds the source lock. Child independently reads the committed ledger,
    # reconstructs the fixed message and owns a second durable one-shot boundary.
    result = subprocess.run([str(Path(node).resolve()), str(Path(__file__).with_name('admission_signer.mjs'))],
        input=json.dumps(dict(directory=str(root), requestSha256=request_hash)), text=True,
        capture_output=True, timeout=5, env={'PATH':os.defpath})
    check(result.returncode == 0 and result.stdout == '{"state":"signed-recorded"}', 'restricted-admission-signer-refused')
    with read_only_journals():
        book = Admission(handoff.storage(root))
        try:
            check(book.read()[0]['signingRequestSha256'] == request_hash, 'signer-request-changed')
            return acknowledgment(root, book)
        finally:
            book.close()


def dispatch(home, wallet, pool, evidence, policy, *, allow_private_key_signing=False, clock=handoff.bridge.view.now):
    """For a separately authorized controlled scope only. No runtime uses this API."""
    check(allow_private_key_signing is True, 'explicit-private-key-opt-in-required')
    root = Path(home).absolute()
    result = handoff.dispatch(root, wallet, pool, evidence, policy,
                             signer_adapter=lambda request: _invoke(root, request), clock=clock)
    result.update(format=VERSION, backendConfigured=True,
                  backendInvokedThisRun=result['signerAdapterCallsThisRun'] == 1,
                  signaturesCreatedThisRun=result['signerAdapterCallsThisRun'],
                  privateKeyAccessedThisRun=result['signerAdapterCallsThisRun'] == 1)
    # Existing generic public flag describes an adapter without a key backend.
    result['liveKeyBackendConnected'] = True
    return result


def recover(home, wallet, pool, *, clock=handoff.bridge.view.now):
    """Save an existing acknowledgment after a lost response, with no key access."""
    with handoff.bridge.view.cycles.c.source_lock(home, wallet) as root:
        b = Admission(handoff.storage(root), clock=clock)
        try:
            roles = b.policy['scope']['accounts']
            check(roles['wallet'] == wallet and roles['pool'] == pool, 'signer-recovery-scope')
            if handoff.bridge.view.cycles.c.submit.swap.stop(root): b.stop()
            state = b.read()[0]
            check(state is not None and state.get('signingRequestSha256'), 'signer-request-missing')
            b.record_signed(acknowledgment(root, b))
            if b.status()['state'] in ('signed-recorded','stopped'): b.stage_accounting_handoff()
            result = handoff.public(b)
            result.update(format=VERSION, backendConfigured=True, backendInvokedThisRun=False,
                          signaturesCreatedThisRun=0, privateKeyAccessedThisRun=False)
            return result
        finally:
            b.close()
