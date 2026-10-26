"""Synthetic inputs only. These values are not trading policy recommendations."""
from copy import deepcopy
from contract import VERSION, USDC


def fixture():
    token = 'So11111111111111111111111111111111111111112'
    return dict(format=VERSION,
        policy=dict(maxQuoteAgeMs=5000, maxValuationAgeMs=30000,
                    additionalExitHaircutBps=100, minimumSurplusUsdcAtomic='0'),
        buy=dict(status='quoted', inputMint=USDC, outputMint=token,
                 inAmount='10000000', outAmount='50000', requestedAtMs=99000, receivedAtMs=99200),
        sell=dict(status='quoted', inputMint=token, outputMint=USDC,
                  inAmount='50000', outAmount='10200000', requestedAtMs=99300, receivedAtMs=99500),
        costs=dict(coverage='declared-complete', entryNetworkFeeCapLamports='10000',
                   exitNetworkFeeCapLamports='10000', entryPriorityIncludedLamports='5000',
                   exitPriorityIncludedLamports='5000', entryTipCapLamports='0', exitTipCapLamports='0',
                   failedAttemptBudgetLamports='10000', rentDebitLamports='0', otherUsdcDebitAtomic='0'),
        nativeValuation=dict(usdcAtomicPerSolUpperBound='200000000', availableAtMs=98000),
        nativeSpendableLamports='10000000')


def scenarios():
    base = fixture()
    rent = deepcopy(base); rent['costs']['rentDebitLamports'] = '2000000'
    missing = deepcopy(base); missing['costs']['exitTipCapLamports'] = None
    unavailable = deepcopy(base); unavailable['sell'].update(status='unavailable', outAmount=None)
    reserve = deepcopy(base); reserve['nativeSpendableLamports'] = '100'
    return [('positive-under-declared-assumptions', base), ('rent-erases-positive-quote', rent),
            ('unknown-cost', missing), ('no-returned-exit-quote', unavailable),
            ('native-reserve-shortfall', reserve)]
