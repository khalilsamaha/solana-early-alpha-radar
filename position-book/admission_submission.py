"""Internal devnet-only one-attempt transport and bounded receipt collector.

No execution CLI, key access, allocation release or runtime integration. The
application boundary records uncertainty, not delivery or chain finality.
"""
import base64
from copy import deepcopy
import json

import admission_receipt as receipts
import restricted_signer
from pre_sign_admission import Admission, encoded
from contract import digest, fields, uint
from core import check
from recorded_capture import Client, GENESIS
from wire import decode_wire

handoff = receipts.handoff
VERSION = 'admission-submission-1'
ENDPOINT = 'https://api.devnet.solana.com'
MAX_CAPTURES = 8
MAX_CAPTURE_BYTES = 4 * 1024 * 1024


class SendRpc(Client):
    METHODS = ('getGenesisHash', 'isBlockhashValid', 'getFeeForMessage', 'sendTransaction')
    REQUEST_CAP = 5
    def __init__(self, opener=None): super().__init__('devnet', opener)
    def request(self, method, params):
        if method == 'sendTransaction':
            check(not any(x['method'] == method for x in self.calls), 'duplicate-send-refused')
        return super().request(method, params)


class ReceiptRpc(Client):
    METHODS = ('getGenesisHash', 'getSignatureStatuses', 'getTransaction')
    REQUEST_CAP = 4
    def __init__(self, opener=None): super().__init__('devnet', opener)


def received(item):
    check(type(item) is dict and item.get('state') == 'received' and 'result' in item,
          'rpc-evidence-unavailable')
    return item['result']


def context(item, minimum=0):
    result = received(item)
    check(type(result) is dict and type(result.get('context')) is dict and 'value' in result,
          'rpc-context-invalid')
    slot = result['context'].get('slot')
    uint(slot, 2**53-1, 'rpc-slot-invalid', minimum=minimum)
    return slot, result['value']


def preflight_check(proof, private, state):
    fields(proof, {'genesisBefore', 'blockhash', 'fee', 'genesisAfter'}, 'submission-preflight-shape')
    check(received(proof['genesisBefore']) == received(proof['genesisAfter']) == GENESIS['devnet'],
          'submission-wrong-cluster')
    slot, valid = context(proof['blockhash'])
    check(valid is True, 'submission-blockhash-unavailable')
    fee_slot, fee = context(proof['fee'], slot)
    uint(fee, int(state['entryFeeCapLamports']), 'submission-fee-cap', minimum=1)
    check(private['intent']['network'] == 'devnet', 'submission-devnet-only')
    return fee_slot


def normalized_package(capture, private, minimum_slot=0):
    """Replay a bounded collector record; metadata still consists of RPC claims."""
    ev = capture['rpcEvidence']
    before, after = ev['genesisBefore'], ev['genesisAfter']
    if any(x.get('state') == 'received' and x.get('result') != GENESIS['devnet'] for x in (before, after)):
        return 'quarantined', None
    if any(x.get('state') != 'received' for x in (before, after)):
        return 'collection-unknown', None
    if any(x.get('result') != GENESIS['devnet'] for x in (before, after)):
        return 'quarantined', None
    tx_item = ev['transaction']
    if tx_item.get('state') != 'received': return 'collection-unknown', None
    tx = tx_item.get('result')
    if tx is not None:
        if (type(tx) is not dict or tx.get('transaction') !=
                [private['signedTransactionBase64'], 'base64']):
            return 'quarantined', None
        if type(tx.get('slot')) is not int or tx['slot'] < minimum_slot:
            return 'quarantined', None
        decoded = decode_wire(private['signedTransactionBase64'])[4]
        if tx.get('version') not in (None, decoded['version']): return 'quarantined', None
        tx = dict(deepcopy(tx), transaction=decoded['transaction'], version=decoded['version'])
    package = dict(format='signed-token-evidence-1', signedTransactionBase64=private['signedTransactionBase64'],
        bundle=dict(format='intent-evidence-bundle-1', network='devnet', capturedAtMs=capture['finishedAtMs'],
            intent=deepcopy(private['intent']), rpcEvidence=dict(
                signatureStatus=deepcopy(ev['signatureStatus']), transaction=dict(state='received', result=tx))))
    return 'genesis-bound-collection', package


