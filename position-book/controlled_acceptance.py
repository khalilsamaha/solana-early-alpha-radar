"""Explicit controlled-devnet command routing. Never chain transactions or retry."""
from functools import partial
import os
import re

import fresh_entry
import fresh_exit
import settled_exit
import exit_settlement
import admission_lifecycle
from core import check, directory
from contract import atomic, uint
from journal import read_only_journals

VERSION = 'controlled-devnet-acceptance-1'
view = fresh_entry.signing.view
CAPS = ('maximum_exit_attempts', 'maximum_exit_fee_lamports', 'maximum_total_fee_lamports')
SIGNING = {'entry', 'exit'}
RECONCILING = {'recover-entry-signature', 'settle-entry', 'recover-exit-signature', 'settle-exit', 'close-exit'}
ACTIONS = {'status'} | SIGNING | RECONCILING
OPERATIONS = {
    'entry': fresh_entry.prepare_sign_submit,
    'exit': fresh_exit.prepare_sign_submit,
    'recover-entry-signature': fresh_entry.signing.recover,
    'settle-entry': partial(settled_exit.advance, prepare_exit=False),
    'recover-exit-signature': fresh_exit.backend.recover,
    'settle-exit': partial(exit_settlement.advance, close_exit=False),
    'close-exit': partial(exit_settlement.advance, close_exit=True),
}
REQUEST_CEILINGS = dict(status=0, entry=25, exit=25, **{
    'recover-entry-signature': 0, 'settle-entry': 4,
    'recover-exit-signature': 0, 'settle-exit': 4, 'close-exit': 8})
# Export only these public scalar projections, never raw evidence or signed bytes.
FIELDS = {'state', 'phase', 'stage', 'coherent', 'stopRequested', 'diagnosticCode',
    'networkRequests', 'totalRequestAttempts', 'sendRequestsThisRun',
    'signerInvocationAttempts', 'signerAcknowledgmentValidated', 'originalDeadlineMs',
    'remainingMs', 'completedWithinOriginalDeadline', 'originalDeadlineCheckedBeforeSend',
    'applicationSendBoundaryRecorded', 'signaturesCreated', 'privateKeyAccessed',
    'closureRecorded', 'closureAppliedThisRun', 'accountingAppliedThisRun',
    'reservationReleased', 'fundsAvailableForNewEntry', 'nextCycleAuthorized',
    'backendInvokedThisRun', 'signaturesCreatedThisRun', 'privateKeyAccessedThisRun',
    'accountingUsable', 'slotOccupied', 'historicalSourceClosed', 'newEntryAuthorized'}
ATOMIC_FIELDS = {'sourcePrincipalHeldAtomic', 'sourcePrincipalSpentAtomic',
    'sourceProceedsHeldAtomic', 'ownedAcquiredHeldAtomic', 'protectedAcquiredInventoryAtomic',
    'feeHeldLamports', 'feePaidLamports', 'sourceProceedsReleasedAtomic',
    'unusedFeeReleasedLamports', 'protectedInventoryReleasedAtomic'}
IDENTITY_FIELDS = {'admissionHeadSha256', 'entryAccountingSha256', 'exitAccountingSha256', 'closureSha256'}


def validate(action, *, allow_private_key_signing=False, allow_devnet_submit=False,
             allow_reconcile=False, **caps):
    check(action in ACTIONS, 'acceptance-action')
    flags = (allow_private_key_signing, allow_devnet_submit, allow_reconcile)
    check(all(type(x) is bool for x in flags), 'acceptance-explicit-flags')
    check(flags == ((True, True, False) if action in SIGNING else
                    (False, False, True) if action in RECONCILING else (False, False, False)),
          'acceptance-action-opt-ins')
    check(set(caps) <= set(CAPS), 'acceptance-policy-fields')
    if action == 'entry':
        check(set(caps) == set(CAPS) and all(v is not None for v in caps.values()), 'acceptance-entry-caps')
        uint(caps['maximum_exit_attempts'], 3, 'acceptance-entry-caps', minimum=1)
        fee = atomic(caps['maximum_exit_fee_lamports'], 'acceptance-entry-caps', positive=True)
        total = atomic(caps['maximum_total_fee_lamports'], 'acceptance-entry-caps', positive=True)
        check(fee <= 10000 and total <= 40000 and fee*caps['maximum_exit_attempts'] < total,
              'acceptance-entry-caps')
    else: check(not caps, 'acceptance-no-policy-replacement')


