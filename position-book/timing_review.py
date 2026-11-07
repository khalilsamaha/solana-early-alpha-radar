"""Offline continuation report comparison. Diagnostic evidence, never authorization."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

VERSION = 'continuation-timing-review-1'
MAX_BYTES = 2 * 1024 * 1024
PHASES = ('continuation-collection-persistence', 'continuation-signing-handoff',
          'continuation-submission')
FALSE_FLAGS = ('productionWalletAccessed', 'productionLedgerUpdated',
               'runtimeIntegrated', 'executionApproved', 'automaticRetryAllowed')

EXPECTED_CASES = frozenset((
    'stop-preserves-one-attempt-boundaries',
    'wrong-original-preserves-one-attempt-boundaries',
    'wrong-current-preserves-one-attempt-boundaries',
    'marker-preserves-one-attempt-boundaries',
    'write-failure-preserves-one-attempt-boundaries',
    'budget-preserves-one-attempt-boundaries',
    'lost-signer-preserves-one-attempt-boundaries',
    'deadline-preserves-one-attempt-boundaries',
    'stop-after-write-preserves-one-attempt-boundaries',
    'persisted-expiry-preserves-one-attempt-boundaries',
    'three-exact-opt-ins-and-no-ordinary-wrapper-bypass',
    'actual-isolated-signer-and-one-lost-response-send',
    'independent-signer-rejects-rehashed-lineage-and-ownership-changes',
    'both-predecessors-source-and-entry-accounting-preserved',
    'repeat-refused-before-collection-keyless-stopped-recovery-never-resends',
    'repeated-recovery-keeps-durable-evidence-byte-identical',
))
EXPECTED_CONTRACTS = frozenset((
    'attempt-budget-reset',
    'continuation-removed',
    'extra-envelope-field',
    'fee-cap-increased',
    'fee-hold-reduced',
    'original-blockhash-reused',
    'original-lineage-rehashed',
    'previous-blockhash-reused',
    'previous-generation-corrupted-and-rehashed',
    'previous-generation-removed',
    'previous-lineage-rehashed',
    'protected-inventory-reduced',
    'third-generation-expired',
    'valid-continuation-replays-all-three-generations',
))


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate-json-key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('non-finite-json')


def read(path):
    """Bound decompressed input; export its digest, never arbitrary report text."""
    with gzip.open(path, 'rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('input-byte-limit')
    data = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    return summarize(data, hashlib.sha256(raw).hexdigest())


def summarize(data, digest=None):
    if type(data) is not dict or data.get('format') != 'continuation-exit-integration-1':
        raise ValueError('unsupported-report')
    if data.get('mode') != 'synthetic-offline':
        raise ValueError('not-offline-report')
    if any(data.get(k) is not False for k in FALSE_FLAGS):
        raise ValueError('offline-boundary-unconfirmed')
    if any(type(data.get(k)) is not int or data[k] != 0
           for k in ('realNetworkRequests', 'transactionsSent')):
        raise ValueError('offline-boundary-unconfirmed')
    state = data.get('state')
    if state not in ('offline-integration-passed', 'review-required'):
        raise ValueError('unsupported-state')
    rows = data.get('diagnosticPhases')
    if type(rows) is not list or len(rows) > 32:
        raise ValueError('invalid-phase-list')
    phases = {}
    for row in rows:
        if type(row) is not dict or type(row.get('phase')) is not str:
            raise ValueError('invalid-phase')
        name = row['phase']
        if name in phases:
            raise ValueError('duplicate-phase')
        elapsed = row.get('elapsedMs')
        if type(row.get('completed')) is not bool or (elapsed is not None and
                (not number(elapsed) or elapsed < 0)):
            raise ValueError('invalid-phase-timing')
        phases[name] = {'completed': row['completed'], 'elapsedMs': elapsed}
    elapsed = data.get('integrationElapsedMs')
    headroom = data.get('deadlineHeadroomMs')
    if elapsed is not None and (not number(elapsed) or elapsed < 0):
        raise ValueError('invalid-total-timing')
    if headroom is not None and not number(headroom):
        raise ValueError('invalid-headroom')
    requested, actual = data.get('requestedProgramFixtureBytes'), data.get('programFixtureBytes')
    fixture_valid = (type(requested) is int and type(actual) is int and
                     0 < requested == actual <= 16 * 1024 * 1024)
    cases, contracts = data.get('cases'), data.get('independentContractCases')
    cases_valid = (type(cases) is dict and set(cases) == EXPECTED_CASES and
                   all(v == 'passed' for v in cases.values()) and
                   type(data.get('casesPassed')) is int and data['casesPassed'] == len(EXPECTED_CASES))
    contracts_valid = (type(contracts) is dict and set(contracts) == EXPECTED_CONTRACTS and
                       all(v == 'passed' for v in contracts.values()))
    reasons = []
    if state != 'offline-integration-passed': reasons.append('source-run-requires-review')
    if not fixture_valid: reasons.append('fixture-not-confirmed')
    if not cases_valid: reasons.append('integration-cases-incomplete')
    if not contracts_valid: reasons.append('signer-contract-cases-incomplete')
    if data.get('temporaryLedgersRemoved') is not True: reasons.append('cleanup-unconfirmed')
    if data.get('continuationStarted') is not True: reasons.append('continuation-not-confirmed')
    if data.get('diagnosticsVersion') != 'continuation-rehearsal-diagnostics-1':
        reasons.append('unsupported-clock-definition')
    required = PHASES + ('continuation-sign-send',)
    if any(k not in phases or not phases[k]['completed'] or phases[k]['elapsedMs'] is None for k in required):
        reasons.append('timing-phases-incomplete')
    if elapsed is None or headroom is None: reasons.append('timing-evidence-incomplete')
    elif headroom <= 0: reasons.append('no-positive-recorded-headroom')
    if elapsed is not None and all(k in phases and phases[k]['elapsedMs'] is not None for k in PHASES):
        if sum(phases[k]['elapsedMs'] for k in PHASES) > elapsed + 1:
            reasons.append('phase-times-exceed-parent')
        nested = phases.get('synthetic-sender-adapter-setup', {}).get('elapsedMs')
        if nested is not None and nested > phases['continuation-submission']['elapsedMs'] + 1:
            reasons.append('nested-setup-exceeds-submission')
    selected = {k: phases.get(k) for k in required + ('synthetic-sender-adapter-setup',)}
    return dict(sourceDigest=digest, sourceState=state,
                functionalEvidence='complete-offline-pass' if not reasons else 'review-required',
                reviewReasons=reasons, fixtureBytes=actual if fixture_valid else None,
                integrationElapsedMs=elapsed, deadlineHeadroomMs=headroom, phases=selected,
                clockDefinition=data.get('diagnosticsVersion') if
                    data.get('diagnosticsVersion') == 'continuation-rehearsal-diagnostics-1' else None)


def compare(before, after, same_host=False):
    reasons = []
    if not same_host: reasons.append('same-host-and-comparable-load-not-attested')
    if before['fixtureBytes'] is None or before['fixtureBytes'] != after['fixtureBytes']:
        reasons.append('fixture-mismatch-or-unknown')
    if before['clockDefinition'] is None or before['clockDefinition'] != after['clockDefinition']:
        reasons.append('clock-definition-mismatch-or-unknown')
    if any(r['functionalEvidence'] != 'complete-offline-pass' for r in (before, after)):
        reasons.append('one-or-both-runs-incomplete')
    deltas = None
    if not reasons:
        deltas = {key: round(after[key] - before[key], 3)
                  for key in ('integrationElapsedMs', 'deadlineHeadroomMs')}
        deltas['phasesMs'] = {key: round(after['phases'][key]['elapsedMs'] -
                                       before['phases'][key]['elapsedMs'], 3) for key in PHASES}
    return dict(format=VERSION, before=before, after=after,
                comparison='descriptive-pair' if not reasons else 'not-comparable',
                comparisonReasons=reasons, sameHostAndLoadUserAttested=same_host,
                afterMinusBefore=deltas, executionApproved=False,
                limitations=[
                    'Source report claims are not independently replayed or authenticated.',
                    'Same-host/load attestation is user supplied, not hardware measurement.',
                    'A single pair does not establish a speedup or reliable network timing.',
                    'Sender setup is nested in submission; never add it again or subtract it.',
                    'Parent phases overlap their children; phase times are not a flat total.',
                    'Positive synthetic headroom is not a live execution readiness threshold.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--same-host-and-load', action='store_true',
                        help='Attest both runs used the same host under comparable load.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = compare(read(args.before), read(args.after), args.same_host_and_load)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launch-study'))
    from report import publish
    publish(args.output, result)
    print('Comparison:', result['comparison'])
    print('Reasons:', ', '.join(result['comparisonReasons']) or 'none')
    print('After minus before:', json.dumps(result['afterMinusBefore']))
    print('Offline diagnostic only; no execution approval. Report:', args.output.absolute())


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Timing review stopped (' + type(exc).__name__ + '). No complete report published.')
