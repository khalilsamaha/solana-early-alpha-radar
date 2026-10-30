"""Offline adversarial post-entry fixtures, never a live simulation response."""
import base64
from copy import deepcopy
import hashlib
import post_entry
from paired_checks import leg, edit, derive, message, simulation_response, NOW
from swap_rehearsal import scope_for


def mutate_row(row, offset, data):
    raw = bytearray(base64.b64decode(row['data'][0]))
    raw[offset:offset+len(data)] = data
    row['data'][0] = base64.b64encode(raw).decode()


def fixture(reverse=False, creator=False):
    entry = leg(reverse)
    args = entry['costInputs']
    c = args['capture']; p = args['packet']; a = p['policy']['accounts']
    # A deliberately large synthetic fee makes both fee-sharing counters nonzero.
    for offset, value in ((12,200000),(20,500000),(28,250000)):
        edit(c,1,offset,value.to_bytes(8,'little'))
        edit(entry['initialPool'],1,offset,value.to_bytes(8,'little'))
    edit(c,0,381,(40).to_bytes(8,'little'))
    if creator:
        edit(c,0,390,b'\x01');edit(entry['initialPool'],0,390,b'\x01')
    scope = scope_for(p['policy'])
    price = derive(entry['initialPool'],scope,slippage_bps=100,now_ms=args['now_ms'])
    p['policy']['minimumAmountOut'] = price['quote']['minimumOutAmount']
    msg = message(scope_for(p['policy']),p['policy']['blockhash'])
    p['unsignedTransactionBase64'] = base64.b64encode(b'\x01'+bytes(64)+msg).decode()
    p['feeAssertion']['messageSha256'] = hashlib.sha256(msg).hexdigest()
    c['messageSha256'] = p['feeAssertion']['messageSha256']
    args['price'] = price
    response = simulation_response(c,price['quote']['outAmount'])
    response['value']['failed'] = False;response['value'].pop('err')
    pool = deepcopy(c['evidence']['accounts']['result']['value'][0])
    # Both fixture directions incur exactly 20 atomic trade fee: 10 protocol, 5 fund.
    side = 1 if reverse else 0
    mutate_row(pool,341+8*side,(10).to_bytes(8,'little'))
    mutate_row(pool,357+8*side,(5).to_bytes(8,'little'))
    mutate_row(pool,381,(41).to_bytes(8,'little'))
    response['value']['accounts'].append(pool)
    args['simulation_item'] = dict(state='received',result=response)
    return args,post_entry.parameters(p,c)


def run():
    args,request = fixture()
    result = post_entry.assess(args,request)
    if result['state'] != 'simulated-post-entry-projection-consistent':
        raise ValueError('post-entry-fixture-rejected')
    projection = result['projection']
    if (projection['acquiredInputAtomic'],projection['projectedOutputAtomic'],
        projection['reservesToken0Token1Atomic']) != ('79','63',['10085','9921']):
        raise ValueError('post-entry-fixture-arithmetic')
    cases = {'same-simulation-pool-and-vaults':'passed'}
    mutations = {
        'missing-pool':lambda a,r:a['simulation_item']['result']['value']['accounts'].pop(),
        'request-pool-missing':lambda a,r:r[1]['accounts']['addresses'].pop(),
        'wrong-fee-counter':lambda a,r:mutate_row(a['simulation_item']['result']['value']['accounts'][8],341,(9).to_bytes(8,'little')),
        'changed-immutable-padding':lambda a,r:mutate_row(a['simulation_item']['result']['value']['accounts'][8],636,b'\x01'),
        'epoch-regression':lambda a,r:mutate_row(a['simulation_item']['result']['value']['accounts'][8],381,(39).to_bytes(8,'little')),
        'missing-own-token-prestate':lambda a,r:a['simulation_item']['result']['value'].pop('preTokenBalances'),
        'expired-observation':lambda a,r:a.update(now_ms=NOW+20000),
        'summary-is-not-raw-response':lambda a,r:a.update(simulation_item={'state':'success'}),
    }
    for name,mutate in mutations.items():
        args,request = fixture();mutate(args,request)
        result = post_entry.assess(args,request)
        if result['state'] != 'unavailable' or result['projection'] is not None:
            raise ValueError('post-entry-rejection-fixture')
        cases[name] = 'rejected'
    return dict(format=post_entry.VERSION+'-self-check',state='offline-checks-passed',
        mode='synthetic-offline',casesPassed=len(cases),cases=cases,
        networkRequests=0,signaturesCreated=0,transactionsSent=0,
        liveCollectorVerified=False,executionApproved=False,productionStateChanged=False)
