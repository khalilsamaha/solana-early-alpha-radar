"""Public synthetic receipts; no private keys, signing or chain access."""
import copy
import json
from pathlib import Path
from audit import audit, FLAGS
ROOT = Path(__file__).resolve().parents[1]


def fixture(name='existing'):
    if name.startswith('wsol-'):
        return json.loads(Path(__file__).with_name('public-wsol-fixtures.json').read_text())[name]
    row = json.loads((ROOT / 'intent-journal/public-fixtures.json').read_text())[name]
    return {'format': 'signed-token-evidence-1', **row}


def run():
    cases = {}
    expected = {}
    for name in ('existing', 'create', 'close', 'v0', 'multisigner', 'wsol-source', 'wsol-destination', 'failed'):
        cases[name] = audit(fixture(name))
        expected[name] = 'finalized-failure-fee-only' if name == 'failed' else 'signed-token-accounting-consistent'
    for name in ('missing-transfer', 'incorrect-transfer', 'wsol-backing', 'unknown-receipt'):
        p = fixture('wsol-source' if name == 'wsol-backing' else 'existing')
        tx = p['bundle']['rpcEvidence']['transaction']['result']
        if name == 'missing-transfer': tx['meta']['innerInstructions'] = []
        if name == 'incorrect-transfer':
            from wire import b58
            tx['meta']['innerInstructions'][0]['instructions'][0]['data'] = b58(bytes([3])+(101).to_bytes(8,'little'))
        if name == 'wsol-backing': tx['meta']['postBalances'][1] += 1
        if name == 'unknown-receipt': p['bundle']['rpcEvidence']['transaction']['result'] = None
        cases[name] = audit(p)
        expected[name] = 'unknown' if name in ('missing-transfer', 'unknown-receipt') else 'mismatch'
    for name, result in cases.items():
        if result['state'] != expected[name]:
            raise ValueError('Self-check failed: ' + name + ' ' + result['state'])
    return {'format': 'token-reconciliation-self-check-1', 'mode': 'synthetic-offline',
            'casesPassed': len(cases), 'cases': cases, **FLAGS}
