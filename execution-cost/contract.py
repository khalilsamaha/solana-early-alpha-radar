"""Pure hypothetical USDC round-trip economics; never execution permission.

Inputs are caller assertions, not authenticated quotes or measured fills. This
module has no network, wallet, database, model, or production-service adapter.
"""
import hashlib
import json
import re

VERSION = 'execution-cost-contract-1'
USDC = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
U64 = 2**64 - 1
MAX_CLOCK = 2**53 - 1
LAMPORTS_PER_SOL = 1_000_000_000


class Rejected(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Rejected(code)


def fields(value, keys, code):
    require(type(value) is dict and set(value) == set(keys.split()), code)


def integer(value, maximum, code, minimum=0):
    require(type(value) is int and minimum <= value <= maximum, code)
    return value


def atomic(value, code, positive=False):
    require(type(value) is str and len(value) <= 20 and
            re.fullmatch(r'0|[1-9][0-9]*', value) is not None, code)
    number = int(value)
    require(int(positive) <= number <= U64, code)
    return number


def mint(value):
    require(type(value) is str and 32 <= len(value) <= 44, 'mint-invalid')
    alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    n = 0
    for char in value:
        require(char in alphabet, 'mint-invalid')
        n = n * 58 + alphabet.index(char)
    raw = bytes((len(value) - len(value.lstrip('1')))) + n.to_bytes((n.bit_length()+7)//8, 'big')
    require(len(raw) == 32, 'mint-invalid')
    return value


def ceil_div(n, d):
    return (n + d - 1) // d


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def evaluate(packet, *, now_ms):
    """Report margin under explicit costs. Sufficient margin is never approval."""
    report = dict(format=VERSION, state='invalid', reasons=[], calculation=None,
                  networkRequests=0, signaturesCreated=0, transactionsSent=0,
                  productionStateChanged=False, modelEvaluated=False,
                  executionApproved=False, measuredNetProfit=False,
                  inputAuthenticityVerified=False)
    try:
        report.update(_evaluate(packet, now_ms))
    except Rejected as exc:
        report['reasons'] = [str(exc)]
    return report


def _evaluate(p, now):
    fields(p, 'format policy buy sell costs nativeValuation nativeSpendableLamports', 'packet-schema')
    require(p['format'] == VERSION, 'packet-format')
    integer(now, MAX_CLOCK, 'clock-invalid')
    policy = p['policy']
    fields(policy, 'maxQuoteAgeMs maxValuationAgeMs additionalExitHaircutBps minimumSurplusUsdcAtomic', 'policy-schema')
    quote_age = integer(policy['maxQuoteAgeMs'], 60000, 'quote-age-policy', 1)
    rate_age = integer(policy['maxValuationAgeMs'], 60000, 'valuation-age-policy', 1)
    haircut = integer(policy['additionalExitHaircutBps'], 10000, 'haircut-invalid')
    minimum = atomic(policy['minimumSurplusUsdcAtomic'], 'minimum-surplus-invalid')
    reasons = []
    amounts = []
    for name in ('buy', 'sell'):
        q = p[name]
        fields(q, 'status inputMint outputMint inAmount outAmount requestedAtMs receivedAtMs', 'quote-schema')
        require(q['status'] in ('quoted', 'unavailable'), 'quote-status')
        mint(q['inputMint']); mint(q['outputMint'])
        start = integer(q['requestedAtMs'], MAX_CLOCK, 'quote-time-invalid')
        received = integer(q['receivedAtMs'], MAX_CLOCK, 'quote-time-invalid')
        require(start <= received <= now, 'quote-time-order')
        # Receipt time cannot make a slow request appear fresh.
        if now - start > quote_age:
            reasons.append(name + '-quote-stale')
        amount = atomic(q['inAmount'], 'quote-input-invalid', positive=True)
        if q['status'] == 'unavailable':
            require(q['outAmount'] is None, 'unavailable-quote-has-output')
            reasons.append(name + '-quote-unavailable')
            output = None
        else:
            output = atomic(q['outAmount'], 'quote-output-invalid', positive=True)
        amounts.append((amount, output))
    buy, sell = p['buy'], p['sell']
    require(buy['inputMint'] == sell['outputMint'] == USDC and
            buy['outputMint'] == sell['inputMint'] != USDC, 'round-trip-mints')
    require(sell['requestedAtMs'] >= buy['receivedAtMs'], 'reverse-before-buy-response')
    principal, quantity = amounts[0]
    if quantity is not None:
        require(quantity == amounts[1][0], 'reverse-quantity-mismatch')
    costs = p['costs']
    fields(costs, 'coverage entryNetworkFeeCapLamports exitNetworkFeeCapLamports entryPriorityIncludedLamports exitPriorityIncludedLamports entryTipCapLamports exitTipCapLamports failedAttemptBudgetLamports rentDebitLamports otherUsdcDebitAtomic', 'cost-schema')
    require(costs['coverage'] in ('declared-complete', 'unknown'), 'cost-coverage')
    if costs['coverage'] == 'unknown':
        reasons.append('cost-coverage-unknown')
    known = {}
    for key, value in costs.items():
        if key == 'coverage':
            continue
        if value is None:
            reasons.append('cost-value-unknown')
        else:
            known[key] = atomic(value, 'cost-value-invalid')
    for leg in ('entry', 'exit'):
        total, priority = leg+'NetworkFeeCapLamports', leg+'PriorityIncludedLamports'
        if total in known and priority in known:
            require(known[priority] <= known[total], 'priority-exceeds-total-network-fee')
    valuation = p['nativeValuation']
    rate = None
    if valuation is None:
        reasons.append('native-valuation-unknown')
    else:
        fields(valuation, 'usdcAtomicPerSolUpperBound availableAtMs', 'valuation-schema')
        rate = atomic(valuation['usdcAtomicPerSolUpperBound'], 'valuation-invalid', positive=True)
        available = integer(valuation['availableAtMs'], MAX_CLOCK, 'valuation-time-invalid')
        require(available <= now, 'valuation-from-future')
        if now - available > rate_age:
            reasons.append('native-valuation-stale')
    balance = None
    if p['nativeSpendableLamports'] is None:
        reasons.append('native-spendable-unknown')
    else:
        balance = atomic(p['nativeSpendableLamports'], 'native-spendable-invalid')
    common = dict(inputSha256=digest(p), policySha256=digest(policy), evaluatedAtMs=now,
                  basis='caller-declared-quote-amounts-and-cost-caps',
                  assumptions=[
                      'Reported outputs already include their embedded route fees and price impact; neither is subtracted again.',
                      'Total network fee caps include priority fees; tips and failed-attempt allowance are separate.',
                      'Native valuation is a caller-supplied upper-bound scenario, not a fetched exchange rate.',
                      'Spendable native balance must already exclude other reservations; no wallet-wide check is performed.',
                      'Rent debit is fully reserved and treated as unrecovered in the margin decision.',
                      'Additional exit haircut is an assumed proceeds reduction, not an on-chain minimum-output guarantee.',
                      'Returned quotes are not fills, authenticated routes, guaranteed exits, or future returns.'])
    if reasons:
        return dict(common, state='unavailable', reasons=sorted(set(reasons)))
    fees = known['entryNetworkFeeCapLamports'] + known['exitNetworkFeeCapLamports']
    tips = known['entryTipCapLamports'] + known['exitTipCapLamports']
    failures = known['failedAttemptBudgetLamports']
    rent = known['rentDebitLamports']
    reserve = fees + tips + failures + rent
    require(reserve <= U64, 'native-reserve-overflow')
    native_cost = ceil_div(reserve * rate, LAMPORTS_PER_SOL)
    other_cost = known['otherUsdcDebitAtomic']
    total_cost = native_cost + other_cost
    quoted_exit = amounts[1][1]
    proceeds = quoted_exit * (10000 - haircut) // 10000
    surplus = proceeds - principal - total_cost
    required = principal + total_cost + minimum
    break_even = None if haircut == 10000 else ceil_div(required * 10000, 10000-haircut)
    blockers = []
    if balance < reserve:
        blockers.append('native-reserve-insufficient')
    if surplus < minimum:
        blockers.append('modeled-margin-below-minimum')
    calculation = dict(
        principalUsdcAtomic=str(principal), acquiredAtomic=str(quantity),
        quotedExitUsdcAtomic=str(quoted_exit), quotedChangeUsdcAtomic=str(quoted_exit-principal),
        stressedExitUsdcAtomic=str(proceeds), networkFeeCapsLamports=str(fees),
        separateTipCapsLamports=str(tips), failedAttemptBudgetLamports=str(failures),
        rentDebitLamports=str(rent), nativeReserveLamports=str(reserve),
        nativeReserveShortfallLamports=str(max(0, reserve-balance)),
        nativeCostUsdcAtomicRoundedUp=str(native_cost), otherUsdcDebitAtomic=str(other_cost),
        totalAdditionalCostUsdcAtomic=str(total_cost), modeledSurplusUsdcAtomic=str(surplus),
        minimumSurplusUsdcAtomic=str(minimum),
        requiredQuotedExitUsdcAtomic=None if break_even is None else str(break_even),
        requiredExitWithinU64=break_even is not None and break_even <= U64,
        usdcDecimals=6, nativeDecimals=9)
    return dict(common, state='modeled-constraints-not-met' if blockers else 'modeled-constraints-met',
                reasons=blockers, calculation=calculation)
