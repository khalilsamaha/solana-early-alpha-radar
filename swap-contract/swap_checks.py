"""Deterministic host check, no wallet, database, network, or signatures."""
from contract import validate
from swap_fixtures import NOW, fixture, edit_wire


def cases():
    entries = {'legacy-match': (fixture(), 'instruction-policy-match'),
               'v0-no-lookups-match': (fixture(0), 'instruction-policy-match')}
    p = fixture(); p['policy']['amountIn'] = '101'
    entries['changed-input'] = (p, 'input-amount-mismatch')
    p = fixture(); p['policy']['minimumAmountOut'] = '191'
    entries['changed-minimum-output'] = (p, 'minimum-output-mismatch')
    p = fixture(); p['policy']['maxPriorityFeeLamports'] = '0'
    entries['priority-cap'] = (p, 'priority-fee-exceeded')
    p = fixture(); p['feeAssertion']['lamports'] = '6001'
    entries['total-fee-cap'] = (p, 'total-fee-outside-bounds')
    p = fixture(); p['policy']['expiresAtMs'] = NOW
    entries['expired-policy'] = (p, 'policy-expired-or-future')
    p = fixture(); p['feeAssertion']['messageSha256'] = '0' * 64
    entries['wrong-fee-message'] = (p, 'fee-message-mismatch')
    p = edit_wire(fixture(), lambda m: m['instructions'].append(m['instructions'][2].copy()))
    entries['extra-instruction'] = (p, 'instruction-count')
    p = edit_wire(fixture(), lambda m: m['instructions'][2]['accounts'].reverse())
    entries['wrong-account-order'] = (p, 'swap-account-role-mismatch')
    p = edit_wire(fixture(), lambda m: None, signatures=[b'\x01' * 64])
    entries['already-signed-message'] = (p, 'requires-one-unsigned-signature')
    p = edit_wire(fixture(), lambda m: m['header'].update(numReadonlyUnsignedAccounts=1))
    entries['escalated-write-permissions'] = (p, 'writable-privilege-mismatch')
    return entries


def run():
    results = {}
    for name, (packet, expected) in cases().items():
        result = validate(packet, now_ms=NOW)
        if result.get('reason', result['state']) != expected:
            raise ValueError('Self-check mismatch: ' + name)
        results[name] = result
    return {'format': 'swap-contract-self-check-1', 'mode': 'synthetic-offline',
            'casesPassed': len(results), 'cases': results, 'networkRequests': 0,
            'transactionsSent': 0, 'signaturesCreated': 0, 'ledgerUpdated': False,
            'signingApproved': False, 'executionApproved': False}
