"""Bridge private raw evidence to admission under the controlled source lock.

No report import, signer invocation, send, third-cycle allocation or live CLI.
The separate admission ledger is an engineering reservation prototype only.
"""
from copy import deepcopy
from pathlib import Path
import reservation_view as view
from core import check
from journal import read_only_journals
from pre_sign_admission import Admission, MAX_EVIDENCE_BYTES, encoded

VERSION='locked-admission-binding-1'
IDENTITY=('phase','wallet','pool','nativeHeldLamports','tokenAccounts',
          'ledgerHeadSha256','cycleBindingSha256')


def same(current, expected, wallet, pool):
    check(current['phase']=='closed' and current['wallet']==wallet and current['pool']==pool,
          'admission-source-scope')
    check(all(current[k]==expected[k] for k in IDENTITY), 'admission-source-changed')


@view.cycles.binding.operation
def prepare(home, wallet, pool, admission, evidence, *, clock=view.now):
    """Reserve and record uncertainty while retaining the actual cooperating lock.

    Caller opens an isolated admission ledger first. Source journal connections
    remain read-only. Evidence is private caller data, not an exported summary.
    """
    check(type(admission) is Admission, 'admission-instance-required')
    check(not admission.j.path.resolve().is_relative_to(Path(home).resolve()), 'admission-outside-source-required')
    check(len(encoded(evidence).encode())<=MAX_EVIDENCE_BYTES, 'admission-evidence-cap')
    evidence=deepcopy(evidence)
    scope=admission.policy['scope']['accounts']
    check(scope['wallet']==wallet and scope['pool']==pool, 'admission-policy-source')
    expected=evidence['costInputs']['reservations']
    with view.cycles.c.source_lock(home,wallet) as root, read_only_journals():
        before=view.read_locked(root,wallet,pool,clock)
        same(before,expected,wallet,pool)
        check(not view.cycles.c.submit.swap.stop(root), 'stop-marker-present')
        reserved=admission.reserve(evidence)
        check(reserved['state']=='reserved', 'admission-not-unsigned-reserved')
        # Independent replay after the durable reservation. If it fails the hold
        # survives, but the signing boundary is never reached.
        after=view.read_locked(root,wallet,pool,clock)
        same(after,before,wallet,pool)
        check(before['readStartedAtMs']<=before['observedAtMs']<=after['readStartedAtMs']
              <=after['observedAtMs']<=clock(), 'admission-source-clock')
        check(not view.cycles.c.submit.swap.stop(root), 'stop-marker-present')
        result=admission.mark_signing_boundary(evidence)
        # A stop may arrive while the final raw checks run. Retain the durable
        # boundary and budget, mark stopped, and withhold a successful handoff.
        if view.cycles.c.submit.swap.stop(root):
            admission.stop()
            check(False, 'stop-marker-present')
        return dict(format=VERSION,state='locked-admission-boundary-recorded',admission=result,
            sourceReservationProvenanceVerified=True,
            sourceWitness=dict(ledgerHeadSha256=after['ledgerHeadSha256'],
                cycleBindingSha256=after['cycleBindingSha256'],firstReadAtMs=before['observedAtMs'],
                finalReadAtMs=after['observedAtMs']),sourceStateChanged=False,
            sourceConnectionsReadOnly=True,networkRequests=0,signaturesCreated=0,transactionsSent=0,
            executionApproved=False,signerInvocationAllowed=False,liveSenderIntegrated=False,
            walletWideReservationsKnown=False,productionLedgerUpdated=False)
