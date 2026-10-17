"""Public synthetic fixtures only; creates and removes a temporary private journal."""
import copy
import json
from pathlib import Path
import tempfile

from journal import Journal, FLAGS
from wire import verify_wire


def fixture(name='existing', intent_id=None):
    case = json.loads(Path(__file__).with_name('public-fixtures.json').read_text())[name]
    package = {'format': 'signed-intent-registration-1', 'logicalIntentId': intent_id or name,
               'intent': copy.deepcopy(case['bundle']['intent']), 'signedTransactionBase64': case['signedTransactionBase64']}
    return package, case['bundle']


def unknown(bundle):
    b = copy.deepcopy(bundle)
    b['rpcEvidence']['signatureStatus']['result']['value'] = [None]
    b['rpcEvidence']['transaction']['result'] = None
    return b


def run():
    cases = {}
    with tempfile.TemporaryDirectory(prefix='radar-intent-selfcheck-') as directory:
        path = Path(directory) / 'journal.sqlite'
        clock = lambda: 1792240010000
        j = Journal(path, clock)
        try:
            for name in ('existing', 'create', 'close', 'failed', 'v0', 'multisigner'):
                p, b = fixture(name)
                j.register(p)
                j.mark_submission_boundary(name)
                # Close/reopen the actual SQLite connection; this is not an in-memory replay.
                j.close(); j = Journal(path, clock)
                cases[name] = j.observe(name, b)
            cases['idempotent-registration'] = j.register(fixture()[0])
            try:
                j.mark_submission_boundary('existing')
                raise AssertionError('Duplicate submission boundary accepted')
            except ValueError:
                cases['duplicate-boundary'] = {'state': 'rejected', **FLAGS}
            altered = fixture()[0]['signedTransactionBase64']
            import base64
            raw = bytearray(base64.b64decode(altered)); raw[-1] ^= 1
            try:
                verify_wire(base64.b64encode(raw).decode())
                raise AssertionError('Tampered wire accepted')
            except ValueError:
                cases['tampered-wire'] = {'state': 'rejected', **FLAGS}
        finally:
            j.close()
        # Independent journals allow one public signed fixture to exercise recovery and quarantine.
        for name in ('unknown-recovery', 'unexpected-debit'):
            j = Journal(Path(directory) / (name + '.sqlite'), clock)
            try:
                p, b = fixture()
                j.register(p); j.mark_submission_boundary('existing')
                if name == 'unknown-recovery':
                    before = j.observe('existing', unknown(b))
                    j.close(); j = Journal(Path(directory) / (name + '.sqlite'), clock)
                    reopened = j.result('existing')
                    assert before['state'] == reopened['state'] == 'submission-unknown'
                    cases[name] = {'stateBefore': before['state'], 'stateAfterRestart': reopened['state'], **j.observe('existing', b)}
                else:
                    b['rpcEvidence']['transaction']['result']['meta']['postBalances'][0] -= 1
                    cases[name] = j.observe('existing', b)
            finally:
                j.close()
    expected = {k: 'reconciled' for k in ('existing', 'create', 'close', 'v0', 'multisigner', 'idempotent-registration', 'unknown-recovery')}
    expected.update(failed='failed-fee-only', **{'duplicate-boundary': 'rejected', 'tampered-wire': 'rejected', 'unexpected-debit': 'quarantined'})
    if {k: v['state'] for k, v in cases.items()} != expected:
        raise ValueError('Self-check state mismatch')
    return {'format': 'signed-intent-self-check-1', 'mode': 'synthetic-offline', 'cases': cases,
            'casesPassed': len(cases), 'temporaryJournalRemoved': True, 'syntheticClock': True, **FLAGS,
            'limitations': ['Public fixtures have valid signatures but hypothetical RPC balances and finality.',
                'No recorded chain or devnet execution was performed.',
                'Signatures do not verify RPC balances, network identity, intent registration time or program semantics.',
                'No production journal, scanner, observer, protocol, model or backup was changed.']}
