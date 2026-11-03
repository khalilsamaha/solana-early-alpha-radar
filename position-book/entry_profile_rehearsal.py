"""Detailed entry timings against synthetic replies and disposable test keys."""
from pathlib import Path
import platform
import tempfile
from unittest.mock import patch

import entry_profile as profile
import fresh_entry
from core import check

VERSION = 'entry-profile-rehearsal-1'


def run():
    from test_fresh_entry import FullSourceEntryTests
    class Fixture(FullSourceEntryTests):
        pass
    r = dict(format=VERSION, state='review-required', cases={}, casesPassed=0,
        mode='synthetic-offline', profile=None, entry=None, recovery=None, signatureVerification=None,
        diagnosticCode=None, temporaryLedgersRemoved=False, originalSourceUnchanged=False,
        realNetworkRequests=0, transactionsSent=0, productionWalletAccessed=False,
        disposableTestKeySigning=True, runtimeIntegrated=False, executionApproved=False,
        timingApproval=False, measuredProviderLatency=False, pythonVersion=platform.python_version(),
        limitations=[
            'One offline sample using actual collectors, admission journals and isolated test-key signer.',
            'Provider replies and receipts are synthetic; lazy fixture construction can add local test overhead.',
            'Nested inclusive spans must not be added; gaps between spans are not attributed to a stage.',
            'A completed span is normal return, not transaction success, delivery or finality.',
            'Diagnostic clocks never authorize work, refresh expiry, retry or change the existing execution guards.',
            'No operational scope, live execution, wallet-wide allocation or profitability approval.'])
    p = profile.Profile(); fixture = None; class_started = instance_started = False
    with tempfile.TemporaryDirectory(prefix='radar-offline-entry-profile-') as owned:
        with patch.object(tempfile, 'tempdir', owned):
            try:
                with patch('socket.socket', side_effect=AssertionError('real network forbidden')):
                    class_started = True; Fixture.setUpClass()
                    fixture = Fixture(); instance_started = True; fixture.setUp()
                    check(fixture.home.resolve().is_relative_to(Path(owned).resolve()), 'profile-temporary-scope')
                    # Setup/signature fixture generation is outside the capture.
                    with profile.capture(p):
                        result, transports = fixture.integrate(lost=True)
                    measured = p.report()
                    check(result['state']=='submission-unknown' and result['sendRequestsThisRun']==1,
                          'profile-one-send')
                    check(result['networkRequests']==25 and result['signerAcknowledgmentValidated'], 'profile-connected-entry')
                    r['entry'] = dict(state=result['state'], syntheticRequestAttempts=25,
                        syntheticSendAttempts=1, recordedSignatures=1,
                        completedWithinOriginalDeadline=result['completedWithinOriginalDeadline'])
                    r['cases']['actual-entry-keeps-lost-response-and-single-send'] = 'passed'
                    check(measured['valid'] and len(measured['spans'])==len(profile.STAGES) and
                          {x['stage'] for x in measured['spans']}==profile.STAGES and
                          all(x['completed'] for x in measured['spans']), 'profile-incomplete')
                    r['cases']['all-expected-phases-recorded-with-valid-clocks'] = 'passed'
                    check(measured['originalDeadlineMs']==result['originalDeadlineMs'] and
                          result['completedWithinOriginalDeadline'] and measured['sendGuardRemainingMs']>0,
                          'profile-original-deadline')
                    r['cases']['original-deadline-and-send-guard-remain-enforced'] = 'passed'
                    metrics = dict(attempt=result['attemptSignatureVerification'],
                        signing=result['signingSignatureVerification'],
                        submission=result['submissionSignatureVerification'])
                    check(result['entryVerificationVersion']=='entry-attempt-verification-1' and
                          metrics['signing']['sharedWithParent'] and metrics['submission']['sharedWithParent'] and
                          metrics['attempt']['verifierProcesses']>0 and
                          metrics['submission']['verifierProcesses']==0 and
                          metrics['submission']['memoHits']>0 and
                          fresh_entry.signing.timing.wire._SIGNATURE_SCOPE.get() is None,
                          'profile-attempt-verification')
                    for key in ('verificationCalls', 'verifierProcesses', 'memoHits', 'capacityBypasses'):
                        check(metrics['attempt'][key]==metrics['signing'][key]+metrics['submission'][key],
                              'profile-verification-counters')
                    r['signatureVerification'] = dict(version=result['entryVerificationVersion'], **metrics)
                    r['cases']['attempt-reuses-exact-verification-and-clears-after-return'] = 'passed'
                    (fixture.home/'signer.pk8').unlink(); (fixture.home/'STOP').touch(mode=0o600)
                    before = fixture.files()
                    with patch.object(fresh_entry.signing.backend, '_invoke', side_effect=AssertionError('signer forbidden')):
                        recovered = fresh_entry.recover(fixture.home, fixture.wallet, fixture.pool,
                            opener=transports[0], clock=fresh_entry.signing.view.now)
                        again = fresh_entry.recover(fixture.home, fixture.wallet, fixture.pool,
                            opener=transports[0], clock=fresh_entry.signing.view.now)
                    check(recovered['state']=='entry-effects-observed' and recovered['sendRequestsThisRun']==0 and
                          again['networkRequestsThisRun']==0 and not again['resumesEntry'], 'profile-recovery')
                    r['cases']['keyless-stopped-recovery-never-resumes-entry'] = 'passed'
                    check(sum(q['method']=='sendTransaction' for q in transports[0].requests)==1, 'profile-no-resend')
                    r['cases']['repeated-recovery-does-not-resend'] = 'passed'
                    check(fixture.files()==before, 'profile-source-preserved')
                    r['originalSourceUnchanged'] = True
                    r['cases']['historical-source-preserved'] = 'passed'
                    r['recovery'] = dict(state=recovered['state'], repeatNetworkRequests=0, resumesEntry=False)
                    r['state'] = 'offline-entry-profile-passed'
            except Exception:
                # Never export exception text, paths, signatures or raw evidence.
                r['diagnosticCode'] = 'entry-profile-incomplete'
            finally:
                for cleanup in ([fixture.tearDown] if instance_started else []) + ([Fixture.tearDownClass] if class_started else []):
                    try: cleanup()
                    except Exception:
                        r.update(state='review-required', diagnosticCode='temporary-cleanup-incomplete')
                Fixture.test_key = None
                r['profile'] = p.report(); r['casesPassed'] = len(r['cases'])
    r['temporaryLedgersRemoved'] = not Path(owned).exists()
    return r
