"""Synthetic error-path checks; the separate recorded fixture is explicitly labelled."""
import copy
import json
from pathlib import Path

from recorded_capture import GENESIS
from review import review


def synthetic(name='existing'):
    case = json.loads((Path(__file__).resolve().parents[1] / 'intent-journal/public-fixtures.json').read_text())[name]
    b = case['bundle']
    tx = b['rpcEvidence']['transaction']['result']
    binary = copy.deepcopy(tx); binary['transaction'] = [case['signedTransactionBase64'], 'base64']
    received = lambda x: {'state': 'received', 'result': x}
    return {'format': 'recorded-chain-capture-1', 'origin': 'synthetic-fixture', 'network': 'devnet',
        'selection': 'explicit-signature', 'signature': b['intent']['signature'],
        'startedAtMs': b['capturedAtMs'], 'finishedAtMs': b['capturedAtMs'] + 1,
        'rpcRequestsAttempted': 0, 'requests': [], 'transactionsSent': 0, 'ledgerUpdated': False,
        'evidence': {'genesisBefore': received(GENESIS['devnet']), 'genesisAfter': received(GENESIS['devnet']),
            'discovery': {'state': 'not-requested'}, 'transactionJson': received(tx), 'transactionBase64': received(binary),
            'signatureStatus': b['rpcEvidence']['signatureStatus']}}


def self_check():
    cases = {name: synthetic(name) for name in ('existing', 'create', 'close', 'failed', 'v0', 'multisigner')}
    cases['wrong-cluster'] = synthetic()
    cases['wrong-cluster']['evidence']['genesisBefore']['result'] = GENESIS['mainnet-beta']
    cases['message-disagreement'] = synthetic()
    cases['message-disagreement']['evidence']['transactionJson']['result']['transaction']['message']['instructions'][0]['data'] = '3'
    cases['missing-history'] = synthetic()
    cases['missing-history']['evidence']['transactionBase64']['result'] = None
    results = {k: review(v) for k, v in cases.items()}
    expected = dict.fromkeys(('existing', 'create', 'close', 'failed', 'v0', 'multisigner'), 'signed-transaction-consistent')
    expected.update({'wrong-cluster': 'mismatch', 'message-disagreement': 'mismatch', 'missing-history': 'unknown'})
    if {k: v['state'] for k, v in results.items()} != expected: raise ValueError('Self-check mismatch')
    return {'format': 'recorded-chain-self-check-1', 'mode': 'synthetic-offline', 'cases': results,
        'casesPassed': len(results), 'rpcRequestsAttempted': 0, 'transactionsSent': 0,
        'executionApproved': False, 'ledgerUpdated': False}
