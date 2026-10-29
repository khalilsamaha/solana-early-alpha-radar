"""Offline reverse-reference checks using raw synthetic pool evidence."""
from copy import deepcopy
import fresh_quote
from preflight_checks import fixture, NOW, edit
from swap_rehearsal import scope_for
from reverse_quote import prepare, fee_plan, VERSION


def inputs():
    c, _ = fixture(True)
    scope = scope_for(c['packet']['policy'])
    scope.update(amountIn='1000', minimumAmountOut='1', maxTotalFeeLamports='10000')
    raw, _ = fresh_quote.preflight.split_capture(c)
    return raw, scope


def run():
    cases = {}
    raw, entry = inputs()
    before = deepcopy((raw, entry))
    reverse, price, ref = prepare(raw, entry, now_ms=NOW)
    assert (raw, entry) == before
    assert reverse['amountIn'] == ref['entryReference']['quote']['outAmount'] == '906'
    assert reverse['accounts']['source'] == entry['accounts']['destination']
    assert reverse['accounts']['inputVault'] == entry['accounts']['outputVault']
    assert ref['quotedRoundTripReturnPct'] is None and not ref['postEntryPoolObserved']
    cases['exact-reference-and-unchanged-inputs'] = 'passed'
    assessment = dict(state='single-leg-cost-evidence-consistent', calculation=dict(
        networkFeeCapLamports=reverse['maxTotalFeeLamports'], inputAtomic=reverse['amountIn'],
        inputMint=reverse['accounts']['inputMint'], outputMint=reverse['accounts']['outputMint'],
        nativeSpendableLamports='100000'))
    plan = fee_plan(entry, reverse, ref, assessment)
    assert plan['knownFeeCapSubtotalLamports'] == '20000'
    assert plan['knownFeeCapSubtotalCovered'] and not plan['roundTripFundingEstablished']
    assert plan['failedAttemptBudgetLamports'] is None and plan['netProfit'] is None
    cases['funded-subtotal-is-not-roundtrip-funding'] = 'passed'
    low = deepcopy(assessment); low['calculation']['nativeSpendableLamports'] = '10000'
    p = fee_plan(entry, reverse, ref, low)
    assert not p['knownFeeCapSubtotalCovered'] and p['shortfallForKnownFeeCapsLamports'] == '10000'
    cases['known-subtotal-shortfall-visible'] = 'passed'
    def rejected(name, fn):
        try: fn()
        except ValueError: cases[name] = 'rejected'; return
        raise ValueError('reverse-check-accepted-invalid-case')
    rejected('stale-original-pool', lambda: prepare(raw,entry,now_ms=NOW+20000))
    wrong = deepcopy(entry); wrong['network'] = 'mainnet-beta'
    rejected('wrong-network',lambda:prepare(raw,wrong,now_ms=NOW))
    big = deepcopy(raw); edit(big,5,64,(100000).to_bytes(8,'little'))
    rejected('output-over-cap-never-truncated',lambda:prepare(big,entry,now_ms=NOW))
    wrong = deepcopy(reverse); wrong['amountIn'] = '905'
    rejected('quantity-link-changed',lambda:fee_plan(entry,wrong,ref,assessment))
    wrongref = deepcopy(ref); wrongref['entryScopeSha256'] = '0'*64
    rejected('entry-reference-changed',lambda:fee_plan(entry,reverse,wrongref,assessment))
    wrongcost = deepcopy(assessment); wrongcost['calculation']['inputMint'] = entry['accounts']['inputMint']
    rejected('cost-direction-changed',lambda:fee_plan(entry,reverse,ref,wrongcost))
    rejected('unavailable-cost',lambda:fee_plan(entry,reverse,ref,dict(state='unavailable')))
    return dict(format=VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,networkRequests=0,signaturesCreated=0,transactionsSent=0,
        executionApproved=False,productionStateChanged=False)
