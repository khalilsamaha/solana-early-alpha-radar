"""Explicit one-shot devnet continuation command; no retry, queue or new policy."""
import re
import controlled_acceptance as acceptance
import fresh_exit
from core import check, directory

VERSION = 'controlled-continuation-exit-1'
# A fixed production binding. Test fixtures may replace it in-process; the CLI
# accepts no RPC endpoint, clock, signer, imported report or execution callback.
EXECUTE = fresh_exit.continue_sign_submit


def identities(original,current):
    fresh_exit.continuation.preserved.identities((original,current))


@fresh_exit.view.cycles.binding.operation
@fresh_exit.fresh_signing.timing.signature_replay
def inspect(home,wallet,pool,*,expected_original_sha256,expected_current_sha256):
    """Read-only local eligibility; no signer key read, RPC, or preparation append."""
    from journal import read_only_journals
    identities(expected_original_sha256,expected_current_sha256)
    check(type(wallet) is str and type(pool) is str and wallet and pool,'continuation-explicit-scope')
    r=dict(format=VERSION+'-inspection',state='inspection-required',eligibleNow=False,
        expectedOriginalPreparationSha256=expected_original_sha256,
        expectedCurrentPreparationSha256=expected_current_sha256,
        networkRequests=0,privateKeyAccessed=False,signaturesCreated=0,transactionsSent=0,
        preparationPersisted=False,reservationReleased=False,executionApproved=False,
        automaticNextAction=False,diagnosticCode=None,
        limitations=['Local journal eligibility only; fresh RPC evidence and deadlines are revalidated during execution.',
                     'Inspection does not reserve a continuation or authorize signing; concurrent state changes can invalidate it.'])
    allowed={'continuation-limit-reached','preserved-exit-stopped','preserved-exit-schema',
        'preserved-exit-later-evidence','preserved-exit-backend-marker','preserved-exit-original-mismatch',
        'preserved-exit-replacement-required','preserved-exit-current-mismatch','preserved-exit-not-expired'}
    try:
        with fresh_exit.view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
            book=fresh_exit.submission.transport._open(root,wallet,pool,fresh_exit.view.now)
            try:
                record=fresh_exit.continuation.eligible(book,root,
                    (expected_original_sha256,expected_current_sha256),fresh_exit.view.now())
                # Preserve only the exact public scalars. No record, wire or raw evidence.
                r['heldConstraints']={key:record['binding'][key] for key in
                    ('quantityAtomic','protectedInventoryAtomic','feeCommitmentRemainingLamports','feeCapLamports')}
                r.update(state='continuation-eligible-research-only',eligibleNow=True)
            finally:book.close()
    except fresh_exit.fresh_signing.ERRORS as exc:
        r.update(state='inspection-required',eligibleNow=False)
        r.pop('heldConstraints',None)
        r['diagnosticCode']=str(exc) if str(exc) in allowed else 'continuation-inspection-unavailable'
    return r


def validate(*, expected_original_sha256, expected_current_sha256, allow_unsigned_continuation=False,
             allow_private_key_signing=False, allow_devnet_submit=False):
    check(all(x is True for x in (allow_unsigned_continuation,
        allow_private_key_signing, allow_devnet_submit)), 'continuation-three-explicit-opt-ins')
    identities(expected_original_sha256,expected_current_sha256)


def execute(home, wallet, pool, *, expected_original_sha256, expected_current_sha256,
            allow_unsigned_continuation=False, allow_private_key_signing=False,
            allow_devnet_submit=False):
    flags = dict(expected_original_sha256=expected_original_sha256,expected_current_sha256=expected_current_sha256,
        allow_unsigned_continuation=allow_unsigned_continuation,
        allow_private_key_signing=allow_private_key_signing,
        allow_devnet_submit=allow_devnet_submit)
    validate(**flags)
    check(type(wallet) is str and type(pool) is str and wallet and pool, 'continuation-explicit-scope')
    root = directory(home)
    report = dict(format=VERSION, network='devnet', state='inspection-required',
        dispatchCompleted=False, diagnosticCode=None, result=None, preparation=None,
        expectedOriginalPreparationSha256=expected_original_sha256,
        expectedCurrentPreparationSha256=expected_current_sha256,
        maximumNetworkRequests=25, maximumSendAttempts=1,
        unsignedContinuationOptIn=True, privateKeySigningOptIn=True, devnetSubmissionOptIn=True,
        automaticRetryAllowed=False, automaticNextAction=False, runtimeIntegrated=False,
        executionApproved=False, newEntryAuthorized=False, mainnetSupported=False,
        limitations=[
            'One explicit continuation of the identified expired unsigned replacement only.',
            'Both predecessor preparations, held inventory and fee policy remain preserved.',
            'No exception or missing report proves rollback; inspect the existing journals.',
            'Acknowledgment is not finalized receipt accounting or scoped closure.',
            'After an attempt, use status and existing signature recovery; never repeat execution.'])
    try:
        raw = EXECUTE(root, wallet, pool, **flags)
        report.update(dispatchCompleted=True, result=acceptance.projection(raw))
        report['collectionDiagnostic']=fresh_exit.collection_diagnostics.summary(raw.get('collectionDiagnostic'))
        report['canonicalDigestReplay']=fresh_exit.canonical_replay.summary(raw.get('canonicalDigestReplay'))
        report['canonicalTextReplay']=fresh_exit.serialization_replay.summary(raw.get('canonicalTextReplay'))
        report['state'] = report['result'].get('state', 'inspection-required')
        for key in ('collectionRequests', 'senderRequests'):
            if type(raw.get(key)) is int and 0 <= raw[key] <= 25:
                report['result'][key] = raw[key]
        p = raw.get('preparation')
        if type(p) is dict:
            public = {}
            for key in ('recordSha256', 'originalPreparationSha256','previousPreparationSha256'):
                if type(p.get(key)) is str and re.fullmatch(r'[0-9a-f]{64}', p[key]): public[key] = p[key]
            for key in ('createdThisRun', 'originalPreserved','replacementPreserved','existingReplacementLimitUnchanged'):
                if type(p.get(key)) is bool: public[key] = p[key]
            if type(p.get('continuationCount')) is int and p['continuationCount'] == 1:
                public['continuationCount'] = 1
            report['preparation'] = public
    except fresh_exit.fresh_signing.ERRORS:
        # An exception can follow signing or a durable send. Do not infer effects.
        report['diagnosticCode'] = 'continuation-inspect-preserved-journals'
    return report


def exit_code(report):
    r = report.get('result') or {}
    return 0 if (report.get('dispatchCompleted') is True and
        report.get('state') == 'rpc-acknowledged' and
        r.get('completedWithinOriginalDeadline') is True) else 2
