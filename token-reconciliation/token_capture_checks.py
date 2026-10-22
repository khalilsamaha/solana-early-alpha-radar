"""Synthetic token captures plus existing public chain captures for regression."""
import copy
import json
from pathlib import Path
from recorded_flows import analyze
from recorded_capture import GENESIS
from checks import fixture


def capture(name='existing'):
    p=fixture(name);b=p['bundle'];tx=b['rpcEvidence']['transaction']['result']
    binary=copy.deepcopy(tx);binary['transaction']=[p['signedTransactionBase64'],'base64']
    received=lambda v:{'state':'received','result':v}
    return {'format':'recorded-chain-capture-1','origin':'synthetic-fixture','network':'devnet',
            'selection':'explicit-signature','signature':b['intent']['signature'],
            'startedAtMs':b['capturedAtMs'],'finishedAtMs':b['capturedAtMs']+1,
            'rpcRequestsAttempted':0,'requests':[], 'transactionsSent':0,'ledgerUpdated':False,
            'evidence':{'genesisBefore':received(GENESIS['devnet']),'genesisAfter':received(GENESIS['devnet']),
                        'discovery':{'state':'not-requested'}, 'transactionJson':received(tx),
                        'transactionBase64':received(binary),'signatureStatus':b['rpcEvidence']['signatureStatus']}}


def sync_meta(c):
    c['evidence']['transactionBase64']['result']['meta']=copy.deepcopy(c['evidence']['transactionJson']['result']['meta'])


def self_check():
    cases={name:capture(name) for name in ('existing','create','close','failed','v0','multisigner','wsol-source','wsol-destination')}
    cases['wrong-cluster']=capture();cases['wrong-cluster']['evidence']['genesisAfter']['result']=GENESIS['mainnet-beta']
    cases['missing-transfers']=capture();cases['missing-transfers']['evidence']['transactionJson']['result']['meta']['innerInstructions']=None
    sync_meta(cases['missing-transfers'])
    cases['unexplained-native']=capture();cases['unexplained-native']['evidence']['transactionJson']['result']['meta']['postBalances'][0]-=1
    sync_meta(cases['unexplained-native'])
    expected={n:'recorded-failure-fee-only' if n=='failed' else 'recorded-token-flows-consistent' for n in cases}
    expected.update({'wrong-cluster':'mismatch','missing-transfers':'unknown','unexplained-native':'mismatch'})
    results={n:analyze(c) for n,c in cases.items()}
    if {n:r['state'] for n,r in results.items()}!=expected:raise ValueError('Recorded token self-check failed')
    return {'format':'recorded-token-self-check-1','mode':'synthetic-offline','casesPassed':len(results),
            'cases':results,'currentRunNetworkRequests':0,'transactionsSent':0,'intentProven':False,
            'executionApproved':False,'productionLedgerUpdated':False}