class Submission:
    """One transport boundary and up to eight observations in the admission DB."""
    def __init__(self, book):
        check(type(book) is Admission, 'submission-admission-required')
        self.b = book; self.db = book.db
        self.private = book.private_accounting_handoff()
        self.identity = digest({k:v for k,v in self.private.items() if k != 'signedTransactionBase64'})

    def state(self):
        state, _, head, at = self.b.read()
        check(state is not None and state['state'] in ('signed-recorded', 'stopped') and
              state.get('accountingHandoffSha256') == self.identity,
              'submission-handoff-changed')
        check(self.b.j.now() >= at, 'submission-clock-regressed')
        return state, head, at

    def row(self, table, maximum):
        exists = self.db.execute("SELECT type FROM sqlite_master WHERE name=?", (table,)).fetchone()
        if not exists: return None
        check(exists[0] == 'table', 'submission-table-type')
        # Table names are constants owned by this module, never user input.
        rows = self.db.execute(f'SELECT id, CASE WHEN length(value)<=? THEN value ELSE NULL END AS value FROM {table} LIMIT 2', (maximum,)).fetchall()
        check(len(rows) == 1 and rows[0]['id'] == 1 and type(rows[0]['value']) is str,
              'submission-record-shape')
        value = json.loads(rows[0]['value'])
        check(encoded(value) == rows[0]['value'], 'submission-record-canonical')
        return value

    def boundary(self):
        state, _, _ = self.state()
        value = self.row('admission_submission', 16384)
        if value is not None:
            fields(value, {'format','handoffSha256','wireSha256','signature','endpoint','atMs',
                           'admissionHeadSha256','preflight'}, 'submission-boundary-shape')
            check(value['format'] == VERSION and value['handoffSha256'] == self.identity and
                  value['wireSha256'] == self.private['wireSha256'] and
                  value['signature'] == self.private['intent']['signature'] and value['endpoint'] == ENDPOINT,
                  'submission-boundary-binding')
            uint(value['atMs'], state['validUntilExclusiveMs']-1, 'submission-boundary-clock',
                 minimum=state['signedRecordedAtMs'])
            check(value['atMs'] <= self.b.j.now(), 'submission-clock-regressed')
            row = self.db.execute('SELECT value,at_ms FROM admission_events WHERE hash=?', (value['admissionHeadSha256'],)).fetchone()
            check(row is not None and row['at_ms'] <= value['atMs'] and
                  json.loads(row['value']).get('accountingHandoffSha256') == self.identity and
                  json.loads(row['value'])['state'] == 'signed-recorded', 'submission-boundary-head')
            preflight_check(value['preflight'], self.private, state)
        return value

    def mark(self, proof):
        with self.b.j.transaction():
            check(self.boundary() is None, 'submission-already-attempted')
            state, head, at = self.state(); now = self.b.j.now()
            check(state['state'] == 'signed-recorded' and now < state['validUntilExclusiveMs'], 'submission-not-fresh')
            preflight_check(proof, self.private, state)
            value = dict(format=VERSION, handoffSha256=self.identity, wireSha256=self.private['wireSha256'],
                signature=self.private['intent']['signature'], endpoint=ENDPOINT, atMs=now,
                admissionHeadSha256=head, preflight=deepcopy(proof))
            check(len(encoded(value)) <= 16384, 'submission-boundary-size')
            self.db.execute('CREATE TABLE admission_submission (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')
            self.db.execute('INSERT INTO admission_submission VALUES(1,?)', (encoded(value),))
        return value

    def acknowledge(self, item):
        with self.b.j.transaction():
            boundary = self.boundary(); check(boundary is not None, 'submission-boundary-required')
            check(self.row('admission_submission_ack', 1024) is None, 'submission-ack-already-recorded')
            state = 'transport-unknown'
            if item.get('state') == 'received':
                state = 'rpc-acknowledged' if item.get('result') == boundary['signature'] else 'quarantined'
            value = dict(state=state, boundarySha256=digest(boundary), atMs=self.b.j.now())
            check(value['atMs'] >= boundary['atMs'], 'submission-clock-regressed')
            self.db.execute('CREATE TABLE admission_submission_ack (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')
            self.db.execute('INSERT INTO admission_submission_ack VALUES(1,?)', (encoded(value),))

    def captures(self):
        boundary = self.boundary()
        exists = self.db.execute("SELECT type FROM sqlite_master WHERE name='admission_rpc_captures'").fetchone()
        if not exists: return []
        check(exists[0] == 'table' and boundary is not None, 'collection-boundary-required')
        rows = self.db.execute('SELECT seq, CASE WHEN length(value)<=? THEN value ELSE NULL END AS value, hash FROM admission_rpc_captures ORDER BY seq LIMIT ?', (MAX_CAPTURE_BYTES, MAX_CAPTURES+1)).fetchall()
        check(len(rows) <= MAX_CAPTURES, 'collection-cap')
        result = []; previous = ''; last = boundary['atMs']
        for seq, row in enumerate(rows, 1):
            check(row['seq'] == seq and type(row['value']) is str, 'collection-record-shape')
            value = json.loads(row['value'])
            fields(value, {'format','boundarySha256','previousSha256','startedAtMs','finishedAtMs','rpcEvidence'}, 'collection-shape')
            check(encoded(value) == row['value'] and digest(value) == row['hash'] and
                  value['previousSha256'] == previous and value['boundarySha256'] == digest(boundary) and
                  value['format'] == VERSION+'-capture', 'collection-binding')
            uint(value['startedAtMs'], self.b.j.now(), 'collection-start-clock', minimum=last)
            uint(value['finishedAtMs'], self.b.j.now(), 'collection-finish-clock', minimum=value['startedAtMs'])
            fields(value['rpcEvidence'], {'genesisBefore','signatureStatus','transaction','genesisAfter'}, 'collection-evidence-shape')
            check(all(type(x) is dict for x in value['rpcEvidence'].values()), 'collection-evidence-items')
            previous = row['hash']; last = value['finishedAtMs']; result.append(value)
        return result

    def save_capture(self, started, evidence):
        with self.b.j.transaction():
            boundary = self.boundary(); check(boundary is not None, 'collection-boundary-required')
            previous = self.captures(); check(len(previous) < MAX_CAPTURES, 'collection-cap')
            finished = self.b.j.now()
            uint(started, finished, 'collection-clock', minimum=previous[-1]['finishedAtMs'] if previous else boundary['atMs'])
            value = dict(format=VERSION+'-capture', boundarySha256=digest(boundary),
                previousSha256=digest(previous[-1]) if previous else '', startedAtMs=started,
                finishedAtMs=finished, rpcEvidence=deepcopy(evidence))
            check(len(encoded(value).encode()) <= MAX_CAPTURE_BYTES, 'collection-size-cap')
            self.db.execute('CREATE TABLE IF NOT EXISTS admission_rpc_captures (seq INTEGER PRIMARY KEY, value TEXT NOT NULL, hash TEXT NOT NULL)')
            self.db.execute('INSERT INTO admission_rpc_captures VALUES(?,?,?)', (len(previous)+1, encoded(value), digest(value)))

    def replay(self):
        """Repair capture→receipt interruption without any network or send call."""
        boundary = self.boundary()
        minimum = 0 if boundary is None else context(boundary['preflight']['blockhash'])[0]
        gate = receipts.ReceiptGate(self.b)
        status = gate.status()  # Validate the bounded inbox before using its hashes.
        if status['state'] == 'quarantined': return 'quarantined'
        seen = set()
        if status['receiptEventCount']:
            seen = {json.loads(r[0])['packageSha256'] for r in
                    self.db.execute('SELECT value FROM admission_receipt_events ORDER BY seq LIMIT ?', (receipts.MAX_EVENTS,))}
        for capture in self.captures():
            state, package = normalized_package(capture, self.private, minimum)
            if state == 'quarantined': return 'quarantined'
            if package is not None and digest(package) not in seen:
                r = gate.observe(package)
                seen.add(digest(package))
                if r['state'] == 'quarantined': return 'quarantined'
        return None

    def status(self, rpc=None):
        boundary = self.boundary()
        ack = self.row('admission_submission_ack', 1024)
        if ack is not None:
            fields(ack, {'state','boundarySha256','atMs'}, 'submission-ack-shape')
            check(boundary is not None and ack['boundarySha256'] == digest(boundary) and
                  ack['state'] in ('rpc-acknowledged','transport-unknown','quarantined'), 'submission-ack-binding')
            uint(ack['atMs'], self.b.j.now(), 'submission-ack-clock', minimum=boundary['atMs'])
        captures = self.captures()
        minimum = 0 if boundary is None else context(boundary['preflight']['blockhash'])[0]
        gate = receipts.ReceiptGate(self.b).status()
        quarantined = (ack is not None and ack['state'] == 'quarantined') or gate['state'] == 'quarantined'
        collected_terminal = False
        for capture in captures:
            outcome, package = normalized_package(capture, self.private, minimum)
            if outcome == 'quarantined': quarantined = True
            if package is not None:
                source, _, _ = self.state()
                outcome, summary = receipts.evaluate(package, self.private, source['signedRecordedAtMs'], self.b.j.now(), self.b.policy['scope'])
                if outcome == 'quarantined': quarantined = True
                if outcome in receipts.TERMINAL.values():
                    if gate['terminalIdentity'] is not None and digest(summary) != gate['terminalIdentity']:
                        quarantined = True
                    if digest(summary) == gate['terminalIdentity']: collected_terminal = True
        state = 'not-attempted' if boundary is None else 'submission-unknown'
        if ack is not None and ack['state'] == 'rpc-acknowledged': state = 'rpc-acknowledged'
        usable = collected_terminal and gate['observedEffectsUsable'] and not quarantined
        if usable: state = gate['state']
        if quarantined: state = 'quarantined'
        calls = [] if rpc is None else rpc.calls
        return dict(format=VERSION, state=state, applicationSendBoundaryRecorded=boundary is not None,
            rpcAcknowledgedSignature=ack is not None and ack['state']=='rpc-acknowledged',
            receiptCaptureCount=len(captures), genesisBoundReceiptCollected=usable,
            receiptEffects=gate if usable else None, networkRequestsThisRun=len(calls),
            sendRequestsThisRun=sum(x['method']=='sendTransaction' for x in calls),
            automaticRetryAllowed=False, reservationReleased=False, allocationTransferred=False,
            walletWideReservationsKnown=False, executionApproved=False, nextCycleAuthorized=False,
            runtimeIntegrated=False, privateKeyAccessed=False, signaturesCreated=0,
            provenanceBasis='Application journal and fixed-endpoint RPC claims; not cryptographic finality proof')


