"""Bounded expiry/receipt/balance evidence, without a recovery transition."""
from copy import deepcopy
from datetime import datetime, timezone
import time

import signed_exit_chain as chain
import exit_balance as balances
from contract import digest, uint, NATIVE, SYSTEM
from core import check
from journal import read_only_journals
from state import account, token, mint, snapshot

VERSION='expired-exit-evidence-1'
ORDER=('getGenesisHash','isBlockhashValid','getBlockHeight','getSignatureStatuses',
       'getTransaction','getMultipleAccounts','getBlockTime','getGenesisHash')
view=chain.view


class Rpc(chain.Client):
    METHODS=ORDER
    REQUEST_CAP=8


def context(root,book,wallet,pool,expected,clock):
    identity=chain.local(root,book,wallet,pool,expected,clock)
    record=chain.history.lifecycle.preparation.saved(book,clock())
    a=book.policy['scope']['accounts']
    keys=[wallet,a['source'],a['destination'],a['inputMint'],a['outputMint']]
    check(len(set(keys))==5 and NATIVE not in keys,'expiry-account-scope')
    capture=record['evidence']['capture']
    rows=dict(zip(capture['accountKeys'],capture['evidence']['accounts']['result']['value']))
    expected_rows=deepcopy([rows[k] for k in keys])
    height=record['collection']['packetBuild']['lastValidBlockHeight']
    uint(height,2**64-1,'expiry-last-height',minimum=1)
    with chain.history.transport.ExitSubmission(book).snapshot():
        signed=chain.history.transport.ExitSubmission(book).signing()['signed']['signedWireBase64']
    return dict(identity=identity,accountKeys=keys,expectedAccounts=expected_rows,
                lastValidBlockHeight=height,signedWire=signed)


def assess(ctx,ev,started,now):
    identity=ctx['identity'];floor=identity['minimumContextSlot']
    observation=chain.classify(ev['validity'],ev['status'],floor)
    received=chain.history.transport.transport.received
    check(received(ev['genesisBefore'])==received(ev['genesisAfter'])==chain.GENESIS['devnet'],'expiry-cluster')
    height=received(ev['height']);uint(height,2**64-1,'expiry-height')
    slot,rows=snapshot(received(ev['accounts']),5)
    uint(slot,2**53-1,'expiry-account-slot',minimum=observation['signatureStatusContextSlot'])
    blocktime=received(ev['blockTime']);uint(blocktime,2**53-1,'expiry-blocktime')
    check(started<=now and now-30000<=blocktime*1000<=now+2000,'expiry-account-time')
    rows=balances.project('getMultipleAccounts',dict(context=dict(slot=slot),value=rows))['value']
    keys=ctx['accountKeys'];expected=ctx['expectedAccounts']
    account(rows[0],SYSTEM,0);account(expected[0],SYSTEM,0)
    current_tokens=[token(rows[i],keys[i+2],keys[0]) for i in (1,2)]
    prior_tokens=[token(expected[i],keys[i+2],keys[0]) for i in (1,2)]
    for row in rows[3:]+expected[3:]:mint(row)
    fields=('owner','executable','lamports','data')
    matches=[all(row[k]==old[k] for k in fields) for row,old in zip(rows,expected)]
    controls=all(t['delegate'] is None and t['delegatedAmount']=='0' and t['closeAuthority'] is None for t in current_tokens)
    amount=identity['scopedAccounting']
    owned=int(amount['ownedAcquiredHeldAtomic']);protected=int(amount['protectedAcquiredInventoryAtomic'])
    check(int(prior_tokens[1]['amount'])>=owned+protected,'expiry-saved-inventory')
    inventory=int(current_tokens[1]['amount'])>=owned+protected
    fee=rows[0]['lamports']>=int(amount['feeHeldLamports'])
    tx=received(ev['transaction']);tx_present=tx is not None;wire_matches=None
    if tx_present:
        check(type(tx) is dict,'expiry-transaction-shape')
        uint(tx.get('slot'),slot,'expiry-transaction-slot',minimum=floor)
        wire_matches=tx.get('transaction')==[ctx['signedWire'],'base64']
    expired=observation['blockhashValidAtFinalized'] is False and height>ctx['lastValidBlockHeight']
    blockers=[]
    for condition,reason in ((not expired,'block-expiry-not-established'),
        (observation['signatureFound'],'signature-status-present'),(tx_present,'transaction-present-receipt-required'),
        (tx_present and not wire_matches,'returned-transaction-wire-conflict'),
        (not matches[0],'wallet-account-changed'),(not all(matches[1:3]),'token-account-changed'),
        (not all(matches[3:]),'mint-account-changed'),(not controls,'token-controls-changed'),
        (not inventory,'protected-or-owned-inventory-shortfall'),(not fee,'held-fee-shortfall')):
        if condition:blockers.append(reason)
    return dict(state='expiry-evidence-consistent-held' if not blockers else 'expiry-evidence-needs-review-held',
        blockers=blockers,chainObservation=observation,lastValidBlockHeight=ctx['lastValidBlockHeight'],
        finalizedBlockHeight=height,blockExpiryEvidenceConsistent=expired,
        transactionFound=tx_present,returnedWireMatchesRecorded=wire_matches,
        accountSnapshotSlot=slot,accountBlockTime=blocktime,
        accountSnapshotAgeMs=now-blocktime*1000,accountMatches=dict(wallet=matches[0],
            sourceToken=matches[1],acquiredToken=matches[2],sourceMint=matches[3],acquiredMint=matches[4]),
        walletLamports=str(rows[0]['lamports']),walletLamportsChange=str(rows[0]['lamports']-expected[0]['lamports']),
        sourceTokenAtomic=current_tokens[0]['amount'],acquiredTokenAtomic=current_tokens[1]['amount'],
        protectedAndOwnedInventoryCovered=inventory,heldFeeCovered=fee,
        nonExecutionProven=False,recoveryAuthorized=False,
        nextAction='review-controlled-retirement-policy' if not blockers else 'investigate-blockers-without-replacement')


