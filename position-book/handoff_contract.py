"""Bounded signer request and receipt-intent template from admitted raw accounts.

No key access or signer implementation. These private objects are not public
execution permits, imported reports or an independent spendable balance.
"""
from copy import deepcopy
from contract import digest, TOKEN
from core import check
from state import token, mint
from wire import parse
from reconcile import validate_intent

VERSION='entry-handoff-1'


def request(evidence, policy, reservation):
    packet=evidence['costInputs']['packet'];capture=evidence['costInputs']['capture']
    roles=policy['scope']['accounts']
    rows=dict(zip(capture['accountKeys'],capture['evidence']['accounts']['result']['value']))
    def account(side, mint_role):
        t=token(rows[roles[side]],roles[mint_role],roles['wallet'])
        m=mint(rows[roles[mint_role]])
        return dict(account=roles[side],mint=roles[mint_role],programId=TOKEN,
                    decimals=m['decimals'],preAmountAtomic=t['amount'],lifecycle='existing')
    template=dict(format='transaction-intent-1',network='devnet',wallet=roles['wallet'],
        messageSha256=parse(packet['unsignedTransactionBase64'])[5],
        preparedAtMs=packet['policy']['issuedAtMs'],walletPreLamports=str(rows[roles['wallet']]['lamports']),
        source=account('source','inputMint'),destination=account('destination','outputMint'),
        inputAtomic=policy['scope']['amountIn'],minimumOutputAtomic=policy['scope']['minimumAmountOut'],
        maximumFeeLamports=reservation['entryFeeCapLamports'],maximumRentLamports='0')
    return dict(format=VERSION+'-sign-request',network='devnet',
        policySha256=reservation['policySha256'],evidenceSha256=reservation['evidenceSha256'],
        messageSha256=reservation['messageSha256'],validUntilExclusiveMs=reservation['validUntilExclusiveMs'],
        packet=deepcopy(packet),receiptIntentTemplate=template)


def accounting(state):
    req=state['signingRequest']
    check(digest(req)==state['signingRequestSha256'],'handoff-request-identity')
    intent=dict(deepcopy(req['receiptIntentTemplate']),signature=state['signature'])
    validate_intent(intent)
    identity=digest(dict(policySha256=state['policySha256'],evidenceSha256=state['evidenceSha256'],
                         signedWireSha256=state['signedWireSha256']))
    return dict(format=VERSION+'-accounting',id=identity,intent=intent,
        wireSha256=state['signedWireSha256'],messageSha256=state['messageSha256'],
        reservation=dict(principalAtomic=state['reservedPrincipalAtomic'],feeLamports=state['reservedFeeLamports'],
                         maximumExitAttempts=state['maximumExitAttempts']),
        submissionObserved=False,receiptApplied=False,allocationTransferred=False)
