"""Synthetic receipt integration; pre-existing fixture signature, no keys or RPC."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import admission_receipt as m
import pre_sign_admission as admission
from locked_admission_checks import fixture, home_fixture, NOW
from contract import TOKEN
from wire import decode_wire, b58


def receipt(evidence, private):
    """Construct synthetic RPC claims, never an actual chain receipt."""
    roles = evidence['scope']['accounts']
    _, _, _, _, tx = decode_wire(private['signedTransactionBase64'])
    sim = evidence['costInputs']['simulation_item']['result']
    meta = {k: deepcopy(sim['value'][k]) for k in
            ('fee', 'preBalances', 'postBalances', 'preTokenBalances', 'postTokenBalances')}
    keys = tx['transaction']['message']['accountKeys']
    def transfer(source, destination, authority, amount):
        return dict(programIdIndex=keys.index(TOKEN), accounts=[keys.index(roles[k]) for k in
                    (source, destination, authority)], data=b58(bytes([3])+int(amount).to_bytes(8, 'little')))
    meta.update(err=None, innerInstructions=[dict(index=2, instructions=[
        transfer('source', 'inputVault', 'wallet', evidence['scope']['amountIn']),
        transfer('outputVault', 'destination', 'authority', evidence['costInputs']['price']['quote']['outAmount'])])])
    tx.update(meta=meta, slot=sim['context']['slot'])
    return dict(format='signed-token-evidence-1', signedTransactionBase64=private['signedTransactionBase64'],
        bundle=dict(format='intent-evidence-bundle-1', network='devnet', capturedAtMs=NOW+1000,
            intent=deepcopy(private['intent']), rpcEvidence=dict(
                signatureStatus=dict(state='received', result=dict(context=dict(slot=tx['slot']+1),
                    value=[dict(slot=tx['slot'], err=None, confirmationStatus='finalized')])),
                transaction=dict(state='received', result=tx))))


def failed(package):
    package = deepcopy(package)
    meta = package['bundle']['rpcEvidence']['transaction']['result']['meta']
    error = {'InstructionError': [2, 'InvalidArgument']}
    meta.update(err=error, postTokenBalances=deepcopy(meta['preTokenBalances']),
                postBalances=meta['preBalances'].copy(), innerInstructions=[])
    meta['postBalances'][0] -= meta['fee']
    package['bundle']['rpcEvidence']['signatureStatus']['result']['value'][0]['err'] = error
    return package


def unknown(package):
    package = deepcopy(package)
    package['bundle']['rpcEvidence']['transaction']['result'] = None
    return package


def other_vault(package, scope):
    package = deepcopy(package)
    tx = package['bundle']['rpcEvidence']['transaction']['result']
    roles = scope['accounts']; keys = tx['transaction']['message']['accountKeys']
    old = keys.index(roles['inputVault']); other = keys.index(roles['config'])
    for field in ('preTokenBalances', 'postTokenBalances'):
        row = deepcopy(next(r for r in tx['meta'][field] if r['accountIndex'] == old))
        row['accountIndex'] = other; tx['meta'][field].append(row)
    tx['meta']['innerInstructions'][0]['instructions'][0]['accounts'][1] = other
    return package


def run():
    e, p, signed = fixture(); cases = {}; now = [NOW+200]
    wallet = p['scope']['accounts']['wallet']; pool = p['scope']['accounts']['pool']
    snapshot = deepcopy(e['costInputs']['reservations'])
    snapshot.update(readStartedAtMs=now[0], observedAtMs=now[0])
    with tempfile.TemporaryDirectory() as tmp, patch.object(admission, 'BASELINE', e['costInputs']['baseline']), patch.object(m.handoff.bridge.view, 'read_locked', return_value=snapshot):
        def setup(name):
            now[0] = NOW+200
            home = home_fixture(Path(tmp)/name, wallet)
            m.handoff.dispatch(home, wallet, pool, e, p,
                signer_adapter=lambda _: signed['signedTransactionBase64'], clock=lambda: now[0])
            b = admission.Admission(m.handoff.storage(home), clock=lambda: now[0])
            try:
                package = receipt(e, b.private_accounting_handoff())
            finally:
                b.close()
            now[0] = NOW+1100
            return home, package
        def observe(h, package=None):
            return m.observe(h, wallet, pool, package, clock=lambda: now[0])
        h, package = setup('success')
        before = m.handoff.recover(h, wallet, pool, clock=lambda: now[0])['admission']
        assert observe(h)['state'] == 'awaiting-receipt'; cases['empty-read-does-not-infer-submission'] = 'passed'
        r = observe(h, unknown(package)); assert r['state'] == 'receipt-unknown'
        cases['missing-receipt-retains-unknown'] = 'passed'
        r = observe(h, package); assert r['state'] == 'entry-effects-observed' and int(r['observedAcquiredAtomic']) > 0
        cases['exact-raw-receipt-bound-to-handoff'] = 'passed'
        assert observe(h, package) == r and observe(h, unknown(package)) == r
        cases['duplicate-and-late-unknown-do-not-reapply'] = 'passed'
        assert r['reservedPrincipalAtomic'] == '100' and r['reservedFeeLamports'] == '26000'
        assert m.handoff.recover(h, wallet, pool, clock=lambda: now[0])['admission'] == before
        cases['original-allocation-held-in-same-ledger'] = 'passed'
        now[0] += 30000
        assert observe(h) == r; cases['expired-evidence-replays-without-resigning'] = 'passed'
        (h/'STOP').touch(mode=0o600)
        m.handoff.recover(h, wallet, pool, clock=lambda: now[0])
        assert observe(h) == r; cases['stop-does-not-hide-existing-effects'] = 'passed'
        assert signed['signedTransactionBase64'] not in json.dumps(r) and 'rpcEvidence' not in json.dumps(r)
        cases['private-wire-and-raw-receipt-not-exported'] = 'passed'
        assert observe(h, failed(package))['state'] == 'quarantined'
        assert observe(h, package)['state'] == 'quarantined'
        cases['conflicting-terminal-evidence-stays-quarantined'] = 'passed'
        h, package = setup('failure')
        r = observe(h, failed(package))
        assert r['state'] == 'entry-failure-observed' and r['observedAcquiredAtomic'] == '0'
        assert int(r['observedEntryFeeLamports']) > 0 and r['reservedFeeLamports'] == '26000'
        cases['failed-entry-records-fee-without-fill-or-release'] = 'passed'
        h, package = setup('wrong-intent')
        package['bundle']['intent']['inputAtomic'] = '101'
        r = observe(h, package); assert r['state'] == 'quarantined' and not r['observedEffectsUsable']
        cases['changed-intent-cannot-advance-accounting'] = 'passed'
        h, package = setup('summary')
        package['bundle']['rpcEvidence'] = {'state': 'passed'}
        assert observe(h, package)['state'] == 'receipt-unknown'
        cases['summary-does-not-replace-raw-evidence'] = 'passed'
        h, package = setup('vault')
        changed = other_vault(package, p['scope'])
        assert m.audit(changed)['state'] == 'signed-token-accounting-consistent'
        assert observe(h, changed)['state'] == 'quarantined'
        cases['compatible-token-counterparty-must-be-exact-admitted-vault'] = 'passed'
        h = home_fixture(Path(tmp)/'missing', wallet)
        try:
            observe(h)
        except (ValueError, OSError):
            pass
        else:
            raise AssertionError('missing allocation created')
        assert not (h.parent/(h.name+'-entry-handoff-v1')).exists()
        cases['missing-ledger-never-creates-an-allocation'] = 'passed'
    return dict(format=m.VERSION+'-self-check', state='offline-checks-passed', mode='synthetic-offline',
        casesPassed=len(cases), cases=cases, temporaryLedgersRemoved=True,
        networkRequests=0, signaturesCreated=0, transactionsSent=0, privateKeyAccessed=False,
        productionLedgerUpdated=False, executionApproved=False, liveSenderIntegrated=False,
        reservationReleased=False, allocationTransferred=False, rpcProvenanceVerified=False,
        submissionProvenanceVerified=False, walletWideReservationsKnown=False)
