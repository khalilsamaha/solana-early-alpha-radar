"""Deterministic unsigned effect checks using synthetic public account fixtures."""
from copy import deepcopy
import base64

import fresh_quote
from unsigned_simulation import review, VERSION, PROGRAM
from preflight_checks import fixture as preflight_fixture, NOW
from swap_rehearsal_fixtures import simulation
from preflight import split_capture
from cpmm_quote import derive
from swap_rehearsal import scope_for


def fixture():
    capture, _ = preflight_fixture(True)
    packet = capture['packet']
    scope = scope_for(packet['policy'])
    price = derive(split_capture(capture)[0], scope, slippage_bps=100, now_ms=NOW)
    packet['policy']['minimumAmountOut'] = price['quote']['minimumOutAmount']
    # Rebuild exact message bytes rather than changing only the declared policy.
    from fresh_packet import message
    import hashlib
    msg = message(scope_for(packet['policy']), packet['policy']['blockhash'])
    packet['unsignedTransactionBase64'] = base64.b64encode(b'\x01'+bytes(64)+msg).decode()
    packet['feeAssertion']['messageSha256'] = hashlib.sha256(msg).hexdigest()
    capture['messageSha256'] = packet['feeAssertion']['messageSha256']
    value = simulation_response(capture, price['quote']['outAmount'])
    value['value']['failed'] = False
    value['value'].pop('err')
    return capture, price, dict(state='received',result=value)


def simulation_response(capture, output):
    # Existing synthetic fixture builds its own pre/post arrays; use the derived
    # output only to supply the deliberately simulated program response.
    simulated = deepcopy(capture)
    simulated['packet']['policy']['minimumAmountOut'] = output
    result = simulation(simulated)
    result['context']['slot'] = capture['evidence']['accounts']['result']['context']['slot']+1
    a = capture['packet']['policy']['accounts']
    bykey = dict(zip(capture['accountKeys'],capture['evidence']['accounts']['result']['value']))
    result['value']['accounts'] += [deepcopy(bykey[k]) for k in (a['config'],PROGRAM,capture['accountKeys'][-1])]
    return result


def run():
    cases = {}
    c,p,item = fixture()
    cases['matching-own-pre-post-effects'] = review(c['packet'],c,p,item,now_ms=NOW)
    mutations = {
        'program-error': lambda x:x['value'].update(failed=True),
        'fee-mismatch': lambda x:x['value'].update(fee=9999),
        'missing-fee': lambda x:x['value'].pop('fee'),
        'missing-native-prestate': lambda x:x['value'].pop('preBalances'),
        'missing-token-prestate': lambda x:x['value'].pop('preTokenBalances'),
        'missing-accounts': lambda x:x['value'].pop('accounts'),
        'context-regression': lambda x:x['context'].update(slot=1),
        'replaced-blockhash': lambda x:x['value'].update(replacementBlockhash='present'),
        'compute-over-cap': lambda x:x['value'].update(unitsConsumed=300001),
        'changed-deployment': lambda x:x['value']['accounts'][7].update(lamports=1),
        'token-identity': lambda x:x['value']['postTokenBalances'][0].update(programId=PROGRAM),
        'duplicate-token': lambda x:x['value']['postTokenBalances'].__setitem__(1,deepcopy(x['value']['postTokenBalances'][0])),
    }
    for name,change in mutations.items():
        c,p,item = fixture(); change(item['result'])
        try:review(c['packet'],c,p,item,now_ms=NOW)
        except (ValueError,KeyError,TypeError,IndexError):cases[name]={'state':'rejected-as-expected'}
        else:raise ValueError('Simulation rejection self-check failed: '+name)
    return dict(format=VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,networkRequests=0,signaturesCreated=0,transactionsSent=0,
        executionApproved=False)
