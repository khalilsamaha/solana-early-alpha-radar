"""Full-source offline completion followed by blocked closure assessment."""
from pathlib import Path

import successor_completion_checks as completion
import successor_closure as closure
from core import check

VERSION = 'successor-closure-rehearsal-1'
CONNECTED_CASES = completion.CONNECTED_CASES + 2


def tree(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}


def connected(c):
    completion.connected(c)
    f=c.f; report=c.report; expected=report['integration']['successorSha256']
    before=(tree(f.home),tree(c.path.parent))
    with completion.execution.fixture.phase(report,'successor-closure-blocked-after-matching-balances'):
        result=closure.status(f.home,f.wallet,f.pool,expected,clock=c.clock)
        report['closureContract']=result
        held=report['accountedHold']; amounts=result['held']
        check(result['state']=='successor-closure-blocked-held' and
            result['blockers']==['retired-exposure-unresolved'] and
            result['identity']['successorAccountingSha256']==report['successorAccounting']['recordSha256'],
            'closure-fixture-contract')
        check(amounts['remainingFeeHeldLamports']==held['feeHeldLamports'] and
            amounts['knownFeesPaidLamports']==held['feePaidLamports'] and
            amounts['retiredFeeExposureHeldLamports']==held['retiredFeeExposureHeldLamports'] and
            amounts['sourceProceedsHeldAtomic']==held['sourceProceedsHeldAtomic'] and
            amounts['protectedAcquiredInventoryAtomic']==held['protectedAcquiredInventoryAtomic'],
            'closure-fixture-held-binding')
        check(not any(result[k] for k in ('closureEligible','closureRecorded','scopedClosureRecorded',
            'freshBalancesEvaluated','reservationsReleased','retiredExposureReleased','fundsAvailableForNewEntry',
            'executionApproved','networkRequests','signaturesCreated','transactionsSent')), 'closure-fixture-authority')
        check(before==(tree(f.home),tree(c.path.parent)), 'closure-fixture-write')
    report['cases']['matching-successor-balances-cannot-release-retired-exposure']='passed'
    with completion.execution.fixture.phase(report,'keyless-stopped-closure-assessment-is-repeatable'):
        check(not c.key.exists(),'closure-fixture-key-removal')
        (f.home/'STOP').touch(mode=0o600)
        stopped=(tree(f.home),tree(c.path.parent))
        again=closure.status(f.home,f.wallet,f.pool,expected,clock=c.clock)
        semantic=lambda r:{k:v for k,v in r.items() if k not in ('signatureVerification','timingOptimization')}
        check(semantic(again)==semantic(result),
            'closure-fixture-stopped-history')
        check(stopped==(tree(f.home),tree(c.path.parent)), 'closure-fixture-stopped-write')
    report['cases']['closure-assessment-repeats-keyless-after-stop-without-write']='passed'
    report['closureContractPreservationPassed']=True


def run():
    report=completion.execution.fixture.run(_exercise=connected)
    report.update(format=VERSION,casesExpected=CONNECTED_CASES,executionApproved=False,
        scopedClosureRecorded=False,retiredExposureReleased=False,
        limitations=['Offline synthetic receipt/balance evidence only; no operational journal or key access.',
            'Passing means closure refusal is correct; no successful closure or release is implemented.',
            'Known successor effects do not resolve the retired attempt. All commitments remain held.',
            'The send and balance windows are unchanged and measured separately.'])
    if report['casesPassed']!=CONNECTED_CASES or not report.get('closureContractPreservationPassed') or not report['temporaryLedgersRemoved']:
        report['state']='review-required'
    return report
