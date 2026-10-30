"""Non-executable reverse message draft from raw same-simulation entry evidence.

No fee assertion is invented or borrowed. The entry blockhash is a reference
only. Draft wire stays in process and is never accepted by an execution CLI.
"""
import base64
from copy import deepcopy
import hashlib
import post_entry
from core import check
from contract import (digest, decode_wire, decode, TOKEN, PROGRAM, COMPUTE, ROLES,
                      WRITABLE, DISCRIMINATOR, U64, fields)
from fresh_packet import message, scope_check
from swap_rehearsal import scope_for
from state import account, u64

VERSION='projected-reverse-message-1'
DRAFT_FIELDS={'format','network','scope','referenceBlockhash','parentSimulationSha256',
              'parentProjectionSha256','unsignedTransactionBase64'}


def expected(inputs, request):
    post=post_entry.assess(inputs,request)
    check(post['state']=='simulated-post-entry-projection-consistent','exit-parent-evidence')
    p=post['projection'];scope=scope_for(inputs['packet']['policy'])
    a=scope['accounts']
    for left,right in (('source','destination'),('inputMint','outputMint'),('inputVault','outputVault')):
        a[left],a[right]=a[right],a[left]
    scope['amountIn']=p['acquiredInputAtomic']
    scope['minimumAmountOut']=p['projectedMinimumOutputAtomic']
    scope_check(scope)
    check(a['inputMint']==p['inputMint'] and a['outputMint']==p['outputMint'],'exit-mints')
    rows=inputs['simulation_item']['result']['value']['accounts']
    # Exact token identity/byte checks have already been repeated by post_entry.
    source=u64(account(rows[2],TOKEN,165),64)
    destination=u64(account(rows[1],TOKEN,165),64)
    check(int(scope['amountIn'])<=source and destination+int(p['projectedOutputAtomic'])<=U64,
          'exit-projected-token-funding')
    return post,scope


def build(inputs, request):
    """Internal draft only. Never call fresh_packet.build or attach a fee assertion."""
    post,scope=expected(inputs,request)
    blockhash=inputs['packet']['policy']['blockhash']
    wire=b'\x01'+bytes(64)+message(scope,blockhash)
    return dict(format=VERSION+'-draft',network='devnet',scope=scope,
        referenceBlockhash=blockhash,parentSimulationSha256=post['evidence']['fullSimulationSha256'],
        parentProjectionSha256=post['evidence']['projectionSha256'],
        unsignedTransactionBase64=base64.b64encode(wire).decode())


def assess(inputs, request, draft):
    result=dict(format=VERSION,state='unavailable',reasons=[],binding=None,
        draftOnly=True,validForSubmission=False,signingApproved=False,executionApproved=False,
        exitSimulationVerified=False,exitFeeVerified=False,blockhashValidityVerified=False,
        actualEntryExecuted=False,roundTripFundingEstablished=False,mainnetSupported=False,
        sourceEquivalenceVerified=False,networkRequests=0,signaturesCreated=0,transactionsSent=0,
        exitFeeLamports=None,netProfit=None,
        limitations=[
            'Reverse message draft uses simulated entry output, not committed token proceeds.',
            'The entry blockhash is a reference only; no fresh exit blockhash or expiry is asserted.',
            'No exit fee assertion is copied from entry; complete round-trip funding is unknown.',
            'Draft wire is neither exported nor passed to an RPC, signer, sender or durable journal.',
            'No exit simulation, oracle-effect review, deployed-source equivalence or profitability pass.'])
    try:result.update(_assess(inputs,request,draft))
    except (ValueError,KeyError,TypeError,IndexError,OverflowError):
        result['reasons']=['projected-exit-message-rejected']
    return result


def _assess(inputs,request,draft):
    post,scope=expected(inputs,request)
    fields(draft,DRAFT_FIELDS,'exit-draft-schema')
    check(draft['format']==VERSION+'-draft' and draft['network']=='devnet','exit-draft-network')
    check(digest(draft['scope'])==digest(scope),'exit-draft-scope')
    check(draft['parentSimulationSha256']==post['evidence']['fullSimulationSha256'] and
          draft['parentProjectionSha256']==post['evidence']['projectionSha256'],'exit-parent-binding')
    check(draft['referenceBlockhash']==inputs['packet']['policy']['blockhash'],'exit-reference-blockhash')
    raw,msg,signers,signatures,tx=decode_wire(draft['unsignedTransactionBase64'])
    check(tx['version']=='legacy' and len(signers)==1 and signatures==[bytes(64)],'exit-wire-unsigned-legacy')
    m=tx['transaction']['message'];keys=m['accountKeys'];h=m['header']
    a=dict(scope['accounts'],inputTokenProgram=TOKEN,outputTokenProgram=TOKEN)
    check(keys[0]==a['wallet'] and m['recentBlockhash']==draft['referenceBlockhash'],'exit-wire-header')
    check(set(keys)==set(a.values())|{PROGRAM,COMPUTE},'exit-wire-keys')
    writable=set(keys[:h['numRequiredSignatures']-h['numReadonlySignedAccounts']])
    writable.update(keys[h['numRequiredSignatures']:len(keys)-h['numReadonlyUnsignedAccounts']])
    check(writable=={a[k] for k in WRITABLE},'exit-wire-privileges')
    ix=m['instructions'];check(len(ix)==3,'exit-wire-instructions')
    limit,price,swap=ix
    for v in (limit,price):check(keys[v['programIdIndex']]==COMPUTE and v['accounts']==[],'exit-wire-compute')
    check(decode(limit['data'])==b'\x02'+scope['maxComputeUnits'].to_bytes(4,'little'),'exit-wire-limit')
    check(decode(price['data'])==b'\x03'+bytes(8),'exit-wire-zero-priority')
    check(keys[swap['programIdIndex']]==PROGRAM and
          [keys[i] for i in swap['accounts']]==[a[k] for k in ROLES],'exit-wire-roles')
    data=decode(swap['data'])
    check(len(data)==24 and data[:8]==DISCRIMINATOR,'exit-wire-instruction')
    check(int.from_bytes(data[8:16],'little')==int(scope['amountIn']) and
          int.from_bytes(data[16:24],'little')==int(scope['minimumAmountOut']),'exit-wire-amounts')
    return dict(state='projected-reverse-message-consistent',reasons=[],binding=dict(
        parentSimulationSha256=post['evidence']['fullSimulationSha256'],
        parentProjectionSha256=post['evidence']['projectionSha256'],
        parentMessageSha256=post['evidence']['messageSha256'],
        draftSha256=digest(draft),messageSha256=hashlib.sha256(msg).hexdigest(),
        unsignedWireSha256=hashlib.sha256(raw).hexdigest(),scopeSha256=digest(scope),
        accounts=scope['accounts'],inputAtomic=scope['amountIn'],
        projectedOutputAtomic=post['projection']['projectedOutputAtomic'],
        minimumOutputAtomic=scope['minimumAmountOut'],computeUnits=scope['maxComputeUnits'],
        priorityPriceMicroLamports='0',instructionCount=3,messageVersion='legacy',
        quantityBasis='exact-simulated-entry-acquisition',
        blockhashBasis='entry-message-reference-only',feeBasis='not-observed',
        evaluatedAtMs=post['evidence']['evaluatedAtMs']))
