"""One zero-signature devnet simulation; no signer, sender or source journal writes.

The simulation's own pre/post balances are required. Earlier RPC balances are
cross-checks, never substitutes for missing simulation metadata.
"""
import base64
import json

from fresh_quote import ReadTransport
from core import check, context_value
from contract import atomic, decode_wire, digest, validate, PROGRAM, TOKEN, SYSTEM
from recorded_capture import Client, GENESIS
from state import account, token, integer
from program import MAX_BASE64
from cpmm_quote import derive
from preflight import split_capture
from swap_rehearsal import scope_for

VERSION = 'unsigned-controlled-quote-simulation-1'
NAMES = ('wallet', 'source', 'destination', 'inputVault', 'outputVault')


def parameters(packet, capture):
    a = packet['policy']['accounts']
    # Returned read-only config and deployment bytes must still match preflight.
    addresses = [a[n] for n in NAMES] + [a['config'], PROGRAM, capture['accountKeys'][-1]]
    return [packet['unsignedTransactionBase64'], dict(encoding='base64', commitment='finalized',
        sigVerify=False, replaceRecentBlockhash=False, innerInstructions=False,
        minContextSlot=capture['evidence']['accounts']['result']['context']['slot'],
        accounts=dict(encoding='base64', addresses=addresses))]


class Transport(ReadTransport):
    """Only the freshly bound packet may be simulated, once, after 18 reads."""
    METHODS = ReadTransport.METHODS | {'simulateTransaction'}
    REQUEST_CAP = 20

    def arm(self, packet, capture, now_ms):
        check(len(self.calls) == 18 and not hasattr(self, 'expected'), 'simulation-order')
        check(validate(packet, now_ms=now_ms)['state'] == 'instruction-policy-match', 'simulation-packet')
        self.expected = parameters(packet, capture)

    def open(self, request, timeout):
        body = json.loads(request.data)
        if len(self.calls) < 18:
            check(body['method'] in ReadTransport.METHODS, 'simulation-before-binding')
        elif len(self.calls) == 18:
            check(hasattr(self, 'expected') and body['method'] == 'simulateTransaction' and
                  body['params'] == self.expected, 'simulation-request-mismatch')
        else:
            check(len(self.calls) == 19 and body['method'] == 'getGenesisHash' and
                  body['params'] == [], 'simulation-final-cluster-only')
        return super().open(request, timeout)


class SimulationRpc(Client):
    METHODS = ('simulateTransaction', 'getGenesisHash')
    REQUEST_CAP = 2
    ACCOUNT_COUNT = 8

    def __init__(self, opener):
        super().__init__('devnet', opener)

    def request(self, method, params):
        r = super().request(method, params)
        if r['state'] != 'received' or method != 'simulateTransaction': return r
        try:
            slot, v = context_value(r, 0)
            check(type(v) is dict and 'err' in v, 'simulation-shape')
            clean = dict(failed=v['err'] is not None,
                         replacementBlockhash=None if v.get('replacementBlockhash') is None else 'present')
            for name in ('fee', 'unitsConsumed'):
                if name in v:
                    check(integer(v[name]), 'simulation-number'); clean[name] = v[name]
            for name in ('preBalances', 'postBalances'):
                if name in v:
                    check(type(v[name]) is list and len(v[name]) <= 14 and
                          all(integer(n) for n in v[name]), 'simulation-balances')
                    clean[name] = v[name]
            if v.get('accounts') is not None:
                rows = v['accounts']; check(type(rows) is list and len(rows) == self.ACCOUNT_COUNT, 'simulation-accounts')
                clean['accounts'] = []
                for i, row in enumerate(rows):
                    check(type(row) is dict and type(row.get('data')) is list and len(row['data']) == 2 and
                          row['data'][1] == 'base64' and type(row['data'][0]) is str and
                          len(row['data'][0]) <= (MAX_BASE64 if i == 7 else 6000), 'simulation-account-data')
                    clean['accounts'].append({k:row[k] for k in ('owner','executable','lamports','data') if k in row})
            for name in ('preTokenBalances', 'postTokenBalances'):
                if name in v:
                    check(type(v[name]) is list and len(v[name]) <= 4, 'simulation-token-array')
                    clean[name] = []
                    for row in v[name]:
                        check(type(row) is dict and type(row.get('uiTokenAmount')) is dict, 'simulation-token-row')
                        clean[name].append(dict(
                            {k:row[k] for k in ('accountIndex','mint','owner','programId') if k in row},
                            uiTokenAmount={k:row['uiTokenAmount'][k] for k in ('amount','decimals') if k in row['uiTokenAmount']}))
            r['result'] = dict(context=dict(slot=slot), value=clean)
        except (ValueError, KeyError, TypeError, IndexError):
            r = {'state':'invalid-simulation-response'}
            self.calls[-1]['state'] = r['state']
        return r


