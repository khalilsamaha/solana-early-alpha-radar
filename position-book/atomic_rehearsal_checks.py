"""Portable synthetic ordered-message and CPI trace cases; no live evidence."""
import base64
from copy import deepcopy
import atomic_rehearsal as m
from contract import TOKEN, b58, decode_wire
from post_entry_checks import fixture as parent_fixture, NOW
from projected_exit_checks import wire_edit


def fixture(reverse=False):
    a, p = parent_fixture(reverse)
    d = m.build(a, p); b = m.assess(a, p, d)['binding']
    _, _, _, _, tx = decode_wire(d['unsignedTransactionBase64'])
    keys = tx['transaction']['message']['accountKeys']
    bykey = dict(zip(a['capture']['accountKeys'], a['capture']['evidence']['accounts']['result']['value']))
    groups = []
    for index, scope, output in ((2, d['entryScope'], b['acquiredAtomic']),
                                 (3, d['exitScope'], b['projectedFinalOutputAtomic'])):
        s = scope['accounts']; instructions = []
        for src, mint, dst, auth, amount in (
            (s['source'], s['inputMint'], s['inputVault'], s['wallet'], scope['amountIn']),
            (s['outputVault'], s['outputMint'], s['destination'], s['authority'], output)):
            decimals = base64.b64decode(bykey[mint]['data'][0])[44]
            instructions.append(dict(programIdIndex=keys.index(TOKEN),
                accounts=[keys.index(k) for k in (src, mint, dst, auth)], stackHeight=2,
                data=b58(b'\x0c'+int(amount).to_bytes(8, 'little')+bytes([decimals]))))
        groups.append(dict(index=index, instructions=instructions))
    return a, p, d, groups


def trace_quantity(ix, amount):
    raw = bytearray(m.decode(ix['data'])); raw[1:9] = amount.to_bytes(8, 'little')
    ix['data'] = b58(raw)


def run():
    a, p, d, g = fixture()
    if m.assess(a, p, d)['state'] != 'atomic-draft-consistent': raise ValueError('atomic-draft-self-check')
    if m.assess_trace(a, p, d, g)['state'] != 'atomic-transfer-trace-consistent': raise ValueError('atomic-trace-self-check')
    cases = {'ordered-entry-exit-message': 'passed', 'four-transfers-zero-acquired-residual': 'passed'}
    draft_changes = {
        'partial-reverse-quantity': lambda a,p,d: d['exitScope'].update(amountIn='1'),
        'weaker-exit-minimum': lambda a,p,d: d['exitScope'].update(minimumAmountOut='1'),
        'wire-quantity-mismatch': lambda a,p,d: wire_edit(d, len(base64.b64decode(d['unsignedTransactionBase64']))-16, (1).to_bytes(8,'little')),
        'nonzero-signature': lambda a,p,d: wire_edit(d, 1, b'\x01'),
        'borrowed-entry-fee': lambda a,p,d: d.update(feeAssertion=a['packet']['feeAssertion']),
        'different-parent': lambda a,p,d: d.update(parentSimulationSha256='f'*64),
        'expired-parent': lambda a,p,d: a.update(now_ms=NOW+20000),
        'public-summary-is-not-parent': lambda a,p,d: a.update(simulation_item={'state':'success'}),
    }
    for name, change in draft_changes.items():
        a,p,d,g = fixture(); change(a,p,d)
        r = m.assess(a,p,d)
        if r['state'] != 'unavailable' or r['binding'] is not None: raise ValueError('atomic-draft-rejection')
        cases[name] = 'rejected'
    trace_changes = {
        'missing-entry-trace': lambda g: g.pop(0),
        'reordered-legs': lambda g: g.reverse(),
        'inventory-masks-entry-shortfall': lambda g: trace_quantity(g[0]['instructions'][1], 78),
        'partial-exit-leaves-residual': lambda g: trace_quantity(g[1]['instructions'][0], 78),
        'unexpected-cpi': lambda g: g[1]['instructions'].append(deepcopy(g[1]['instructions'][0])),
        'wrong-transfer-authority': lambda g: g[1]['instructions'][0]['accounts'].__setitem__(3, 1),
        'missing-stack-depth': lambda g: g[0]['instructions'][0].pop('stackHeight'),
        'oversized-trace-data': lambda g: g[0]['instructions'][0].update(data='1'*1000),
    }
    for name, change in trace_changes.items():
        a,p,d,g = fixture(); change(g)
        r = m.assess_trace(a,p,d,g)
        if r['state'] != 'unavailable' or r['trace'] is not None: raise ValueError('atomic-trace-rejection-'+name)
        cases[name] = 'rejected'
    return dict(format=m.VERSION+'-self-check', state='offline-checks-passed', mode='synthetic-offline',
        casesPassed=len(cases), cases=cases, networkRequests=0, signaturesCreated=0, transactionsSent=0,
        executionApproved=False, simulationVerified=False, productionStateChanged=False,
        note='Ordered message and trace contract only; live combined simulation and final-state reconciliation are pending.')
