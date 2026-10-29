"""Deterministic unsigned devnet fixtures. No live evidence or signing material."""
from quote_binding import review, VERSION, PROGRAM
from state_fixtures import fixture, NOW


def bundle(reverse=False):
    c = fixture(with_packet=True, reverse=reverse)
    p = c['packet']['policy']; a = p['accounts']
    q = {k: a[k] for k in ('pool', 'wallet', 'source', 'destination', 'inputMint', 'outputMint')}
    q.update(network='devnet', program=PROGRAM, inAmount='100', outAmount='200', minimumOutAmount='190',
             requestedAtMs=NOW-1500, receivedAtMs=NOW-1200, contextSlot=100)
    return dict(format=VERSION, quote=q, capture=c, maxSlippageBps=500,
                reservations=dict(wallet=a['wallet'], source=a['source'], inputMint=a['inputMint'],
                                  otherTokenAtomic='900', otherNativeLamports='94000', asOfMs=NOW-500))



def run():
    cases = {}
    for reverse in (False, True):
        cases['reverse' if reverse else 'forward'] = (bundle(reverse), 'declared-quote-state-consistent')
    b = bundle(); b['quote']['outAmount'] = '201'
    cases['slippage-rounding'] = (b, 'quote-minimum-outside-bound')
    b = bundle(); b['reservations']['otherTokenAtomic'] = '901'
    cases['reserved-token-shortfall'] = (b, 'token-funding-shortfall')
    b = bundle(); b['reservations']['otherNativeLamports'] = '94001'
    cases['reserved-native-shortfall'] = (b, 'native-funding-shortfall')
    b = bundle(); b['reservations']['otherTokenAtomic'] = None
    cases['unknown-reservation'] = (b, 'reservation-evidence-unavailable')
    b = bundle(); b['quote']['requestedAtMs'] = NOW-10001
    cases['stale-quote'] = (b, 'quote-stale-or-future')
    b = bundle(); b['quote']['network'] = 'mainnet-beta'
    cases['mainnet-blocked'] = (b, 'unsupported-route')
    checked = {}
    for name, (value, expected) in cases.items():
        r = review(value, now_ms=NOW)
        actual = r['reasons'][0] if r['reasons'] else r['state']
        if actual != expected:
            raise ValueError('Quote binding self-check mismatch')
        checked[name] = r
    return dict(format='devnet-quote-binding-self-check-1', mode='synthetic-offline',
                casesPassed=len(checked), cases=checked, networkRequests=0, signaturesCreated=0,
                transactionsSent=0, executionApproved=False, signingApproved=False, ledgerUpdated=False)