@view.cycles.binding.operation
@chain.history.fresh_signing.timing.signature_replay
def inspect(home,wallet,pool,expected,*,opener=None,clock=view.now,monotonic=time.monotonic):
    r=dict(format=VERSION,state='expiry-evidence-unavailable',assessment=None,identity=None,
        diagnosticCode=None,networkRequests=0,requestMethods=[],sourceStateChanged=False,
        databaseConnectionsReadOnly=True,privateKeyAccessed=False,signaturesCreated=0,transactionsSent=0,
        reservationsReleasedThisRun=False,replacementAuthorized=False,retryAllowed=False,executionApproved=False,
        limitations=['One fixed devnet provider, not independent consensus or complete historical proof.',
          'Matching present balances cannot rule out intervening offsetting transactions.',
          'No retirement, release, re-signing or replacement transition is implemented by this report.'])
    start=monotonic();transport=None
    try:
        check(type(expected) is str and len(expected)==64 and all(c in '0123456789abcdef' for c in expected),'expiry-id')
        with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
            b=chain.history.lifecycle.entry.submission._open(root,wallet,pool,clock)
            try:
                with chain.history.lifecycle.admission_read_lock(b.j.path):
                    ctx=context(root,b,wallet,pool,expected,clock);i=ctx['identity']
                    elapsed=monotonic()-start;check(0<=elapsed<120,'expiry-budget')
                    plan=[];transport=chain.BoundedReads(plan,opener,monotonic,budget=min(30,120-elapsed))
                    rpc=Rpc('devnet',transport);ev={};began=clock()
                    def ask(name,method,params):
                        check(len(plan)<8 and method==ORDER[len(plan)],'expiry-order')
                        plan.append((method,params));item=rpc.request(method,params)
                        value=chain.history.transport.transport.received(item);ev[name]=item
                        return value
                    check(ask('genesisBefore','getGenesisHash',[])==chain.GENESIS['devnet'],'expiry-cluster')
                    ask('validity','isBlockhashValid',[i['blockhash'],dict(commitment='finalized',minContextSlot=i['minimumContextSlot'])])
                    block_slot,_=chain.history.transport.transport.context(ev['validity'],i['minimumContextSlot'])
                    ask('height','getBlockHeight',[dict(commitment='finalized',minContextSlot=block_slot)])
                    ask('status','getSignatureStatuses',[[i['signature']],dict(searchTransactionHistory=True)])
                    status=chain.classify(ev['validity'],ev['status'],i['minimumContextSlot'])
                    ask('transaction','getTransaction',[i['signature'],dict(encoding='base64',commitment='finalized',maxSupportedTransactionVersion=0)])
                    accounts=ask('accounts','getMultipleAccounts',[ctx['accountKeys'],dict(encoding='base64',commitment='finalized',minContextSlot=status['signatureStatusContextSlot'])])
                    account_slot,_=snapshot(accounts,5)
                    ask('blockTime','getBlockTime',[account_slot])
                    check(ask('genesisAfter','getGenesisHash',[])==chain.GENESIS['devnet'],'expiry-cluster')
                    check(0<=monotonic()-transport.started<=transport.budget,'expiry-budget')
                    after=context(root,b,wallet,pool,expected,clock);check(ctx==after,'expiry-local-changed')
                    stamp=clock();assessment=assess(ctx,ev,began,stamp)
                    check(0<=monotonic()-start<=120,'expiry-budget')
                    r.update(state='expired-exit-evidence-observed',assessment=assessment,
                        identity=dict(preparationSha256=expected,signingStateSha256=i['signingStateSha256'],
                            signatureSha256=digest(i['signature']),blockhashSha256=digest(i['blockhash'])),observedAtMs=stamp)
            finally:b.close()
    except view.ERRORS:r['diagnosticCode']='expired-exit-evidence-unavailable'
    finally:
        if transport is not None:r.update(networkRequests=len(transport.calls),requestMethods=list(transport.calls))
    r['capturedAt']=datetime.now(timezone.utc).isoformat();return r
