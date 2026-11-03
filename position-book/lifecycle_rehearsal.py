"""Offline connected lifecycle profile. Synthetic providers and disposable keys only.

No operational parameters or user-journal reader. Timings are diagnostic and never
extend evidence deadlines or authorize a send. Individual stages are inclusive.
"""
from contextlib import contextmanager
from copy import deepcopy
import math
from pathlib import Path
import platform
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

import fresh_entry
import fresh_exit
import settled_exit
import exit_settlement
from core import check

VERSION = 'lifecycle-rehearsal-1'
DIAGNOSTICS = {'rehearsal-clock', 'rehearsal-stage', 'rehearsal-unknown-send',
    'rehearsal-one-send', 'rehearsal-original-expiry', 'rehearsal-request-count',
    'rehearsal-entry-evidence', 'rehearsal-entry-settlement', 'rehearsal-entry-accounting',
    'rehearsal-ambiguous-closure', 'rehearsal-source-mutated', 'rehearsal-read-only-recovery',
    'rehearsal-repeat-recovery', 'rehearsal-recovery-mutated', 'rehearsal-recovery-identity',
    'rehearsal-scoped-accounting', 'rehearsal-fee-conservation', 'rehearsal-no-allocation',
    'rehearsal-exact-send-count', 'rehearsal-historical-source', 'rehearsal-temporary-scope'}
STAGES = ('fixture-setup', 'entry-collection-sign-send', 'entry-receipt-accounting',
          'exit-collection-sign-send', 'exit-receipt-accounting-closure',
          'read-only-closure-recovery', 'repeated-closure-recovery')


class Measurements:
    """Sanitized timings; no callbacks or measured results are exported."""
    def __init__(self, monotonic=time.monotonic):
        self.monotonic = monotonic
        self.rows = []
        self.last_tick = None
        self.current_stage = None

    @contextmanager
    def stage(self, name):
        check(name in STAGES, 'rehearsal-stage')
        self.current_stage = name
        start = self.monotonic()
        check(type(start) in (int, float) and math.isfinite(start) and
              (self.last_tick is None or start >= self.last_tick), 'rehearsal-clock')
        complete = False
        try:
            yield
            complete = True
        finally:
            end = self.monotonic()
            valid = type(end) in (int, float) and math.isfinite(end) and end >= start
            self.rows.append(dict(stage=name, elapsedMs=round((end-start)*1000, 3) if valid else None,
                                  completed=complete and valid))
            check(valid, 'rehearsal-clock')
            self.last_tick = end


def base():
    return dict(format=VERSION, state='review-required', mode='synthetic-offline',
        casesPassed=0, cases={}, timings=[], diagnosticCode=None, failedStage=None,
        realNetworkRequests=0, transactionsSent=0, productionWalletAccessed=False,
        disposableTestKeySigning=True, productionLedgerUpdated=False,
        temporaryLedgersRemoved=False, originalSourceUnchanged=False,
        entry=None, exit=None, recovery=None, measuredProviderLatency=False,
        measuredFinalityLatency=False, timingApproval=False, executionApproved=False,
        fundsAvailableForNewEntry=False, nextCycleAuthorized=False, runtimeIntegrated=False,
        pythonVersion=platform.python_version(),
        limitations=[
            'One offline sample with real local collectors, verification, journals and isolated test-key signers.',
            'Synthetic provider replies and synthetic finalized receipts; elapsed times exclude real network and finality delays.',
            'Historical fixture setup generates disposable keys and signatures separately from the two measured transaction legs.',
            'Each measured stage is inclusive; do not add nested component timings or infer a latency distribution.',
            'The original entry and exit expiry guards remain unchanged; this profile never refreshes their deadlines.',
            'A successful scoped close is historical accounting, not wallet-wide buying power or pilot approval.'])


def leg(result):
    """Small allowlisted projection, no key, signature, wire or raw evidence."""
    state = result.get('state')
    check(state in ('submission-unknown', 'exit-submission-unknown'), 'rehearsal-unknown-send')
    check(result.get('signerAcknowledgmentValidated') is True and result.get('sendRequestsThisRun') == 1,
          'rehearsal-one-send')
    check(result.get('completedWithinOriginalDeadline') is True, 'rehearsal-original-expiry')
    check(result.get('networkRequests') == 25, 'rehearsal-request-count')
    return dict(state=state, syntheticRequestAttempts=25, syntheticSendAttempts=1,
                recordedSignatures=1, completedWithinOriginalDeadline=True)