def review(packet, capture, price, item, *, now_ms):
    """Pointwise quote agreement with the simulation's own atomic balance changes."""
    contract = validate(packet, now_ms=now_ms)
    check(contract['state'] == 'instruction-policy-match', 'simulation-packet')
    check(capture['packet'] == packet, 'simulation-capture-packet')
    slot, v = context_value(item, capture['evidence']['accounts']['result']['context']['slot'])
    check(v.get('failed') is False, 'simulation-failed')
    check(v.get('replacementBlockhash') is None, 'simulation-blockhash-replaced')
    p = packet['policy']; a = p['accounts']; q = price['quote']
    repriced = derive(split_capture(capture)[0], scope_for(p), slippage_bps=100, now_ms=now_ms)
    check(price['economicInputsSha256'] == repriced['economicInputsSha256'] and
          price['arithmetic'] == repriced['arithmetic'] and q['outAmount'] == repriced['quote']['outAmount'] and
          all(q[k] == repriced['quote'][k] for k in ('network','program','pool','wallet','source',
              'destination','inputMint','outputMint')), 'simulation-quote-binding')
    check(q['inAmount'] == p['amountIn'] and q['minimumOutAmount'] == p['minimumAmountOut'], 'simulation-quote-binding')
    fee = atomic(packet['feeAssertion']['lamports'], 'simulation-asserted-fee', positive=True)
    check(integer(v.get('fee'), 1) and v['fee'] == fee <= int(p['maxTotalFeeLamports']), 'simulation-fee')
    check(integer(v.get('unitsConsumed'), 1) and v['unitsConsumed'] <= contract['computeUnits'], 'simulation-compute')
    wire, message, _, signatures, decoded = decode_wire(packet['unsignedTransactionBase64'])
    check(signatures == [bytes(64)], 'simulation-must-be-unsigned')
    keys = decoded['transaction']['message']['accountKeys']
    before, after = v.get('preBalances'), v.get('postBalances')
    check(type(before) is list and type(after) is list and len(before) == len(after) == len(keys) and
          all(integer(x) for x in before+after), 'simulation-native-evidence-missing')
    expected = before.copy(); expected[0] -= fee
    check(expected[0] >= 0 and after == expected, 'simulation-native-deltas')
    bykey = dict(zip(capture['accountKeys'], capture['evidence']['accounts']['result']['value']))
    # Context minimum is a lower bound, not an exact-bank guarantee. Treat drift
    # as unavailable, even if a later quote would produce the same rounded output.
    check(all(before[i] == bykey[k]['lamports'] for i,k in enumerate(keys) if k in bykey),
          'simulation-prestate-changed')
    rows = v.get('accounts')
    check(type(rows) is list and len(rows) == 8, 'simulation-account-evidence-missing')
    account(rows[0], SYSTEM, 0)
    check(rows[0]['lamports'] == after[0], 'simulation-wallet-account')
    for i, k in enumerate((a['config'], PROGRAM, capture['accountKeys'][-1]), 5):
        check(rows[i] == bykey[k], 'simulation-config-or-deployment-changed')

    def indexed(name):
        items = v.get(name)
        check(type(items) is list and len(items) == 4, 'simulation-token-evidence-missing')
        result = {}
        for row in items:
            index = row.get('accountIndex')
            check(integer(index) and index < len(keys) and keys[index] not in result, 'simulation-token-index')
            result[keys[index]] = row
        check(set(result) == {a[n] for n in NAMES[1:]}, 'simulation-token-set')
        return result

    pre, post = indexed('preTokenBalances'), indexed('postTokenBalances')
    deltas = []
    for i, name in enumerate(NAMES[1:]):
        k = a[name]; mint = a['inputMint' if i in (0,2) else 'outputMint']
        owner = a['wallet' if i < 2 else 'authority']
        original, returned = token(bykey[k], mint, owner), token(rows[i+1], mint, owner)
        prior_raw, post_raw = account(bykey[k], TOKEN, 165), account(rows[i+1], TOKEN, 165)
        check(prior_raw[:64]+prior_raw[72:] == post_raw[:64]+post_raw[72:], 'simulation-token-layout-changed')
        check(rows[i+1]['lamports'] == before[keys.index(k)] == after[keys.index(k)], 'simulation-token-rent')
        decimals = base64.b64decode(bykey[mint]['data'][0])[44]
        amounts = []
        for group in (pre, post):
            row = group[k]; u = row['uiTokenAmount']
            check(row.get('mint') == mint and row.get('owner') == owner and row.get('programId') == TOKEN and
                  type(u.get('decimals')) is int and u['decimals'] == decimals, 'simulation-token-identity')
            amounts.append(atomic(u.get('amount'), 'simulation-token-amount'))
        check(amounts[0] == int(original['amount']), 'simulation-prestate-changed')
        check(amounts[1] == int(returned['amount']), 'simulation-post-account-amount')
        deltas.append(amounts[1]-amounts[0])
    output = atomic(q['outAmount'], 'simulation-quote-output', positive=True)
    check(deltas == [-int(p['amountIn']), output, int(p['amountIn']), -output], 'simulation-quote-effects-differ')
    check(output >= int(p['minimumAmountOut']), 'simulation-minimum-output')
    import hashlib
    return dict(state='unsigned-effects-match-quote', simulationSlot=slot,
        messageSha256=hashlib.sha256(message).hexdigest(), unsignedWireSha256=hashlib.sha256(wire).hexdigest(),
        preflightCaptureSha256=digest(capture), quoteSha256=digest(q), evidenceSha256=digest(item),
        feeLamports=str(fee), unitsConsumed=v['unitsConsumed'], inputAtomic=p['amountIn'],
        quotedOutputAtomic=q['outAmount'], simulatedOutputAtomic=str(deltas[1]),
        tokenDeltasAtomic=dict(zip(NAMES[1:], map(str,deltas))), simulationPrestateMatchesCapture=True,
        returnedConfigAndDeploymentMatch=True, signatureVerification=False,
        actualExecutionObserved=False, executionApproved=False, sourceEquivalenceVerified=False)


