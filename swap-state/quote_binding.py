"""Bind one declared direct devnet quote to raw instruction/account evidence.

Pure review only. Neither quote provenance nor declared reservations are trusted
authoritatively. This module never participates in signing or submission.
"""
from state import audit, PROGRAM
from contract import atomic, digest, fields, key, require, uint, validate, Rejected, U64

VERSION = 'devnet-quote-state-binding-1'
MAX_CLOCK = 2**53 - 1
MAX_AGE_MS = 10000


def review(bundle, *, now_ms):
    result = dict(format=VERSION, state='unavailable', reasons=[], binding=None,
                  networkRequests=0, signaturesCreated=0, transactionsSent=0,
                  signingApproved=False, executionApproved=False, ledgerUpdated=False,
                  quoteAuthenticityVerified=False, reservationsVerified=False,
                  programDeploymentVerified=False, simulationVerified=False,
                  mainnetSupported=False,
                  limitations=[
                      'One declared direct devnet CPMM quote and existing standard SPL accounts only.',
                      'RPC evidence is provider-reported; input clocks and quote provenance are not authenticated.',
                      'Declared reservations are checked arithmetically, not read from an authoritative ledger.',
                      'No price recomputation, economic return, fill guarantee or mainnet route support.',
                      'A recent local capture does not prove the RPC node is caught up.',
                      'No signer, simulation, transaction submission or change to existing journals.'])
    try:
        fields(bundle, {'format', 'quote', 'capture', 'reservations', 'maxSlippageBps'}, 'bundle-schema')
        require(bundle['format'] == VERSION, 'bundle-format')
        now = uint(now_ms, MAX_CLOCK, 'invalid-clock')
        bps = uint(bundle['maxSlippageBps'], 9999, 'invalid-slippage')
        q, c, r = bundle['quote'], bundle['capture'], bundle['reservations']
        fields(q, {'network', 'program', 'pool', 'wallet', 'source', 'destination',
                   'inputMint', 'outputMint', 'inAmount', 'outAmount', 'minimumOutAmount',
                   'requestedAtMs', 'receivedAtMs', 'contextSlot'}, 'quote-schema')
        require(q['network'] == 'devnet' and q['program'] == PROGRAM, 'unsupported-route')
        for name in ('pool', 'wallet', 'source', 'destination', 'inputMint', 'outputMint'):
            key(q[name])
        amounts = {name: atomic(q[name], 'invalid-quote-amount', positive=True)
                   for name in ('inAmount', 'outAmount', 'minimumOutAmount')}
        begin = uint(q['requestedAtMs'], MAX_CLOCK, 'quote-clock')
        end = uint(q['receivedAtMs'], MAX_CLOCK, 'quote-clock')
        quote_slot = uint(q['contextSlot'], MAX_CLOCK, 'quote-slot', minimum=1)
        require(begin <= end <= now and now - begin <= MAX_AGE_MS, 'quote-stale-or-future')
        # Ceil prevents rounding from weakening the declared maximum slippage.
        floor_out = (amounts['outAmount'] * (10000 - bps) + 9999) // 10000
        require(floor_out <= amounts['minimumOutAmount'] <= amounts['outAmount'], 'quote-minimum-outside-bound')
        require(type(c) is dict and c.get('selection') == 'prior-packet', 'prior-packet-required')
        start = uint(c.get('startedAtMs'), MAX_CLOCK, 'capture-clock')
        finish = uint(c.get('finishedAtMs'), MAX_CLOCK, 'capture-clock')
        require(start <= finish <= now and now - start <= MAX_AGE_MS, 'capture-stale-or-future')
        packet = c['packet']
        current = validate(packet, now_ms=now)
        require(current['state'] == 'instruction-policy-match', 'instruction-policy-not-current')
        p, a = packet['policy'], packet['policy']['accounts']
        require(end <= p['issuedAtMs'] <= start, 'quote-policy-capture-order')
        require(all(q[name] == a[name] for name in
                    ('pool', 'wallet', 'source', 'destination', 'inputMint', 'outputMint')), 'quote-account-mismatch')
        require(q['inAmount'] == p['amountIn'] and q['minimumOutAmount'] == p['minimumAmountOut'],
                'quote-instruction-amount-mismatch')
        state = audit(c)  # Recompute from raw bytes, never accept a supplied summary.
        require(state['state'] == 'policy-state-consistent', 'account-or-message-evidence-rejected')
        require(not state['eligibilityBlockers'], 'pool-eligibility-blocked')
        require(all(m['mintAuthority'] is None for m in state['mints']), 'mint-authority-present')
        require(state['snapshotSlot'] >= quote_slot, 'account-state-predates-quote-slot')
        orientation = 0 if a['inputMint'] == state['poolState']['mint0'] else 1
        require(amounts['outAmount'] <= int(state['effectiveReservesAtomic'][1-orientation]),
                'quote-output-exceeds-reserve')
        require(int(state['destinationBalanceAtomic']) + amounts['outAmount'] <= U64,
                'quoted-destination-overflow')
        fields(r, {'wallet', 'source', 'inputMint', 'otherTokenAtomic', 'otherNativeLamports', 'asOfMs'},
               'reservation-schema')
        require(all(r[k] == a[k] for k in ('wallet', 'source', 'inputMint')), 'reservation-account-mismatch')
        require(r['otherTokenAtomic'] is not None and r['otherNativeLamports'] is not None and
                r['asOfMs'] is not None, 'reservation-evidence-unavailable')
        token_reserved = atomic(r['otherTokenAtomic'], 'invalid-token-reservation')
        native_reserved = atomic(r['otherNativeLamports'], 'invalid-native-reservation')
        reserve_at = uint(r['asOfMs'], MAX_CLOCK, 'reservation-clock')
        require(reserve_at <= start and 0 <= now - reserve_at <= MAX_AGE_MS, 'reservation-stale-or-after-capture')
        token_balance = int(state['sourceBalanceAtomic'])
        native_balance = c['evidence']['accounts']['result']['value'][8]['lamports']
        require(token_reserved + amounts['inAmount'] <= token_balance, 'token-funding-shortfall')
        # The fee cap includes priority. No second priority debit is added.
        fee_cap = int(p['maxTotalFeeLamports'])
        require(native_reserved + fee_cap <= native_balance, 'native-funding-shortfall')
        result.update(state='declared-quote-state-consistent', binding=dict(
            inputSha256=digest(bundle), quoteSha256=digest(q), captureSha256=digest(c),
            policySha256=current['policySha256'], messageSha256=current['wireMessageSha256'],
            reservationSha256=digest(r), inputAmountAtomic=q['inAmount'],
            quotedOutputAtomic=q['outAmount'], minimumOutputAtomic=q['minimumOutAmount'],
            slippageFloorAtomic=str(floor_out), tokenSpendableAtomic=str(token_balance-token_reserved),
            nativeSpendableLamports=str(native_balance-native_reserved), totalFeeCapLamports=str(fee_cap),
            rpcMessageFeeLamports=state['rpcMessageFeeLamports'],
            priorityIncludedLamports=current['priorityFeeLamports'],
            accountCreationInstructions=0, newAccountRentDebitLamports='0',
            snapshotSlot=state['snapshotSlot'], quoteContextSlot=quote_slot,
            validUntilExclusiveMs=min(current['validUntilExclusiveMs'], begin+MAX_AGE_MS+1,
                                      start+MAX_AGE_MS+1, reserve_at+MAX_AGE_MS+1)))
    except Rejected as exc:
        result['reasons'] = [str(exc)]
    except (ValueError, TypeError, KeyError, IndexError, RecursionError):
        result['reasons'] = ['malformed-binding-evidence']
    return result
