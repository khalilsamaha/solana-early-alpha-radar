"""Offline full-source successor snapshot and isolated restore rehearsal."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

import admission_recovery as recovery
import successor_completion_checks as completion
from core import check
from contract import digest
from pre_sign_admission import encoded

VERSION = 'successor-recovery-rehearsal-1'
CONNECTED_CASES = completion.CONNECTED_CASES + 5


def tree_bytes(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


@contextmanager
def originals_unavailable(c):
    """Temporarily rename only the two owned disposable source directories."""
    moved = []
    try:
        for path in (c.f.home, c.path.parent):
            target = path.with_name(path.name + '-recovery-unavailable')
            check(not target.exists(), 'recovery-fixture-destination')
            path.rename(target); moved.append((path, target))
        yield
    finally:
        for path, target in reversed(moved): target.rename(path)


def restored(c, destination, expected_state, expected_accounting=None):
    f = c.f
    original = (tree_bytes(f.home), tree_bytes(c.path.parent))
    completion.execution.fixture.require_cold_reuse_scopes()
    captured = recovery.capture(f.home, f.wallet, f.pool, destination, clock=c.clock)
    check(original == (tree_bytes(f.home), tree_bytes(c.path.parent)), 'recovery-source-mutated')
    sealed = tree_bytes(destination)
    with originals_unavailable(c):
        verified = recovery.verify(destination, f.wallet, f.pool, clock=c.clock)
    completion.execution.fixture.require_cold_reuse_scopes()
    check(captured['manifestSha256'] == verified['manifestSha256'] and
        verified['state'] == 'isolated-admission-restore-verified', 'recovery-isolated-restore')
    check(sealed == tree_bytes(destination) and original == (tree_bytes(f.home), tree_bytes(c.path.parent)),
        'recovery-restore-mutated-evidence')
    manifest = json.loads((destination/recovery.MANIFEST).read_text())
    projected = manifest['projection']['exitRetirement']
    check(projected['state'] == expected_state and not projected['scopedAccounting']['scopedClosureRecorded'],
        'recovery-held-state')
    check(projected['successorBackendAcknowledgmentPresent'] and projected['successorBackendAttemptPresent'],
        'recovery-successor-markers')
    if expected_accounting is not None:
        check(projected['successorAccountingSha256'] == expected_accounting['recordSha256'] and
            projected['scopedAccounting'] == c.report['accountedHold'], 'recovery-accounting-binding')
    else:
        check('successorAccountingSha256' not in projected and
            projected['successorTransportState'] == 'successor-submission-unknown', 'recovery-unknown-state')
    check(not list(destination.rglob('*.pk8')) and not list(destination.glob('.admission-restore-check-*')),
        'recovery-private-key-or-temporary-copy')
    for result in (captured, verified):
        check(result['restoredCopyStopped'] and result['temporaryRestoreRemoved'] and not result['signingKeyIncluded'] and
            not any(result[k] for k in ('privateKeyAccessed', 'networkRequests', 'signaturesCreated', 'transactionsSent',
                'reservationReleased', 'sourceStateChanged', 'allocationTransferred', 'executionApproved',
                'nextCycleAuthorized')), 'recovery-unexpected-authority')
    # Public summaries only. The private manifest, signatures and source paths
    # remain inside the disposable fixture and never enter the output report.
    return dict(state=verified['state'], manifestSha256=verified['manifestSha256'], files=verified['files'],
        bytes=verified['bytes'], sqliteDatabasesChecked=verified['sqliteDatabasesChecked'],
        successorState=projected['state'], successorTransportState=projected['successorTransportState'],
        originalDirectoriesUnavailableDuringVerify=True, originalEvidenceUnchanged=True,
        restoredCopyStopped=True, privateKeysIncluded=False, scopedClosureRecorded=False)


def reseal_inventory(snapshot):
    path = snapshot/recovery.MANIFEST
    manifest = json.loads(path.read_text())
    manifest['inventories'] = recovery.inventories(snapshot/recovery.SOURCE, snapshot/recovery.SIBLING)
    path.write_text(json.dumps(manifest))


def rejects(c, snapshot, reason):
    before = tree_bytes(snapshot)
    try: recovery.verify(snapshot, c.f.wallet, c.f.pool, clock=c.clock)
    except ValueError as exc: check(str(exc) == reason, 'recovery-wrong-rejection')
    else: raise AssertionError('altered snapshot accepted')
    check(before == tree_bytes(snapshot) and not list(snapshot.glob('.admission-restore-check-*')),
        'recovery-rejection-mutated-evidence')


def connected(c):
    report = c.report; phase = completion.execution.fixture.phase
    with tempfile.TemporaryDirectory(prefix='successor-snapshots-', dir=c.f.home.parent) as owned:
        root = Path(owned); original_recover = completion.execution.m._recover; seen = []
        def observe_unknown(*args, **kwargs):
            if not seen:
                seen.append(True)
                with phase(report, 'unknown-successor-private-snapshot-isolated-restore'):
                    check(not c.key.exists() and (c.f.home/'STOP').exists(), 'recovery-keyless-stop')
                    report['unknownSnapshot'] = restored(c, root/'unknown', 'exit-retired-held')
                report['cases']['unknown-send-survives-full-snapshot-without-originals'] = 'passed'
            return original_recover(*args, **kwargs)
        with patch.object(completion.execution.m, '_recover', side_effect=observe_unknown):
            completion.connected(c)
        check(len(seen) == 1, 'recovery-unknown-check-required')
        snapshot = root/'accounted'
        with phase(report, 'accounted-successor-private-snapshot-isolated-restore'):
            report['accountedSnapshot'] = restored(c, snapshot, 'successor-accounted-flat-held', report['successorAccounting'])
        report['cases']['accounted-successor-and-retired-hold-survive-full-isolated-restore'] = 'passed'
        with phase(report, 'snapshot-key-exclusion-stop-and-preservation'):
            check(report['unknownSnapshot']['restoredCopyStopped'] and report['accountedSnapshot']['restoredCopyStopped'],
                'recovery-stopped-copy')
        report['cases']['both-restored-copies-stopped-keyless-and-originals-unchanged'] = 'passed'
        database = snapshot/recovery.SIBLING/'entry.admission.sqlite'
        original_db = database.read_bytes(); manifest = snapshot/recovery.MANIFEST; original_manifest = manifest.read_bytes()
        with phase(report, 'rehashed-successor-accounting-snapshot-rejected'):
            db = sqlite3.connect(database, isolation_level=None)
            try:
                row = json.loads(db.execute('SELECT value FROM admission_successor_accounting').fetchone()[0])
                row['effects']['retiredFeeExposureHeldLamports'] = '0'
                db.execute('UPDATE admission_successor_accounting SET value=?,hash=?', (encoded(row), digest(row)))
            finally: db.close()
            reseal_inventory(snapshot); rejects(c, snapshot, 'successor-accounting-source-conflict')
            database.write_bytes(original_db); manifest.write_bytes(original_manifest)
        report['cases']['rehashed-snapshot-cannot-erase-retired-fee-exposure'] = 'passed'
        with phase(report, 'rehashed-successor-marker-snapshot-rejected'):
            path = snapshot/recovery.SIBLING/'successor-signer-attempt.json'
            row = json.loads(path.read_text()); row['successorSha256'] = '0'*64; path.write_text(json.dumps(row))
            reseal_inventory(snapshot); rejects(c, snapshot, 'successor-signer-attempt-binding')
        report['cases']['rehashed-snapshot-cannot-substitute-successor-marker'] = 'passed'
    check(not Path(owned).exists(), 'recovery-snapshot-cleanup')
    report['privateSnapshotFixturesRemoved'] = True


def run():
    report = completion.execution.fixture.run(_exercise=connected)
    report.update(format=VERSION, casesExpected=CONNECTED_CASES, executionApproved=False,
        scopedClosureRecorded=False, retiredExposureReleased=False,
        limitations=['Disposable full-source snapshots only; no operational backup or active restore.',
            'Synthetic RPC and disposable keys; real network, provider finality and execution are not tested.',
            'Restored copies are stopped. Unknown sends and retired exposure remain held.',
            'Snapshot replay is historical evidence, not current balances, closure or new-entry authority.',
            'Checksums do not authenticate a malicious replacement of the entire evidence history.'])
    if report['casesPassed'] != CONNECTED_CASES or not report.get('privateSnapshotFixturesRemoved') or not report['temporaryLedgersRemoved']:
        report['state'] = 'review-required'
    return report
