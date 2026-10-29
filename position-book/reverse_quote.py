"""Bind a fresh current-state reverse quote to the full reference entry output.

Neither quote describes a post-entry pool. No acquired quantity or round-trip
return is invented. The live caller separately validates pinned deployment,
actual reverse-side funds, own-bank simulation and locked reservations.
"""
from copy import deepcopy
from core import check
from contract import digest
from fresh_packet import scope_check
from cpmm_quote import derive

VERSION = 'controlled-reverse-quote-reference-1'


def prepare(capture, entry_scope, *, now_ms):
    scope_check(entry_scope)
    entry = derive(capture, entry_scope, slippage_bps=100, now_ms=now_ms)
    quantity = entry['quote']['outAmount']
    # Preserve exact quantity: never cap/truncate output to make a reverse fit.
    check(0 < int(quantity) <= 1000, 'reverse-reference-quantity-over-cap')
    reverse = deepcopy(entry_scope)
    a = reverse['accounts']
    for left, right in (('source','destination'),('inputMint','outputMint'),('inputVault','outputVault')):
        a[left], a[right] = a[right], a[left]
    reverse.update(amountIn=quantity, minimumAmountOut='1')
    scope_check(reverse)
    exit_price = derive(capture, reverse, slippage_bps=100, now_ms=now_ms)
    reverse['minimumAmountOut'] = exit_price['quote']['minimumOutAmount']
    scope_check(reverse)
    return reverse, exit_price, dict(format=VERSION,
        state='current-state-reverse-reference-bound',
        entryReference=entry,
        entryScopeSha256=digest(entry_scope), reverseScopeSha256=digest(reverse),
        referenceEntryQuoteSha256=digest(entry['quote']), reverseQuoteSha256=digest(exit_price['quote']),
        referenceEntryOutputAtomic=quantity, reverseInputAtomic=quantity,
        entryExecuted=False, entryFundingVerified=False, entrySimulationVerified=False,
        acquiredTokensAssumed=False, postEntryPoolObserved=False,
        quotedRoundTripReturnPct=None, actualExecutionObserved=False,
        limitations=[
            'Both quotes use the same observed pre-entry pool; neither includes a hypothetical entry state mutation.',
            'Reverse simulation requires tokens already in the actual source account; expected entry proceeds do not fund it.',
            'Reference entry is priced but its funds, message, fee and simulation are not validated in this command.',
            'Exact full output must fit the existing 1000-atomic scope; no truncation or partial exit.'])


def fee_plan(entry_scope, exit_scope, reference, assessed):
    """Known cap subtotal only; missing budgets can never become a funded round trip."""
    scope_check(entry_scope); scope_check(exit_scope)
    expected = deepcopy(entry_scope['accounts'])
    for left, right in (('source','destination'),('inputMint','outputMint'),('inputVault','outputVault')):
        expected[left], expected[right] = expected[right], expected[left]
    check(exit_scope['accounts'] == expected
          and reference['entryScopeSha256'] == digest(entry_scope)
          and reference['reverseScopeSha256'] == digest(exit_scope)
          and reference['referenceEntryOutputAtomic'] == reference['reverseInputAtomic'] == exit_scope['amountIn'],
          'reverse-cost-scope')
    check(assessed['state']=='single-leg-cost-evidence-consistent', 'reverse-cost-required')
    c = assessed['calculation']
    check(c['networkFeeCapLamports']==exit_scope['maxTotalFeeLamports']
          and c['inputAtomic']==exit_scope['amountIn']
          and c['inputMint']==exit_scope['accounts']['inputMint']
          and c['outputMint']==exit_scope['accounts']['outputMint'], 'reverse-cost-scope')
    entry_cap = int(entry_scope['maxTotalFeeLamports'])
    exit_cap = int(c['networkFeeCapLamports'])
    available = int(c['nativeSpendableLamports'])
    return dict(state='partial-fee-plan-only',
        declaredEntryFeeCapLamports=str(entry_cap), validatedExitFeeCapLamports=str(exit_cap),
        knownFeeCapSubtotalLamports=str(entry_cap+exit_cap),
        currentNativeSpendableLamports=str(available),
        knownFeeCapSubtotalCovered=available>=entry_cap+exit_cap,
        shortfallForKnownFeeCapsLamports=str(max(0,entry_cap+exit_cap-available)),
        validatedEntryFeeLamports=None, failedAttemptBudgetLamports=None,
        requiredNativeForCompleteRoundTripLamports=None, netProfit=None,
        roundTripFundingEstablished=False, reservationCreated=False, executionApproved=False,
        limitations=[
            'Subtotal adds two network caps once; priority is already included.',
            'Entry cap is a declared policy bound, not validated entry-fee evidence.',
            'Unspecified failure/other cost budgets remain unknown, even if the known subtotal fits.',
            'No round-trip simulation, principal transfer, durable allocation or economics claim.'])
