"""Synthetic unified evidence only; no funded accounts, keys or live baseline override."""
import base64
import copy
from preflight import _review, flags, PROGRAM, GENESIS, digest
from program import audit as program_audit, IDENTITY_FIELDS
from state_fixtures import fixture as state_fixture, fake_key, decode, NOW
from checks import fixture as program_fixture


def fixture(packet=True):
    s=state_fixture(with_packet=packet); p=program_fixture()
    b=program_audit(p)
    baseline=dict(id='synthetic-preflight-baseline',kind='synthetic-test-baseline',network='devnet',
                  observedSlot=100,observedAtMs=NOW-1000,sourceCaptureSha256=b['captureSha256'],
                  identity={k:b[k] for k in IDENTITY_FIELDS})
    ev=copy.deepcopy(s['evidence'])
    ev['programBootstrap']=copy.deepcopy(p['evidence']['bootstrap'])
    ev['poolBootstrap']=ev.pop('bootstrap')
    ev['accounts']['result']['value'].append(copy.deepcopy(p['evidence']['accounts']['result']['value'][1]))
    ev.pop('transaction');ev.pop('discovery')
    for item in ev.values():item['receivedAtMs']=NOW
    c=dict(format='swap-preflight-capture-1',network='devnet',origin='synthetic-offline',
           pool=s['pool'],packet=s['packet'],selection=s['selection'],startedAtMs=NOW-500,finishedAtMs=NOW,
           accountKeys=s['accountKeys']+[b['programDataAddress']],blockTimeSlot=101,messageSha256=s['messageSha256'],
           evidence=ev,requests=[],rpcRequestsAttempted=0,transactionsSent=0,signaturesCreated=0,ledgerUpdated=False)
    return c,baseline


def edit(c,index,offset,value):
    row=c['evidence']['accounts']['result']['value'][index]
    raw=bytearray(base64.b64decode(row['data'][0]));raw[offset:offset+len(value)]=value
    row['data'][0]=base64.b64encode(raw).decode();return c


def run():
    cases={}
    def add(name,c,b,expected,at=NOW):
        r=_review(c,b,at)
        if r.get('reason',r['state'])!=expected:raise ValueError('Preflight self-check failed: '+name)
        cases[name]=r
    c,b=fixture();add('bound-packet',c,b,'preflight-evidence-consistent')
    c,b=fixture(False);add('pool-only',c,b,'pinned-pool-snapshot')
    c,b=fixture();add('changed-payload',edit(c,-1,120,b'\x01'),b,'deployment-differs-from-pinned-observation')
    c,b=fixture();add('changed-authority',edit(c,-1,13,decode(fake_key('other-authority'))),b,'deployment-differs-from-pinned-observation')
    c,b=fixture();add('redeployed',edit(c,-1,4,(100).to_bytes(8,'little')),b,'deployment-differs-from-pinned-observation')
    c,b=fixture();c['accountKeys'][-1]=fake_key('other');add('wrong-batch-binding',c,b,'combined-key-binding')
    c,b=fixture();c['evidence']['accounts']['result']['context']['slot']=99;add('slot-regression',c,b,'snapshot-slot-regression')
    c,b=fixture();add('stale',c,b,'evidence-stale-or-future',NOW+10001)
    c,b=fixture();add('future',c,b,'evidence-stale-or-future',NOW-1)
    c,b=fixture();c['packet']['policy']['expiresAtMs']=NOW+1;add('expired-policy',c,b,'packet-expired-or-invalid-at-review',NOW+1)
    c,b=fixture();c['evidence']['fee']['result']['value']=5002;add('changed-fee',c,b,'pool-check-rpc-message-fee-mismatch')
    c,b=fixture();c['evidence']['blockhash']['result']['value']=False;add('expired-blockhash',c,b,'pool-check-blockhash-not-valid-at-capture')
    c,b=fixture();add('insufficient-source',edit(c,9,64,(99).to_bytes(8,'little')),b,'pool-check-insufficient-source-balance')
    c,b=fixture();add('disabled-pool',edit(c,0,329,b'\x04'),b,'pool-eligibility-blocked')
    c,b=fixture();c['evidence']['genesisAfter']['result']=GENESIS['mainnet-beta'];add('wrong-cluster',c,b,'pool-check-wrong-cluster')
    return dict(format='swap-preflight-self-check-1',mode='synthetic-offline',syntheticBaselineUsed=True,
                casesPassed=len(cases),cases=cases,networkRequests=0,**flags())