def exit_inputs(e, accounting, stamp):
    # Reuse the raw-account fixture generator used by the independent exit tests.
    from test_admission_exit_recovery import delayed
    evidence = delayed(e['costInputs']['capture'], accounting, stamp)
    raw = evidence['initialPool']; first = deepcopy(evidence['capture'])
    first.update(packet=None, selection='explicit-pool', accountKeys=raw['accountKeys']+[first['accountKeys'][-1]])
    programdata = deepcopy(first['evidence']['accounts']['result']['value'][-1])
    first['evidence']['accounts'] = deepcopy(raw['evidence']['accounts'])
    first['evidence']['accounts']['result']['value'].append(programdata)
    first['evidence']['poolBootstrap'] = deepcopy(raw['evidence']['bootstrap'])
    first['evidence']['programBootstrap']['result']['context']['slot'] = first['evidence']['poolBootstrap']['result']['context']['slot']
    for name in ('genesisBefore', 'genesisAfter', 'blockTime'):
        first['evidence'][name] = deepcopy(raw['evidence'][name])
    first['evidence']['blockhash'] = {'state':'not-requested'}
    first['evidence']['fee'] = {'state':'not-requested'}
    return first, evidence


def _exercise(fixture, report, measurements):
    """All paths originate from a freshly generated temporary full-source fixture."""
    from admission_exit_capture_checks import Opener
    from exit_submission_checks import FakeRpc
    from exit_accounting_checks import package, ReceiptRpc
    from exit_balance_checks import FakeRpc as BalanceRpc
    cases = report['cases']; observations = []
    observe = fresh_entry.signing.timing.fresh_quote.observe
    def record_evidence(*args, **kwargs):
        sink = kwargs['_evidence_sink']
        def capture(e): observations.append(e); sink(e)
        return observe(*args, **dict(kwargs, _evidence_sink=capture))
    with measurements.stage('entry-collection-sign-send'), patch.object(fresh_entry.signing.timing.fresh_quote, 'observe', record_evidence):
        entry, transports = fixture.integrate(lost=True)
        report['entry'] = leg(entry)
    check(len(observations) == 1, 'rehearsal-entry-evidence')
    e = observations[0]; clock = exit_settlement.view.now
    key = fixture.home/'signer.pk8'; key.unlink()
    before = fixture.files()
    cases['fresh-entry-one-send-retains-lost-response'] = 'passed'
    baseline = deepcopy(e['costInputs']['baseline'])
    baseline.update(kind='observed-devnet-deployment', observedAtMs=0)
    with patch.object(fresh_exit.collection.exit, 'BASELINE', baseline):
        with measurements.stage('entry-receipt-accounting'), patch.object(fresh_entry.signing.backend, '_invoke', side_effect=AssertionError('unexpected signer')):
            settled = settled_exit.advance(fixture.home, fixture.wallet, fixture.pool,
                receipt_opener=transports[0], clock=clock)
            check(settled['state']=='entry-settled-exit-not-prepared' and settled['receiptRequestsThisRun']==4,
                  'rehearsal-entry-settlement')
            check(settled['accounting']['accountingUsable'], 'rehearsal-entry-accounting')
        cases['entry-recovery-settles-without-key-or-resend'] = 'passed'
        first, evidence = exit_inputs(e, settled['accounting']['accounting'], clock())
        key.write_bytes(fixture.test_key); key.chmod(0o600)
        exit_rpcs = []; contexts = []
        class Lazy:
            def open(self, request, timeout=None):
                if not exit_rpcs:
                    book = exit_settlement.submission.transport._open(fixture.home, fixture.wallet, fixture.pool, clock)
                    try:
                        state = exit_settlement.submission.ExitSubmission(book).signing()
                        c = SimpleNamespace(exit_state=state, exit_wire=state['signed']['signedWireBase64'], path=book.j.path, signed={})
                    finally: book.close()
                    contexts.append(c); exit_rpcs.append(FakeRpc(c, lost=True))
                return exit_rpcs[0].open(request, timeout)
        with measurements.stage('exit-collection-sign-send'):
            result = fresh_exit.prepare_sign_submit(fixture.home, fixture.wallet, fixture.pool,
                allow_private_key_signing=True, allow_devnet_submit=True,
                collection_opener=Opener(first, evidence), submission_opener=Lazy(), clock=clock)
            report['exit'] = leg(result)
        key.unlink()
        cases['separate-fresh-exit-one-send-keeps-original-expiry'] = 'passed'
        c = contexts[0]; c.now = clock()
        c.book = lambda:exit_settlement.submission.transport._open(fixture.home, fixture.wallet, fixture.pool, clock)
        receipt = ReceiptRpc(c, package(c)[0]); balances = BalanceRpc(c)
        commit = exit_settlement.closure._commit
        def lost_commit(*args, **kwargs):
            commit(*args, **kwargs)
            raise OSError('synthetic lost closure response')
        # A committed write followed by a lost response must remain unknown until
        # independent replay. No rollback/retry inference from the exception.
        with measurements.stage('exit-receipt-accounting-closure'), patch.object(exit_settlement.closure, '_commit', lost_commit):
            result = exit_settlement.advance(fixture.home, fixture.wallet, fixture.pool,
                close_exit=True, receipt_opener=receipt, balance_opener=balances, clock=clock)
            check(result['state']=='inspection-required' and result['networkRequests']==8 and
                  result['closureRecorded'] is None, 'rehearsal-ambiguous-closure')
        cases['lost-closure-response-retains-uncertainty'] = 'passed'
        check(fixture.files()==before, 'rehearsal-source-mutated')
        (fixture.home/'STOP').touch(mode=0o600)
        journal = c.path.read_bytes()
        with patch.object(fresh_exit.backend, '_invoke', side_effect=AssertionError('unexpected signer')), \
             patch.object(exit_settlement.submission, 'recover', side_effect=AssertionError('unexpected receipt read')), \
             patch.object(exit_settlement.closure.balance, 'collect', side_effect=AssertionError('unexpected balances')):
            with measurements.stage('read-only-closure-recovery'):
                recovered = exit_settlement.status(fixture.home, fixture.wallet, fixture.pool, clock=clock)
                check(recovered['coherent'] and recovered['phase']=='closed' and recovered['closureRecorded'] and
                      recovered['stopRequested'] and recovered['networkRequests']==0, 'rehearsal-read-only-recovery')
            with measurements.stage('repeated-closure-recovery'):
                again = exit_settlement.advance(fixture.home, fixture.wallet, fixture.pool, close_exit=True, clock=clock)
                check(again['closureRecorded'] and again['networkRequests']==0 and not again['closureAppliedThisRun'],
                      'rehearsal-repeat-recovery')
        check(journal==c.path.read_bytes(), 'rehearsal-recovery-mutated')
        cases['stopped-keyless-recovery-needs-no-provider-or-execution'] = 'passed'
        cases['repeated-recovery-preserves-bytes-and-release-identity'] = 'passed'
        check(recovered['recordIdentity']==again['recordIdentity'] and recovered['scopedAccounting']==again['scopedAccounting'],
              'rehearsal-recovery-identity')
        totals = recovered['scopedAccounting']; original = recovered['accounting']['accounting']
        check(totals['feeHeldLamports']==totals['ownedAcquiredHeldAtomic']==totals['sourceProceedsHeldAtomic']=='0' and
              totals['protectedInventoryReleasedAtomic']=='0', 'rehearsal-scoped-accounting')
        check(int(original['originalFeeCommitmentLamports'])==int(totals['feePaidLamports'])+int(totals['unusedFeeReleasedLamports']),
              'rehearsal-fee-conservation')
        check(not recovered['fundsAvailableForNewEntry'] and not recovered['nextCycleAuthorized'], 'rehearsal-no-allocation')
        report['recovery'] = dict(state=recovered['state'], networkRequests=0, repeatNetworkRequests=0,
            closureIdentityPreserved=True, journalBytesUnchanged=True, stopPreserved=True,
            nextAction='inspect-closed-allocation-no-new-entry-authority')
        cases['scoped-conservation-does-not-credit-new-allocation'] = 'passed'
        check(all(sum(q['method']=='sendTransaction' for q in rpc.requests)==1 for rpc in (transports[0], exit_rpcs[0])),
              'rehearsal-exact-send-count')
        cases['two-separate-legs-never-resend'] = 'passed'
        before['STOP'] = b''
        check(fixture.files()==before, 'rehearsal-historical-source')
        report['originalSourceUnchanged'] = True  # Deliberately added STOP is accounted for.
        cases['historical-source-preserved-except-explicit-test-stop'] = 'passed'


