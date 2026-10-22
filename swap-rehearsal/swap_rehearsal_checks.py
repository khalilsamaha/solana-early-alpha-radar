"""Host exercise with disposable unfunded keys and synthetic transport only."""
import copy
from pathlib import Path
import tempfile
from swap_rehearsal import _prepare, report, CHILD, FLAGS
from core import initialize
from swap_rehearsal_fixtures import scenario,Transport,dependencies


def run():
    cases={}
    for name in ('valid','simulation-failure','wrong-fee','wrong-native-delta','wrong-token-output',
                 'replaced-blockhash','stale-preflight','scope-mismatch','stop-marker','wrong-wallet'):
        with tempfile.TemporaryDirectory(prefix='radar-swap-self-check-') as tmp:
            home=Path(tmp)/'wallet';wallet=initialize(home)['wallet'];c,b,scope=scenario(wallet)
            change=None
            if name=='simulation-failure':change=lambda r:r['value'].update(err={'InstructionError':[2,'Custom']})
            if name=='wrong-fee':change=lambda r:r['value'].update(fee=6001)
            if name=='wrong-native-delta':change=lambda r:r['value']['postBalances'].__setitem__(1,1)
            if name=='wrong-token-output':change=lambda r:r['value']['postTokenBalances'][1]['uiTokenAmount'].update(amount='0')
            if name=='replaced-blockhash':change=lambda r:r['value'].update(replacementBlockhash={'blockhash':'unexpected'})
            if name=='stale-preflight':c['evidence']['accounts']['receivedAtMs']-=11000
            if name=='scope-mismatch':scope['amountIn']='101'
            if name=='stop-marker':(home/'STOP').touch()
            expected_wallet=wallet if name!='wrong-wallet' else c['pool']
            transport=Transport(c,change)
            try:r=_prepare(home,expected_wallet,scope,c['packet'],opener=transport,**dependencies(c,b));state=r['state']
            except ValueError:state='blocked-before-plan'
            expected='signed-simulation-consistent' if name=='valid' else 'blocked-before-plan' if name in ('scope-mismatch','stop-marker','wrong-wallet') else 'preparation-incomplete'
            if state!=expected:raise ValueError('Self-check state mismatch: '+name)
            cases[name]={'state':state,'syntheticRequests':len(transport.calls),'transactionSent':False}
            if name=='valid':
                again=_prepare(home,wallet,scope,c['packet'],opener=transport,**dependencies(c,b))
                if again['networkRequests']!=0 or again['signaturesCreatedThisRun']!=0:raise ValueError('Duplicate guard failed')
                cases['repeat-no-resign']={'state':again['state'],'networkRequests':0,'newSignatures':0}
                if report(home)['state']!=expected:raise ValueError('Status failed')
                cases['durable-status']={'state':expected,'networkRequests':0}
    return dict(format='devnet-swap-rehearsal-self-check-1',mode='synthetic-offline',casesPassed=len(cases),cases=cases,
                ephemeralKeysGenerated=True,ephemeralSignaturesCreated=True,realWalletAccessed=False,
                publicRpcRequests=0,syntheticBaselineUsed=True,**FLAGS)
