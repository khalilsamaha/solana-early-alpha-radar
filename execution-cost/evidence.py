"""Read-only exact-message fee/native-balance bridge; never a swap validator.

Raw RPC observations are checked independently of caller cost caps. Quotes,
route semantics, rent, tips, valuation and other reservations remain assertions.
"""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

from contract import (atomic, ceil_div, digest, evaluate, fields, integer, mint,
                      require, Rejected, MAX_CLOCK, U64)

_path = sys.path[:]
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'intent-journal'))
    from wire import decode_wire
finally:
    sys.path[:] = _path

VERSION = 'execution-cost-evidence-1'
ENDPOINTS = {'devnet': 'https://api.devnet.solana.com',
             'mainnet-beta': 'https://api.mainnet-beta.solana.com'}
GENESIS = {'devnet': 'EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG',
           'mainnet-beta': '5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d'}
SYSTEM = '11111111111111111111111111111111'
COMPUTE = 'ComputeBudget111111111111111111111111111111'
MAX_AGE_MS = 10000
MAX_RESPONSE = 65536
NAMES = ('genesisBefore', 'entryFee', 'exitFee', 'wallet', 'genesisAfter')


def unbase58(value):
    alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    n = 0
    for c in value:
        n = n * 58 + alphabet.index(c)
    return bytes(len(value) - len(value.lstrip('1'))) + n.to_bytes((n.bit_length()+7)//8, 'big')


def message_evidence(encoded, wallet):
    try:
        raw, message, keys, signatures, tx = decode_wire(encoded)
        m = tx['transaction']['message']
        require(len(signatures) == 1 and signatures[0] == bytes(64), 'unsigned-single-signer-required')
        require(m['accountKeys'][0] == wallet, 'fee-payer-mismatch')
        require(not m.get('addressTableLookups'), 'lookup-tables-unsupported')
        ix = m['instructions']
        require(len(ix) >= 3, 'explicit-compute-budget-required')
        params = []
        for index, tag, length in ((0, 2, 5), (1, 3, 9)):
            instruction = ix[index]
            program = instruction['programIdIndex']
            require(m['accountKeys'][program] == COMPUTE and not instruction['accounts'] and
                    program >= len(m['accountKeys']) - m['header']['numReadonlyUnsignedAccounts'],
                    'compute-budget-envelope')
            data = unbase58(instruction['data'])
            require(len(data) == length and data[0] == tag, 'compute-budget-instruction')
            params.append(int.from_bytes(data[1:], 'little'))
        require(all(m['accountKeys'][i['programIdIndex']] != COMPUTE for i in ix[2:]),
                'additional-compute-instruction')
        units = integer(params[0], 1400000, 'compute-limit', 1)
        priority = ceil_div(units * params[1], 1000000)
        require(priority <= U64, 'priority-overflow')
        return dict(messageBase64=base64.b64encode(message).decode(),
                    messageSha256=hashlib.sha256(message).hexdigest(),
                    wireSha256=hashlib.sha256(raw).hexdigest(), priorityLamports=str(priority))
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        if isinstance(exc, Rejected):
            raise
        raise Rejected('message-envelope-invalid') from None


def validate_input(p, now):
    fields(p, 'format network wallet scenario entryTransactionBase64 exitTransactionBase64 reservations', 'evidence-input-schema')
    require(p['format'] == VERSION, 'evidence-input-format')
    require(type(p['network']) is str and p['network'] in GENESIS, 'network-unsupported')
    mint(p['wallet'])
    result = evaluate(p['scenario'], now_ms=now)
    require(result['state'] != 'invalid', 'cost-scenario-invalid')
    # These fields must be derived below, not quietly accepted from the caller.
    s = p['scenario']
    require(s['nativeSpendableLamports'] is None and
            all(s['costs'][leg+'PriorityIncludedLamports'] is None for leg in ('entry', 'exit')),
            'derived-fields-must-be-null')
    require(all(s[name]['status'] == 'quoted' for name in ('buy', 'sell')), 'both-quotes-required')
    require(not any(reason.endswith('-quote-stale') for reason in result['reasons']), 'quotes-stale')
    r = p['reservations']
    fields(r, 'otherNativeLamports asOfMs', 'reservation-schema')
    if r['otherNativeLamports'] is None:
        require(r['asOfMs'] is None, 'unknown-reservation-clock')
    else:
        atomic(r['otherNativeLamports'], 'reservation-amount')
        integer(r['asOfMs'], MAX_CLOCK, 'reservation-clock')
        require(0 <= now - r['asOfMs'] <= MAX_AGE_MS, 'reservation-stale-or-future')
    return {leg: message_evidence(p[leg+'TransactionBase64'], p['wallet']) for leg in ('entry', 'exit')}


def request_for(name, p, messages, slot):
    config = dict(commitment='finalized', minContextSlot=slot)
    if name.startswith('genesis'):
        return 'getGenesisHash', []
    if name.endswith('Fee'):
        return 'getFeeForMessage', [messages[name[:-3]]['messageBase64'], config]
    return 'getAccountInfo', [p['wallet'], dict(config, encoding='base64')]


def project(name, result, slot):
    """Validate and retain only bounded evidence needed by the bridge."""
    if name.startswith('genesis'):
        require(type(result) is str and result in GENESIS.values(), 'genesis-invalid')
        return result, slot
    require(type(result) is dict and type(result.get('context')) is dict and 'value' in result,
            'rpc-result-schema')
    current = integer(result['context'].get('slot'), MAX_CLOCK, 'rpc-slot')
    require(current >= slot, 'rpc-slot-regressed')
    value = result['value']
    if name.endswith('Fee'):
        if value is not None:
            integer(value, U64, 'rpc-fee-invalid', 1)
    elif value is not None:
        require(type(value) is dict and value.get('owner') == SYSTEM and
                value.get('executable') is False and value.get('data') == ['', 'base64'] and
                type(value.get('space', 0)) is int and value.get('space', 0) == 0,
                'wallet-must-be-empty-system-account')
        integer(value.get('lamports'), U64, 'wallet-balance-invalid')
        value = dict(owner=SYSTEM, executable=False, data=['', 'base64'], space=0, lamports=value['lamports'])
    return dict(context=dict(slot=current), value=value), current


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def unique(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, 'duplicate-json-key')
        result[k] = v
    return result


def no_constant(_):
    raise Rejected('nonfinite-json')


def rpc(network, method, params, request_id, opener):
    require(network in ENDPOINTS and method in ('getGenesisHash', 'getFeeForMessage', 'getAccountInfo'),
            'rpc-operation-not-allowed')
    request = urllib.request.Request(ENDPOINTS[network], method='POST',
        headers={'Content-Type': 'application/json'}, data=json.dumps(dict(
            jsonrpc='2.0', id=request_id, method=method, params=params), allow_nan=False).encode())
    with opener.open(request, timeout=5) as response:
        raw = response.read(MAX_RESPONSE + 1)
    require(len(raw) <= MAX_RESPONSE, 'rpc-response-size')
    result = json.loads(raw, object_pairs_hook=unique, parse_constant=no_constant)
    require(type(result) is dict and result.get('jsonrpc') == '2.0' and
            type(result.get('id')) is int and result['id'] == request_id and
            set(result) == {'jsonrpc', 'id', 'result'}, 'rpc-envelope-or-error')
    return result['result']


def collect(p, *, opener=None, clock=None):
    clock = clock or (lambda: time.time_ns() // 1000000)
    started = clock()
    messages = validate_input(p, started)  # malformed/signed input makes zero requests
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    capture = dict(format=VERSION, inputSha256=digest(p), startedAtMs=started,
                   observations=[], networkRequests=0, stopReason=None)
    slot = 0
    for name in NAMES:
        requested = clock()
        if not 0 <= requested - started <= MAX_AGE_MS:
            capture['stopReason'] = 'capture-deadline'; break
        method, params = request_for(name, p, messages, slot)
        capture['networkRequests'] += 1
        try:
            raw = rpc(p['network'], method, params, capture['networkRequests'], opener)
            result, slot = project(name, raw, slot)
            require(not name.startswith('genesis') or result == GENESIS[p['network']], 'network-genesis-mismatch')
            capture['observations'].append(dict(name=name, requestSha256=digest([method, params]),
                requestedAtMs=requested, receivedAtMs=clock(), result=result))
            if not name.startswith('genesis') and result['value'] is None:
                capture['stopReason'] = name + '-unavailable'; break
        except (ValueError, OSError, urllib.error.URLError, RecursionError, TypeError):
            # No raw provider text, URLs, message bytes or arbitrary exception text.
            capture['stopReason'] = 'rpc-evidence-unavailable'; break
    capture['finishedAtMs'] = clock()
    return capture


def review(p, capture, *, now_ms):
    report = dict(format='execution-cost-evidence-review-1', state='unavailable', reasons=[],
        economics=None, feeAndNativeEvidence=None, executionApproved=False, signingApproved=False,
        transactionsSent=0, signaturesCreated=0, productionStateChanged=False, modelEvaluated=False,
        quoteMessageSemanticsVerified=False, reservationsVerified=False, principalBalanceVerified=False,
        inputAuthenticityVerified=False,
        limitations=[
            'RPC evidence is provider-reported, not cryptographic proof; replay cannot authenticate its source.',
            'Message hashes bind fee observations, not swap semantics or the quoted route and quantity.',
            'Only native fee funding is checked; USDC principal and acquired token spendability are not checked.',
            'Other reservations, rent, tips, cost completeness and native valuation remain caller assertions.',
            'Sequential finalized reads can use different slots; they are not one atomic snapshot.',
            'Request age and nondecreasing slots do not prove that the RPC node is caught up with the chain.',
            'No signing, reservation creation, simulation, submission, route approval or model evaluation.'])
    try:
        messages = validate_input(p, now_ms)
        fields(capture, 'format inputSha256 startedAtMs observations networkRequests stopReason finishedAtMs', 'capture-schema')
        require(capture['format'] == VERSION and capture['inputSha256'] == digest(p), 'capture-input-mismatch')
        integer(capture['networkRequests'], 5, 'request-count')
        require(type(capture['observations']) is list and len(capture['observations']) <= 5, 'observation-count')
        start = integer(capture['startedAtMs'], MAX_CLOCK, 'capture-clock')
        end = integer(capture['finishedAtMs'], MAX_CLOCK, 'capture-clock')
        require(start <= end <= now_ms and now_ms - start <= MAX_AGE_MS, 'capture-stale-or-future')
        # Replaying later must not admit input evidence that did not yet exist
        # when collection began, even if its clocks are valid at review time.
        validate_input(p, start)
        require(capture['stopReason'] is None and capture['networkRequests'] == 5 and
                len(capture['observations']) == 5, 'capture-incomplete')
        slot, previous, results = 0, start, {}
        for name, row in zip(NAMES, capture['observations']):
            fields(row, 'name requestSha256 requestedAtMs receivedAtMs result', 'observation-schema')
            require(row['name'] == name, 'observation-order')
            begin = integer(row['requestedAtMs'], MAX_CLOCK, 'observation-clock')
            finish = integer(row['receivedAtMs'], MAX_CLOCK, 'observation-clock')
            require(previous <= begin <= finish <= end, 'observation-time-order')
            previous = finish
            method, params = request_for(name, p, messages, slot)
            require(row['requestSha256'] == digest([method, params]), 'observation-request-mismatch')
            results[name], slot = project(name, row['result'], slot)
            if name.startswith('genesis'):
                require(results[name] == GENESIS[p['network']], 'network-genesis-mismatch')
            else:
                require(results[name]['value'] is not None, name + '-unavailable')
        scenario = deepcopy(p['scenario'])
        fee_rows = {}
        for leg in ('entry', 'exit'):
            fee = results[leg+'Fee']['value']
            priority = int(messages[leg]['priorityLamports'])
            require(fee >= priority, 'fee-below-message-priority')
            cap = scenario['costs'][leg+'NetworkFeeCapLamports']
            if cap is not None:
                require(fee <= int(cap), leg + '-fee-exceeds-cap')
            scenario['costs'][leg+'PriorityIncludedLamports'] = str(priority)
            fee_rows[leg] = dict(messageSha256=messages[leg]['messageSha256'],
                wireSha256=messages[leg]['wireSha256'],
                quoteSha256=digest(scenario['buy' if leg == 'entry' else 'sell']),
                totalNetworkFeeLamports=str(fee), priorityIncludedLamports=str(priority))
        balance = results['wallet']['value']['lamports']
        reserve = p['reservations']['otherNativeLamports']
        if reserve is not None:
            require(int(reserve) <= balance, 'other-reservations-exceed-balance')
            scenario['nativeSpendableLamports'] = str(balance - int(reserve))
        report['feeAndNativeEvidence'] = dict(messages=fee_rows, observedNativeLamports=str(balance),
            otherReservedLamports=reserve, scenarioSpendableLamports=scenario['nativeSpendableLamports'],
            evidenceSha256=digest(capture), lastContextSlot=slot)
        report['inputSha256'] = digest(p)
        if p['network'] == 'devnet':
            report.update(state='devnet-fee-evidence-only', reasons=['devnet-has-no-usdc-economic-interpretation'])
        else:
            report['economics'] = evaluate(scenario, now_ms=now_ms)
            report.update(state='fee-and-native-evidence-consistent', reasons=[])
    except Rejected as exc:
        report['reasons'] = [str(exc)]
    except (ValueError, TypeError, KeyError, IndexError, RecursionError):
        report['reasons'] = ['malformed-evidence']
    return report