@view.cycles.binding.operation
@fresh_entry.signing.timing.signature_replay
def status(home, wallet, pool):
    """Read-only local facts, including a vacant slot. No key inspection or RPC."""
    with view.cycles.c.source_lock(home, wallet) as root, read_only_journals():
        sibling = root.parent/(root.name+'-entry-handoff-v1')
        if not os.path.lexists(sibling):
            source = view.read_locked(root, wallet, pool, view.now, _closed_history=True)
            check(source['phase']=='closed', 'acceptance-source-not-closed')
            return dict(state='local-scope-consistent', coherent=True, slotOccupied=False,
                historicalSourceClosed=True, stopRequested=view.cycles.c.submit.swap.stop(root),
                networkRequests=0, privateKeyAccessed=False, signaturesCreated=0,
                fundsAvailableForNewEntry=False, newEntryAuthorized=False)
    # The lifecycle reader owns its own non-reentrant source lock. Even partial
    # or empty artifacts count as occupied; unavailable is never permission.
    result = admission_lifecycle.inspect(root, wallet, pool)
    return dict(result, slotOccupied=True, newEntryAuthorized=False)


def projection(result):
    public = {}
    for key in FIELDS:
        if key not in result: continue
        value = result[key]
        if value is None or type(value) is bool or (type(value) is int and abs(value)<2**53):
            public[key] = value
        elif type(value) is str and re.fullmatch(r'[a-z][a-z0-9-]{0,95}', value):
            public[key] = value
    for name, fields, pattern in (('scopedAccounting', ATOMIC_FIELDS, r'(0|[1-9][0-9]{0,19})'),
                                  ('recordIdentity', IDENTITY_FIELDS, r'[0-9a-f]{64}')):
        if type(result.get(name)) is dict:
            public[name] = {k:v for k,v in result[name].items() if k in fields and
                (v is None or (type(v) is str and re.fullmatch(pattern, v)))}
    return public


def dispatch(action, home, wallet, pool, *, allow_private_key_signing=False,
             allow_devnet_submit=False, allow_reconcile=False, **caps):
    validate(action, allow_private_key_signing=allow_private_key_signing,
        allow_devnet_submit=allow_devnet_submit, allow_reconcile=allow_reconcile, **caps)
    check(type(wallet) is str and type(pool) is str and wallet and pool, 'acceptance-scope')
    # Every called operation independently verifies wallet/pool against private
    # source evidence and keeps its own locks and original deadline guards.
    root = directory(home)
    r = dict(format=VERSION, action=action, network='devnet', state='inspection-required',
        dispatchCompleted=False, diagnosticCode=None, result=None,
        maximumNetworkRequests=REQUEST_CEILINGS[action], maximumSendAttempts=1 if action in SIGNING else 0,
        privateKeySigningOptIn=allow_private_key_signing, devnetSubmissionOptIn=allow_devnet_submit,
        reconciliationOptIn=allow_reconcile, automaticRetryAllowed=False,
        automaticNextAction=False, runtimeIntegrated=False, executionApproved=False,
        newEntryAuthorized=False, mainnetSupported=False,
        limitations=[
            'One explicit controlled-devnet action per invocation; no chained transaction or polling loop.',
            'Normal command completion does not prove delivery, finality, closure or profitability.',
            'Preserve all journals after errors or interruption; status and recovery never resume a send.',
            'Recovery may append receipt or acknowledgment evidence; status alone is read-only.',
            'Closure is scoped historical accounting, not permission or funds for another entry.'])
    try:
        if action == 'status': result = status(root, wallet, pool)
        elif action in SIGNING:
            result = OPERATIONS[action](root, wallet, pool,
                allow_private_key_signing=True, allow_devnet_submit=True, **caps)
        else: result = OPERATIONS[action](root, wallet, pool)
        r.update(dispatchCompleted=True, result=projection(result))
        r['state'] = r['result'].get('state', 'inspection-required')
    except fresh_entry.signing.ERRORS:
        # An exception may follow a durable commit/send. Never assert zero effects.
        r['diagnosticCode'] = 'acceptance-inspect-preserved-journals'
    return r
