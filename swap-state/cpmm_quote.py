"""Integer exact-input research quotes from raw standard-SPL CPMM evidence.

Formula reference: raydium-cp-swap f4b9b26342afe9122d5ff67cd7a4f19ded4ac0a5.
This is a local calculation, not proof of deployed-source equivalence or a fill.
"""
from state import audit, PROGRAM
from contract import atomic, digest, require, uint, U64, NATIVE

VERSION = 'local-cpmm-exact-input-1'
SOURCE_COMMIT = 'f4b9b26342afe9122d5ff67cd7a4f19ded4ac0a5'
DENOMINATOR = 1000000


def calculate(amount, reserve_in, reserve_out, trade_rate, creator_rate, creator_on_input):
    """Mirror swap_base_input/Fees rounding; protocol/fund fees split trade fees."""
    for value in (amount, reserve_in, reserve_out):
        uint(value, U64, 'curve-amount', minimum=1)
    for value in (trade_rate, creator_rate):
        uint(value, DENOMINATOR-1, 'curve-rate')
    require(type(creator_on_input) is bool, 'curve-fee-side')
    combined = trade_rate + creator_rate if creator_on_input else trade_rate
    require(combined < DENOMINATOR, 'combined-fee-rate')
    # The upstream input-side fee split divides by the combined rate.
    require(not creator_on_input or combined > 0, 'zero-input-fee-denominator')
    input_fee = (amount * combined + DENOMINATOR-1) // DENOMINATOR
    net = amount - input_fee
    require(net > 0, 'input-consumed-by-fee')
    raw_out = net * reserve_out // (reserve_in + net)
    creator_fee = (input_fee * creator_rate // combined if creator_on_input else
                   (raw_out * creator_rate + DENOMINATOR-1) // DENOMINATOR)
    out = raw_out if creator_on_input else raw_out - creator_fee
    require(0 < out < reserve_out, 'empty-or-invalid-output')
    return dict(outputAtomic=str(out), inputFeeAtomic=str(input_fee),
                creatorFeeAtomic=str(creator_fee),
                tradeFeeAtomic=str(input_fee-creator_fee if creator_on_input else input_fee),
                curveOutputBeforeOutputFeeAtomic=str(raw_out))


def derive(capture, scope, *, slippage_bps, now_ms):
    """Re-read raw bytes. Caller reviews the combined pinned-program capture too."""
    uint(now_ms, 2**53-1, 'quote-clock')
    uint(slippage_bps, 100, 'quote-slippage-cap')
    start, end = capture['startedAtMs'], capture['finishedAtMs']
    for at in (start, end): uint(at, 2**53-1, 'quote-clock')
    require(start <= end <= now_ms and now_ms-start <= 10000, 'quote-read-stale-or-future')
    require(scope['network'] == 'devnet', 'quote-network')
    s = audit(capture)
    require(s['state'] in ('pool-state-consistent', 'policy-state-consistent'), 'quote-pool-rejected')
    require(not s['eligibilityBlockers'], 'quote-pool-ineligible')
    require(all(m['mintAuthority'] is None for m in s['mints']), 'quote-mint-authority')
    a, p = scope['accounts'], s['poolState']
    require(capture['pool'] == a['pool'], 'quote-pool-scope')
    require(a['inputMint'] in (p['mint0'], p['mint1']), 'quote-input-mint')
    side = 0 if a['inputMint'] == p['mint0'] else 1
    require(a['outputMint'] == p['mint'+str(1-side)] and
            a['inputVault'] == p['vault'+str(side)] and
            a['outputVault'] == p['vault'+str(1-side)] and
            a['config'] == p['config'] and a['observation'] == p['observation'] and
            a['authority'] == s['authority'], 'quote-pool-roles')
    require(NATIVE not in (a['inputMint'], a['outputMint']), 'native-route-unsupported')
    amount = atomic(scope['amountIn'], 'quote-amount', positive=True)
    require(amount <= 1000, 'quote-input-cap')
    require(int(s['vaults'][side]['amount']) + amount <= U64, 'input-vault-overflow')
    rates = s['configRatesMillionths']
    creator = rates['creator'] if p['creatorFeeEnabled'] else 0
    on_input = p['creatorFeeOn'] == 0 or p['creatorFeeOn'] == side+1
    reserves = [int(x) for x in s['effectiveReservesAtomic']]
    math = calculate(amount, reserves[side], reserves[1-side], rates['trade'], creator, on_input)
    minimum = (int(math['outputAtomic']) * (10000-slippage_bps)+9999)//10000
    # Keep all fee settings in the fingerprint, including the shares. No pool
    # change is silently accepted just because integer output happens to match.
    inputs = dict(pool=a['pool'], inputMint=a['inputMint'], outputMint=a['outputMint'],
        reserves=s['effectiveReservesAtomic'], rates=rates, creatorEnabled=p['creatorFeeEnabled'],
        creatorFeeOn=p['creatorFeeOn'], amountIn=str(amount))
    q = {k:a[k] for k in ('pool','wallet','source','destination','inputMint','outputMint')}
    q.update(network='devnet', program=PROGRAM, inAmount=str(amount), outAmount=math['outputAtomic'],
             minimumOutAmount=str(minimum), requestedAtMs=start, receivedAtMs=end, contextSlot=s['snapshotSlot'])
    return dict(format=VERSION, quote=q, arithmetic=math, economicInputs=inputs,
                economicInputsSha256=digest(inputs), rawCaptureSha256=digest(capture),
                sourceReferenceCommit=SOURCE_COMMIT, sourceEquivalenceVerified=False,
                slippageBps=slippage_bps, executionApproved=False)