def _open(root, wallet, pool, clock):
    book = Admission(handoff.storage(root), clock=clock)
    try:
        roles = book.policy['scope']['accounts']
        check(roles['wallet'] == wallet and roles['pool'] == pool, 'submission-source-scope')
        return book
    except BaseException:
        book.close(); raise


def submit(home, wallet, pool, *, allow_devnet_submit=False, opener=None, clock=handoff.bridge.view.now):
    """Explicit internal opt-in. No retry, resign, plan replacement or CLI."""
    check(allow_devnet_submit is True, 'explicit-devnet-submit-required')
    with handoff.bridge.view.cycles.c.source_lock(home, wallet) as root:
        b = _open(root, wallet, pool, clock)
        try:
            s = Submission(b)
            if s.boundary() is not None: return s.status()
            check(not handoff.bridge.view.cycles.c.submit.swap.stop(root), 'submission-stopped')
            state, _, _ = s.state()
            check(state['state']=='signed-recorded' and clock() < state['validUntilExclusiveMs'], 'submission-not-fresh')
            check(restricted_signer.acknowledgment(root, b) == s.private['signedTransactionBase64'], 'submission-signer-ack')
            check(receipts.ReceiptGate(b).status()['state'] == 'awaiting-receipt', 'submission-existing-receipt')
            rpc = SendRpc(opener)
            proof = {'genesisBefore':rpc.request('getGenesisHash', [])}
            check(received(proof['genesisBefore']) == GENESIS['devnet'], 'submission-wrong-cluster')
            packet = state['signingRequest']['packet']
            proof['blockhash'] = rpc.request('isBlockhashValid', [packet['policy']['blockhash'], {'commitment':'confirmed'}])
            slot, valid = context(proof['blockhash']); check(valid is True, 'submission-blockhash-unavailable')
            message = base64.b64encode(decode_wire(s.private['signedTransactionBase64'])[1]).decode()
            proof['fee'] = rpc.request('getFeeForMessage', [message, {'commitment':'confirmed','minContextSlot':slot}])
            proof['genesisAfter'] = rpc.request('getGenesisHash', [])
            minimum = preflight_check(proof, s.private, state)
            check(not handoff.bridge.view.cycles.c.submit.swap.stop(root), 'submission-stopped')
            # Committed and fsynced before the first possible transport invocation.
            boundary = s.mark(proof)
            check(not handoff.bridge.view.cycles.c.submit.swap.stop(root) and
                  boundary['atMs'] <= clock() < state['validUntilExclusiveMs'], 'submission-boundary-now-unknown')
            item = rpc.request('sendTransaction', [s.private['signedTransactionBase64'],
                dict(encoding='base64', skipPreflight=False, preflightCommitment='confirmed', maxRetries=0, minContextSlot=minimum)])
            s.acknowledge(item)
            return s.status(rpc)
        finally: b.close()


