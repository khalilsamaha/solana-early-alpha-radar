"""Explicit one-shot devnet replacement command; no retry, queue or new policy."""
import re
import controlled_acceptance as acceptance
import fresh_exit
from core import check, directory

VERSION = 'controlled-replacement-exit-1'
# A fixed production binding. Test fixtures may replace it in-process; the CLI
# accepts no RPC endpoint, clock, signer, imported report or execution callback.
EXECUTE = fresh_exit.replace_sign_submit


def validate(*, expected_preparation_sha256, allow_unsigned_replacement=False,
             allow_private_key_signing=False, allow_devnet_submit=False):
    check(all(x is True for x in (allow_unsigned_replacement,
        allow_private_key_signing, allow_devnet_submit)), 'replacement-three-explicit-opt-ins')
    check(type(expected_preparation_sha256) is str and
          re.fullmatch(r'[0-9a-f]{64}', expected_preparation_sha256) is not None,
          'replacement-exact-original-identity')


def execute(home, wallet, pool, *, expected_preparation_sha256,
            allow_unsigned_replacement=False, allow_private_key_signing=False,
            allow_devnet_submit=False):
    flags = dict(expected_preparation_sha256=expected_preparation_sha256,
        allow_unsigned_replacement=allow_unsigned_replacement,
        allow_private_key_signing=allow_private_key_signing,
        allow_devnet_submit=allow_devnet_submit)
    validate(**flags)
    check(type(wallet) is str and type(pool) is str and wallet and pool, 'replacement-explicit-scope')
    root = directory(home)
    report = dict(format=VERSION, network='devnet', state='inspection-required',
        dispatchCompleted=False, diagnosticCode=None, result=None, preparation=None,
        expectedOriginalPreparationSha256=expected_preparation_sha256,
        maximumNetworkRequests=25, maximumSendAttempts=1,
        unsignedReplacementOptIn=True, privateKeySigningOptIn=True, devnetSubmissionOptIn=True,
        automaticRetryAllowed=False, automaticNextAction=False, runtimeIntegrated=False,
        executionApproved=False, newEntryAuthorized=False, mainnetSupported=False,
        limitations=[
            'One explicit replacement of the identified expired unsigned preparation only.',
            'The original preparation, held inventory and fee policy remain preserved.',
            'No exception or missing report proves rollback; inspect the existing journals.',
            'Acknowledgment is not finalized receipt accounting or scoped closure.',
            'After an attempt, use status and existing signature recovery; never repeat execution.'])
    try:
        raw = EXECUTE(root, wallet, pool, **flags)
        report.update(dispatchCompleted=True, result=acceptance.projection(raw))
        report['state'] = report['result'].get('state', 'inspection-required')
        for key in ('collectionRequests', 'senderRequests'):
            if type(raw.get(key)) is int and 0 <= raw[key] <= 25:
                report['result'][key] = raw[key]
        p = raw.get('preparation')
        if type(p) is dict:
            public = {}
            for key in ('recordSha256', 'originalPreparationSha256'):
                if type(p.get(key)) is str and re.fullmatch(r'[0-9a-f]{64}', p[key]): public[key] = p[key]
            for key in ('createdThisRun', 'originalPreserved'):
                if type(p.get(key)) is bool: public[key] = p[key]
            if type(p.get('replacementCount')) is int and p['replacementCount'] == 1:
                public['replacementCount'] = 1
            report['preparation'] = public
    except fresh_exit.fresh_signing.ERRORS:
        # An exception can follow signing or a durable send. Do not infer effects.
        report['diagnosticCode'] = 'replacement-inspect-preserved-journals'
    return report


def exit_code(report):
    r = report.get('result') or {}
    return 0 if (report.get('dispatchCompleted') is True and
        report.get('state') == 'rpc-acknowledged' and
        r.get('completedWithinOriginalDeadline') is True) else 2