def collect(packet, capture, price, *, transport, clock, deadline, _evidence_sink=None, _genesis_sink=None):
    start = clock()
    result = dict(state='unavailable', requestedAtMs=start, signatureVerification=False,
                  transactionsSent=0, signaturesCreated=0, executionApproved=False)
    # Only fixed codes are exported; logs, arbitrary provider errors and wire bytes are not.
    try:
        check(start < deadline, 'simulation-evidence-expired')
        transport.arm(packet, capture, start)
        rpc = SimulationRpc(transport)
        item = rpc.request('simulateTransaction', parameters(packet, capture))
        received = clock(); result['receivedAtMs'] = received
        check(start <= received < deadline, 'simulation-evidence-expired')
        check(item['state'] == 'received', 'simulation-rpc-unavailable')
        result.update(review(packet, capture, price, item, now_ms=received))
        # A pass is withheld if the final public cluster check fails.
        genesis = rpc.request('getGenesisHash', [])
        check(genesis.get('state') == 'received' and genesis.get('result') == GENESIS['devnet'], 'simulation-cluster')
        finish = clock(); check(received <= finish < deadline, 'simulation-evidence-expired')
        result['finishedAtMs'] = finish
        if _evidence_sink is not None:
            # Internal in-memory handoff only, never added to the public result.
            from copy import deepcopy
            _evidence_sink(deepcopy(item))
        if _genesis_sink is not None:
            from copy import deepcopy
            _genesis_sink(deepcopy(genesis))
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        allowed = {'simulation-evidence-expired','simulation-rpc-unavailable','simulation-cluster',
            'simulation-failed','simulation-fee','simulation-compute','simulation-prestate-changed',
            'simulation-native-evidence-missing','simulation-token-evidence-missing',
            'simulation-account-evidence-missing','simulation-config-or-deployment-changed',
            'simulation-quote-effects-differ','simulation-native-deltas','simulation-blockhash-replaced',
            'simulation-token-identity','simulation-token-layout-changed','simulation-post-account-amount'}
        result.update(state='unavailable', reason=str(exc) if str(exc) in allowed else 'simulation-evidence-unavailable')
    return result
