"""Pure review of a ninth pool account returned by the SAME unsigned entry simulation.

This internal seam has no network adapter or file/report input. It projects a
reverse amount from simulated reserves; it neither builds nor simulates an exit.
"""
from copy import deepcopy
import fresh_quote  # Install the same fixed local module paths as the existing observer.
import cost_readiness
import unsigned_simulation
from core import check
from contract import digest, PROGRAM, U64
from state import account, decode_pool, configuration, u64
from cpmm_quote import calculate, SOURCE_COMMIT

VERSION = 'simulated-post-entry-projection-1'


def parameters(packet, capture):
    """Separate nine-account contract; existing eight-account transport is unchanged."""
    result = deepcopy(unsigned_simulation.parameters(packet, capture))
    result[1]['accounts']['addresses'].append(packet['policy']['accounts']['pool'])
    return result


def assess(cost_inputs, request_parameters):
    """Internal raw-response seam, not evidence authentication or execution approval.

The future collector must bind these exact parameters to its one simulation
response. A caller-supplied request/response pair alone cannot prove that binding.
"""
    result = dict(format=VERSION, state='unavailable', reasons=[], projection=None,
        executionApproved=False, signingApproved=False, actualEntryExecuted=False,
        exitSimulationVerified=False, liveCollectorVerified=False,
        roundTripFundingEstablished=False, sourceEquivalenceVerified=False,
        mainnetSupported=False, netProfit=None,
        networkRequests=0, signaturesCreated=0, transactionsSent=0,
        limitations=[
            'Pure raw-evidence contract; live request/response collection is not integrated.',
            'Returned accounts describe an unsigned simulated entry, not committed chain state.',
            'Reverse arithmetic uses the acquired quantity, not existing wallet inventory.',
            'Recent epoch is only checked for non-regression; no independent epoch attestation.',
            'Oracle account effects and an exit transaction have not been reviewed or simulated.',
            'No complete funding, net-profit, signing, submission or retry authorization.'])
    try:
        result.update(_assess(cost_inputs, request_parameters))
    except (ValueError, KeyError, TypeError, IndexError, OverflowError):
        result['reasons'] = ['post-entry-evidence-rejected']
    return result


def _assess(inputs, request):
    args = deepcopy(inputs)
    packet, capture = args['packet'], args['capture']
    check(digest(request) == digest(parameters(packet, capture)), 'post-entry-request')
    rows = args['simulation_item']['result']['value']['accounts']
    check(type(rows) is list and len(rows) == 9, 'post-entry-returned-accounts')
    post_row = rows.pop()
    # Reuse all original deployment, fee, pre/post balance, quantity, freshness
    # and reservation checks. The original response is not mutated or exported.
    costs = cost_readiness.assess(**args)
    check(costs['state'] == 'single-leg-cost-evidence-consistent', 'post-entry-entry-evidence')
    a = packet['policy']['accounts']
    before = dict(zip(capture['accountKeys'], capture['evidence']['accounts']['result']['value']))
    pre_row = before[a['pool']]
    pre = account(pre_row, PROGRAM, 637)
    post = account(post_row, PROGRAM, 637)
    p, updated = decode_pool(pre_row), decode_pool(post_row)
    check(not p['creatorFeeEnabled'], 'post-entry-creator-fee-unsupported')
    check(pre_row['lamports'] == post_row['lamports'], 'post-entry-pool-lamports')
    side = 0 if a['inputMint'] == p['mint0'] else 1
    rates = configuration(before[a['config']])
    trade_fee = int(args['price']['arithmetic']['tradeFeeAtomic'])
    protocol_fee = trade_fee * rates['protocolShare'] // 1000000
    fund_fee = trade_fee * rates['fundShare'] // 1000000
    expected = bytearray(pre)
    for offset, delta in ((341 + side * 8, protocol_fee), (357 + side * 8, fund_fee)):
        value = u64(pre, offset) + delta
        check(value <= U64, 'post-entry-fee-overflow')
        expected[offset:offset+8] = value.to_bytes(8, 'little')
    # Upstream swap_base_input updates only these fee counters and recent_epoch
    # in PoolState when creator fees are disabled. All other bytes must match.
    check(u64(post, 381) >= u64(pre, 381), 'post-entry-epoch-regression')
    expected[381:389] = post[381:389]
    check(bytes(expected) == post, 'post-entry-pool-transition')
    vaults = {a['inputVault']: rows[3], a['outputVault']: rows[4]}
    # The eight-account review above checked identity, token bytes and deltas.
    from contract import TOKEN
    amounts = [u64(account(vaults[p['vault'+str(i)]], TOKEN, 165), 64) for i in range(2)]
    reserves = [amounts[i] - updated['accruedFees'+str(i)] for i in range(2)]
    check(all(0 < v <= U64 for v in reserves), 'post-entry-effective-reserves')
    acquired = int(costs['calculation']['simulatedOutputAtomic'])
    check(0 < acquired <= 1000 and amounts[1-side] + acquired <= U64, 'post-entry-reverse-cap')
    reverse_side = 1-side
    math = calculate(acquired, reserves[reverse_side], reserves[side], rates['trade'], 0,
                     p['creatorFeeOn'] == 0 or p['creatorFeeOn'] == reverse_side + 1)
    projection = dict(origin='simulated-entry-returned-accounts', pool=a['pool'],
        inputMint=a['outputMint'], outputMint=a['inputMint'],
        acquiredInputAtomic=str(acquired), projectedOutputAtomic=math['outputAtomic'],
        projectedMinimumOutputAtomic=str((int(math['outputAtomic'])*9900+9999)//10000),
        reservesToken0Token1Atomic=[str(v) for v in reserves],
        vaultAmountsToken0Token1Atomic=[str(v) for v in amounts],
        protocolFeeAddedAtomic=str(protocol_fee), fundFeeAddedAtomic=str(fund_fee),
        arithmetic=math, slippageBps=100, validForSubmission=False)
    return dict(state='simulated-post-entry-projection-consistent', reasons=[], projection=projection,
        evidence=dict(requestParametersSha256=digest(request),
            fullSimulationSha256=digest(inputs['simulation_item']),
            prePoolAccountSha256=digest(pre_row), postPoolAccountSha256=digest(post_row),
            projectionSha256=digest(projection),
            messageSha256=costs['evidence']['messageSha256'],
            quoteSha256=costs['evidence']['quoteSha256'],
            baselineSha256=costs['evidence']['baselineSha256'],
            preflightCaptureSha256=costs['evidence']['preflightCaptureSha256'],
            simulationContextSlot=costs['evidence']['simulationContextSlot'],
            evaluatedAtMs=costs['evaluatedAtMs'], sourceReferenceCommit=SOURCE_COMMIT),
        entryFeeEvidence=costs['calculation'])
