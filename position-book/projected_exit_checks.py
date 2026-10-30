"""Synthetic reverse-message checks; no keys, RPC or signed transaction."""
import base64
import projected_exit as m
from post_entry_checks import fixture, NOW


def wire_edit(draft, offset, value):
    raw=bytearray(base64.b64decode(draft['unsignedTransactionBase64']))
    raw[offset:offset+len(value)]=value
    draft['unsignedTransactionBase64']=base64.b64encode(raw).decode()


def run():
    args,request=fixture();draft=m.build(args,request);r=m.assess(args,request,draft)
    if r['state']!='projected-reverse-message-consistent':raise ValueError('exit-self-check')
    cases={'exact-acquired-quantity-and-minimum':'passed'}
    changes={
        'partial-quantity':lambda a,r,d:d['scope'].update(amountIn='1'),
        'weaker-minimum':lambda a,r,d:d['scope'].update(minimumAmountOut='1'),
        'wire-quantity':lambda a,r,d:wire_edit(d,len(base64.b64decode(d['unsignedTransactionBase64']))-16,(1).to_bytes(8,'little')),
        'nonzero-signature':lambda a,r,d:wire_edit(d,1,b'\x01'),
        'different-parent':lambda a,r,d:d.update(parentSimulationSha256='f'*64),
        'copied-entry-fee':lambda a,r,d:d.update(feeAssertion=a['packet']['feeAssertion']),
        'changed-reference-blockhash':lambda a,r,d:d.update(referenceBlockhash=a['packet']['policy']['accounts']['wallet']),
        'expired-parent':lambda a,r,d:a.update(now_ms=NOW+20000),
        'missing-parent-response':lambda a,r,d:a.update(simulation_item={'state':'success'}),
    }
    for name,change in changes.items():
        a,request=fixture();d=m.build(a,request);change(a,request,d)
        r=m.assess(a,request,d)
        if r['state']!='unavailable' or r['binding'] is not None:raise ValueError('exit-rejection-self-check')
        cases[name]='rejected'
    return dict(format=m.VERSION+'-self-check',state='offline-checks-passed',mode='synthetic-offline',
        casesPassed=len(cases),cases=cases,networkRequests=0,signaturesCreated=0,transactionsSent=0,
        exitSimulationVerified=False,exitFeeVerified=False,executionApproved=False,productionStateChanged=False)