def recover(home, wallet, pool, *, opener=None, clock=handoff.bridge.view.now):
    """RPC observation only; may write capture/receipt evidence, never broadcasts."""
    with handoff.bridge.view.cycles.c.source_lock(home, wallet) as root:
        b = _open(root, wallet, pool, clock)
        try:
            s = Submission(b)
            if s.boundary() is None: return s.status()
            replay = s.replay(); status = s.status()
            if replay == 'quarantined' or status['state'] in (*receipts.TERMINAL.values(), 'quarantined'): return status
            check(len(s.captures()) < MAX_CAPTURES, 'collection-cap')
            started = clock(); rpc = ReceiptRpc(opener)
            evidence = {k:{'state':'not-requested'} for k in ('genesisBefore','signatureStatus','transaction','genesisAfter')}
            evidence['genesisBefore'] = rpc.request('getGenesisHash', [])
            if evidence['genesisBefore'].get('result') == GENESIS['devnet'] and evidence['genesisBefore'].get('state') == 'received':
                signature = s.private['intent']['signature']
                evidence['signatureStatus'] = rpc.request('getSignatureStatuses', [[signature], {'searchTransactionHistory':True}])
                evidence['transaction'] = rpc.request('getTransaction', [signature, dict(encoding='base64', commitment='finalized', maxSupportedTransactionVersion=0)])
                evidence['genesisAfter'] = rpc.request('getGenesisHash', [])
            s.save_capture(started, evidence); s.replay()
            return s.status(rpc)
        finally: b.close()
