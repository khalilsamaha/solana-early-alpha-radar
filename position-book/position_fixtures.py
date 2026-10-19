"""Public signed synthetic evidence, never recorded chain fills."""
import copy
import json
from pathlib import Path


def package(name='entry', failed=False, unknown=False):
    p=json.loads(Path(__file__).with_name('public-fixtures.json').read_text())[name]
    if failed:
        tx=p['bundle']['rpcEvidence']['transaction']['result']
        error={'InstructionError':[0,'Custom']}
        tx['meta']['err']=error
        p['bundle']['rpcEvidence']['signatureStatus']['result']['value'][0]['err']=error
        tx['meta']['postTokenBalances']=copy.deepcopy(tx['meta']['preTokenBalances'])
        tx['meta']['innerInstructions']=[]
    if unknown:p['bundle']['rpcEvidence']['transaction']['result']=None
    return p


def registration(p,lid):
    return {'format':'signed-intent-registration-1','logicalIntentId':lid,
            'intent':p['bundle']['intent'],'signedTransactionBase64':p['signedTransactionBase64']}


def policy():
    i=package()['bundle']['intent']
    return {'format':'position-book-policy-1','network':'devnet','wallet':i['wallet'],
        'quoteAccount':i['source']['account'],'quoteMint':i['source']['mint'],'quoteDecimals':6,
        'initialQuoteAtomic':'1000','initialNativeLamports':'10000000',
        'maximumPrincipalAtomic':'100','maximumGrossLossAtomic':'20',
        'maximumTotalFeeLamports':'50000','maximumLegFeeLamports':'10000','maximumIntentAgeMs':15000}


def clock():return package()['bundle']['intent']['preparedAtMs']+10000
