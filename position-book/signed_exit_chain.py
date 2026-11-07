"""Read-only devnet observation of an exact signed, locally unsubmitted exit."""
from datetime import datetime, timezone
import json
import time
import urllib.error
import urllib.request

import exit_history_timing as history
from contract import digest, uint
from core import check
from journal import read_only_journals
from recorded_capture import Client, ENDPOINTS, GENESIS, NoRedirect

VERSION = 'signed-exit-chain-observation-1'
MAX_RESPONSE = 65536
view = history.view


class Response:
    def __init__(self, response, deadline, monotonic):
        self.response, self.deadline, self.monotonic = response, deadline, monotonic
    def __enter__(self): return self
    def __exit__(self, *args): self.response.close()
    def read(self, size):
        limit = min(size, MAX_RESPONSE + 1); chunks = []; total = 0
        reader = getattr(self.response, 'read1', self.response.read)
        while total < limit:
            check(self.monotonic() < self.deadline, 'chain-read-budget')
            chunk = reader(min(4096, limit-total))
            check(self.monotonic() < self.deadline, 'chain-read-budget')
            if not chunk:
                check(getattr(self.response, 'length', None) in (None, 0), 'chain-response-incomplete')
                break
            chunks.append(chunk); total += len(chunk)
        check(total <= MAX_RESPONSE, 'chain-response-cap')
        return b''.join(chunks)


class BoundedReads:
    def __init__(self, plan, opener, monotonic, budget=30):
        check(0 < budget <= 30, 'chain-read-budget')
        self.budget = budget
        self.plan, self.monotonic = plan, monotonic
        self.opener = opener if opener is not None else urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect())
        self.started = monotonic(); self.calls = []

    def open(self, request, timeout):
        remaining = self.budget - (self.monotonic() - self.started)
        check(0 < remaining <= 30 and len(self.calls) < len(self.plan), 'chain-read-budget')
        body = json.loads(request.data)
        method, params = self.plan[len(self.calls)]
        check(request.full_url == ENDPOINTS['devnet'] and request.get_method() == 'POST' and
              body == dict(jsonrpc='2.0', id=len(self.calls)+1, method=method, params=params),
              'chain-request-binding')
        self.calls.append(method)
        try:
            return Response(self.opener.open(request, timeout=min(timeout, remaining)),
                            self.started+self.budget, self.monotonic)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise


class ChainRpc(Client):
    METHODS = ('getGenesisHash', 'isBlockhashValid', 'getSignatureStatuses')
    REQUEST_CAP = 4


def local(root, book, wallet, pool, expected, clock):
    record = history.lifecycle.preparation.saved(book, clock())
    check(record is not None and digest(record) == expected, 'chain-preparation-mismatch')
    timeline = history.signing_timeline(root, book, record, clock())
    check(timeline.get('state') == 'expired-signed-locally-unsubmitted-held', 'chain-held-expired-required')
    phase, _, amounts, _, _, _ = history.lifecycle.projection(book, root, wallet, pool, clock)
    check(phase in ('exit-signed-not-submitted','exit-retired-held') and amounts is not None, 'chain-held-position-required')
    with history.transport.ExitSubmission(book).snapshot():
        state = history.transport.ExitSubmission(book).signing()
        check(state['request']['preparationSha256'] == expected, 'chain-signing-mismatch')
        history.backend._attempt_record_for_state(root, book, state)
        check(history.backend._read_ack(root, book, state) == state['signed']['signedWireBase64'], 'chain-ack-mismatch')
    return dict(preparationSha256=expected, signingStateSha256=digest(state),
        signature=state['signed']['signature'], blockhash=state['request']['packet']['policy']['blockhash'],
        minimumContextSlot=state['minimumContextSlot'], scopedAccounting=amounts)