def run():
    # Import fixture builders only for this explicit offline rehearsal. The CLI
    # accepts no home/wallet/pool/action argument and cannot target user journals.
    import test_fresh_entry as source
    class RunFixture(source.FullSourceEntryTests):
        pass
    fixture_type = RunFixture
    r = base(); measures = Measurements(); fixture = None
    class_started = False; instance_started = False
    # The outer directory owns even partially constructed fixture trees. A setup
    # exception must not strand a test key or rely on a fixture destructor.
    with tempfile.TemporaryDirectory(prefix='radar-offline-lifecycle-') as owned:
        with patch.object(tempfile, 'tempdir', owned):
            try:
                with patch('socket.socket', side_effect=AssertionError('real network forbidden')):
                    with measures.stage('fixture-setup'):
                        class_started = True; fixture_type.setUpClass()
                        fixture = fixture_type(); instance_started = True; fixture.setUp()
                        check(fixture.home.resolve().is_relative_to(Path(owned).resolve()), 'rehearsal-temporary-scope')
                    _exercise(fixture, r, measures)
                    r['state'] = 'offline-rehearsal-passed'
            except Exception as exc:
                r['diagnosticCode'] = str(exc) if str(exc) in DIAGNOSTICS else 'rehearsal-incomplete-inspect-stage'
                r['failedStage'] = measures.current_stage or 'fixture-setup'
            finally:
                for cleanup in ([fixture.tearDown] if instance_started else []) + ([fixture_type.tearDownClass] if class_started else []):
                    try: cleanup()
                    except Exception:
                        r.update(state='review-required', diagnosticCode='temporary-cleanup-incomplete')
                fixture_type.test_key = None
                r['timings'] = measures.rows
                r['casesPassed'] = len(r['cases'])
    r['temporaryLedgersRemoved'] = not Path(owned).exists()
    return r
