"""Small deterministic host report; full adversarial suite is in test_state.py."""
from state import audit, GENESIS, decode
from state_fixtures import fixture,change_row,fake_key


def run():
    cases={
        'pool':(fixture(),'pool-state-consistent'),
        'bound-packet':(fixture(with_packet=True),'policy-state-consistent'),
        'reverse-direction':(fixture(with_packet=True,reverse=True),'policy-state-consistent'),
        'native-vault-read-only':(fixture(native=True),'pool-state-consistent')}
    c=fixture(); c['evidence']['genesisAfter']['result']=GENESIS['mainnet-beta']
    cases['wrong-cluster']=(c,'wrong-cluster')
    cases['wrong-vault-authority']=(change_row(fixture(),4,32,decode(fake_key('attacker'))),'token-mint-or-authority')
    cases['wrong-bump']=(change_row(fixture(),0,328,b'\xfe'),'pool-authority-bump')
    cases['decimals-mismatch']=(change_row(fixture(),2,44,b'\x07'),'pool-mint-decimals')
    cases['frozen-vault']=(change_row(fixture(),4,108,b'\x02'),'token-uninitialized-frozen-or-invalid')
    c=fixture();c['evidence']['accounts']['result']['value'][4]=None
    cases['missing-vault']=(c,'account-unavailable')
    c=fixture();c['evidence']['accounts']['result']['context']['slot']=99
    cases['slot-regression']=(c,'snapshot-slot-regression')
    c=fixture(with_packet=True);c['evidence']['blockhash']['result']['value']=False
    cases['expired-blockhash']=(c,'blockhash-not-valid-at-capture')
    c=fixture(with_packet=True);c['evidence']['fee']['result']['value']=5002
    cases['changed-rpc-fee']=(c,'rpc-message-fee-mismatch')
    cases['insufficient-source']=(change_row(fixture(with_packet=True),9,64,(99).to_bytes(8,'little')),'insufficient-source-balance')
    c=fixture();c=change_row(c,0,329,b'\x04')
    cases['disabled-pool-retained']=(c,'pool-state-consistent')
    results={}
    for name,(capture,expected) in cases.items():
        r=audit(capture)
        if r.get('reason',r['state']) != expected: raise ValueError('State self-check mismatch: '+name)
        if name=='disabled-pool-retained' and 'pool-swaps-disabled' not in r['eligibilityBlockers']:
            raise ValueError('Missing pool blocker')
        results[name]=r
    return {'format':'swap-state-self-check-1','mode':'synthetic-offline','casesPassed':len(results),'cases':results,
            'networkRequests':0,'transactionsSent':0,'signaturesCreated':0,'ledgerUpdated':False,
            'signingApproved':False,'executionApproved':False}