def classify(validity, statuses, minimum):
    rpc = history.transport.transport
    block_slot, valid = rpc.context(validity, minimum)
    check(type(valid) is bool, 'chain-blockhash-shape')
    status_slot, values = rpc.context(statuses, block_slot)
    check(type(values) is list and len(values) == 1, 'chain-status-shape')
    row = values[0]; summary = None
    if row is not None:
        check(type(row) is dict and all(k in row for k in ('slot','err','confirmations','confirmationStatus')), 'chain-status-shape')
        uint(row['slot'], status_slot, 'chain-status-slot', minimum=minimum)
        confirmation = row['confirmationStatus']
        check(confirmation in ('processed','confirmed','finalized'), 'chain-confirmation-shape')
        if confirmation == 'finalized': check(row['confirmations'] is None, 'chain-finalized-shape')
        else: uint(row['confirmations'], 2**53-1, 'chain-confirmations')
        check(row['err'] is None or type(row['err']) in (dict,str), 'chain-error-shape')
        check(len(json.dumps(row['err'])) <= 4096, 'chain-error-cap')
        summary = dict(slot=row['slot'], confirmationStatus=confirmation,
                       executionErrorReported=row['err'] is not None)
    label = ('signature-status-observed-receipt-required' if summary else
             'signature-not-found-blockhash-valid-held' if valid else
             'signature-not-found-blockhash-invalid-held')
    return dict(classification=label, blockhashValidAtFinalized=valid,
        blockhashContextSlot=block_slot, signatureStatusContextSlot=status_slot,
        signatureFound=row is not None, signatureStatus=summary,
        absenceProvesNonExecution=False, receiptEffectsReconciled=False,
        nextAction='inspect-exact-receipt' if summary else 'preserve-hold-pending-recovery-policy')


@view.cycles.binding.operation
@history.fresh_signing.timing.signature_replay
def inspect(home, wallet, pool, expected, *, opener=None, clock=view.now, monotonic=time.monotonic):
    result = dict(format=VERSION, state='chain-observation-unavailable', observation=None,
        identity=None, scopedAccounting=None, diagnosticCode=None, networkRequests=0,
        requestMethods=[], databaseConnectionsReadOnly=True, sourceStateChanged=False,
        privateKeyAccessed=False, signaturesCreated=0, transactionsSent=0,
        reservationsReleasedThisRun=False, replacementAuthorized=False, retryAllowed=False,
        executionApproved=False, mainnetSupported=False,
        limitations=['Single fixed devnet RPC provider claims, not cryptographic finality proof.',
          'No local send boundary does not prove that the signed wire was never broadcast elsewhere.',
          'A missing signature status and invalid blockhash do not prove non-execution or release funds.',
          'Status alone does not reconcile the exact transaction receipt, fees or token effects.'])
    start = monotonic(); wall = clock(); transport = None
    try:
        check(type(expected) is str and len(expected) == 64 and all(c in '0123456789abcdef' for c in expected), 'chain-preparation-id')
        with view.cycles.c.source_lock(home,wallet) as root, read_only_journals():
            book = history.lifecycle.entry.submission._open(root,wallet,pool,clock)
            try:
                with history.lifecycle.admission_read_lock(book.j.path):
                    before = local(root,book,wallet,pool,expected,clock)
                    plan = [('getGenesisHash',[]), ('isBlockhashValid',[before['blockhash'],
                        dict(commitment='finalized',minContextSlot=before['minimumContextSlot'])]),
                        ('getSignatureStatuses',[[before['signature']],dict(searchTransactionHistory=True)]),
                        ('getGenesisHash',[])]
                    elapsed = monotonic()-start
                    check(0 <= elapsed < 120, 'chain-operation-budget')
                    transport = BoundedReads(plan,opener,monotonic,budget=min(30,120-elapsed))
                    rpc = ChainRpc('devnet',transport); evidence = []
                    for method, params in plan:
                        item = rpc.request(method,params)
                        value = history.transport.transport.received(item)
                        if method == 'getGenesisHash': check(value == GENESIS['devnet'], 'chain-genesis-mismatch')
                        evidence.append(item)
                    check(0 <= monotonic()-transport.started <= 30, 'chain-read-budget')
                    observation = classify(evidence[1], evidence[2], before['minimumContextSlot'])
                    after = local(root,book,wallet,pool,expected,clock)
                    check(before == after, 'chain-local-evidence-changed')
                    stamp = clock(); uint(stamp,2**53-1,'chain-clock',minimum=wall)
                    check(0 <= monotonic()-start <= 120, 'chain-operation-budget')
                    result.update(state='signed-exit-chain-observed',observation=observation,
                        identity=dict(preparationSha256=expected,signingStateSha256=before['signingStateSha256'],
                            signatureSha256=digest(before['signature']),blockhashSha256=digest(before['blockhash'])),
                        scopedAccounting=before['scopedAccounting'],observedAtMs=stamp)
            finally: book.close()
    except view.ERRORS:
        result['diagnosticCode']='signed-exit-chain-evidence-unavailable'
    finally:
        if transport is not None:
            result.update(networkRequests=len(transport.calls),requestMethods=list(transport.calls))
    result['capturedAt']=datetime.now(timezone.utc).isoformat()
    return result
