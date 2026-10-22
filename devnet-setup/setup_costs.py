"""Read-only controlled standard-SPL pair/pool cost inventory, not a setup authorization."""
import time
from fresh_packet import ROOT, Client, GENESIS, key, check, uint, U64, context_value
from preflight import audit, BASELINE
from preflight_capture import collect
from state import account, configuration, PROGRAM, SYSTEM, u64

# Two new test mints/holder accounts, then LP mint, two vaults, LP holder, pool and oracle.
# Existing AmmConfig is reused. No WSOL principal or Token-2022 accounts are in this plan.
SIZES = (82, 165, 637, 4075)
TRANSACTION_FEE_RESERVE = 100000  # planning allowance, not an RPC fee quote or execution cap


class CostRpc(Client):
    METHODS = ('getGenesisHash', 'getMultipleAccounts', 'getMinimumBalanceForRentExemption')
    REQUEST_CAP = 7
    def __init__(self, opener=None): super().__init__('devnet', opener)


def review(capture, wallet, evidence, *, pool_reviewer=audit):
    result = dict(format='devnet-setup-cost-review-1', state='unavailable', network='devnet', wallet=wallet,
                  transactionsSent=0, signaturesCreated=0, walletKeyRead=False, executionApproved=False,
                  provisioningImplemented=False, setupReady=False)
    try:
        key(wallet)
        p = pool_reviewer(capture, now_ms=capture['finishedAtMs'])
        check(p['state'] == 'pinned-pool-snapshot', 'pinned-pool-required')
        # No substitution of an unrelated config: use the validated pool's exact batch.
        row = capture['evidence']['accounts']['result']['value'][1]
        configuration(row); raw = account(row, PROGRAM, 236)
        enabled = raw[9] == 0; creation_fee = u64(raw, 36)
        for name in ('genesisBefore', 'genesisAfter'):
            check(evidence[name]['state'] == 'received' and evidence[name]['result'] == GENESIS['devnet'], 'cost-cluster')
        slot, rows = context_value(evidence['wallet'], p['snapshotSlot'])
        check(type(rows) is list and len(rows) == 1, 'wallet-shape')
        balance = 0
        if rows[0] is not None:
            account(rows[0], SYSTEM, 0); balance = rows[0]['lamports']
        rent = {}
        for size in SIZES:
            item = evidence['rent' + str(size)]
            check(item['state'] == 'received', 'rent-unavailable')
            rent[size] = uint(item['result'], U64, 'rent-invalid', minimum=1)
        pair = 2 * rent[82] + 2 * rent[165]
        pool = rent[82] + 3 * rent[165] + rent[637] + rent[4075]
        total = pair + pool + creation_fee + TRANSACTION_FEE_RESERVE
        check(total <= U64, 'cost-overflow')
        result.update(state='costs-observed', config=p['poolReview']['poolState']['config'],
            referencePool=p['poolReview']['pool'], snapshotSlot=p['snapshotSlot'], walletSlot=slot,
            poolCreationEnabled=enabled, walletLamports=str(balance),
            rentByAccountBytes={str(k): str(v) for k, v in rent.items()},
            newTestPairRentLamports=str(pair), newPoolRentLamports=str(pool),
            configCreationFeeLamports=str(creation_fee), transactionFeeReserveLamports=str(TRANSACTION_FEE_RESERVE),
            estimatedTotalLamports=str(total), estimatedShortfallLamports=str(max(0, total-balance)),
            balanceCoversEstimate=balance >= total,
            blockers=['controlled-token-and-pool-provisioner-not-yet-implemented'] +
                     ([] if enabled else ['config-disables-new-pools']) +
                     ([] if balance >= total else ['insufficient-devnet-lamports-for-estimate']),
            limitations=['Estimate for new standard SPL test tokens, not acquisition of the reference pool tokens.',
                         'Rent and config fee are observations; transaction fee reserve is a planning allowance.',
                         'No keys generated, tokens minted, pool created, airdrop requested or transaction submitted.',
                         'Observed deployment pin is not a proof that source code matches the binary.',
                         'Recheck fee, rent, config, accounts and balance before any future setup transaction.'])
    except (ValueError, TypeError, KeyError, IndexError):
        result.update(state='unavailable', reason='cost-evidence-incomplete-or-unsupported')
    return result


def _collect_costs(pool, wallet, *, opener=None, collector=collect, pool_reviewer=audit):
    key(pool); key(wallet)
    capture = collector(pool=pool, opener=opener)
    p = pool_reviewer(capture, now_ms=capture['finishedAtMs'])
    check(p['state'] == 'pinned-pool-snapshot', 'pinned-pool-required')
    rpc = CostRpc(opener); evidence = {}
    try:
        evidence['genesisBefore'] = rpc.request('getGenesisHash', [])
        check(evidence['genesisBefore'].get('state') == 'received' and
              evidence['genesisBefore'].get('result') == GENESIS['devnet'], 'cost-cluster')
        item = rpc.request('getMultipleAccounts', [[wallet], {'encoding':'base64', 'commitment':'finalized',
                                                           'minContextSlot':p['snapshotSlot']}])
        slot, rows = context_value(item, p['snapshotSlot'])
        check(type(rows) is list and len(rows) == 1, 'wallet-shape')
        if rows[0] is not None:
            account(rows[0], SYSTEM, 0)
            rows = [{k: rows[0][k] for k in ('data','owner','lamports','executable')}]
        evidence['wallet'] = dict(state='received', result=dict(context={'slot':slot}, value=rows))
        for size in SIZES:
            item = rpc.request('getMinimumBalanceForRentExemption', [size, {'commitment':'finalized'}])
            check(item.get('state') == 'received', 'rent-unavailable')
            uint(item.get('result'), U64, 'rent-invalid', minimum=1)
            evidence['rent' + str(size)] = item
        evidence['genesisAfter'] = rpc.request('getGenesisHash', [])
    except (ValueError, TypeError, KeyError, IndexError): pass
    return dict(format='devnet-setup-costs-1', capturedAtMs=time.time_ns()//1000000,
                sourcePoolCapture=capture, evidence=evidence,
                review=review(capture, wallet, evidence, pool_reviewer=pool_reviewer), requests=rpc.calls,
                networkRequests=len(rpc.calls) + capture.get('rpcRequestsAttempted', 0),
                transactionsSent=0, signaturesCreated=0)


def collect_costs(pool, wallet, *, opener=None):
    return _collect_costs(pool, wallet, opener=opener)
