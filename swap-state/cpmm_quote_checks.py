"""Small deterministic host arithmetic checks; no RPC or local wallet state."""
from cpmm_quote import calculate, VERSION


def run():
    # Independently worked integer examples: net input=997; 997*10000/10997=906.
    vectors = [
        ('standard-fee', (1000,10000,10000,2500,0,True), ('906','3','0','3')),
        ('creator-input', (1000,10000,10000,2500,1500,True), ('905','4','1','3')),
        ('creator-output', (1000,10000,10000,2500,1500,False), ('904','3','2','3')),
        ('small-rounding', (101,10000,10000,2500,0,True), ('99','1','0','1')),
        ('no-fee-output-mode', (1000,10000,10000,0,0,False), ('909','0','0','0')),
    ]
    cases = {}
    for name, args, expected in vectors:
        r = calculate(*args)
        if tuple(r[k] for k in ('outputAtomic','inputFeeAtomic','creatorFeeAtomic','tradeFeeAtomic')) != expected:
            raise ValueError('Curve self-check mismatch')
        cases[name] = r
    rejected = [
        ('fee-consumes-input', (1,10000,10000,2500,0,True)),
        ('empty-output', (2,10000,1,2500,0,True)),
        ('combined-fee-limit', (1000,10000,10000,900000,100000,True)),
        ('invalid-bool-amount', (True,10000,10000,2500,0,True)),
        ('empty-reserve', (1000,0,10000,2500,0,True)),
        ('zero-fee-input-split', (1000,10000,10000,0,0,True)),
    ]
    for name, args in rejected:
        try: calculate(*args)
        except ValueError: cases[name] = {'state':'rejected-as-expected'}
        else: raise ValueError('Curve rejection self-check mismatch')
    return dict(format=VERSION+'-self-check', state='offline-checks-passed',
        mode='synthetic-offline', casesPassed=len(cases), cases=cases,
        networkRequests=0, signaturesCreated=0, transactionsSent=0, executionApproved=False)
