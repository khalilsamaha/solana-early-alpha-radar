"""Exact devnet-only atomic WSOL lifecycle message and receipt contract."""
import hashlib
from core import raw58, check, integer, GENESIS, decode_wire
from wire import verify_signed_message

TOKEN = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
NATIVE = 'So11111111111111111111111111111111111111112'
SYSTEM = '11111111111111111111111111111111'
AMOUNT = 1000
MAX_RENT = 2500000
MAX_FEE = 20000


def instruction(program, accounts, data):
    check(len(data)<128, 'instruction-size')
    return bytes([program,len(accounts),*accounts,len(data)])+data


def message(wallet, source, destination, blockhash, rent):
    check(integer(rent) and 0<rent<=MAX_RENT, 'rent-cap')
    keys=[wallet,source,destination,SYSTEM,TOKEN,NATIVE]
    check(len(set(keys))==6, 'duplicate-keys')
    def create(index, funding):
        return instruction(3,[0,index],bytes(4)+funding.to_bytes(8,'little')+(165).to_bytes(8,'little')+raw58(TOKEN))
    def init(index): return instruction(4,[index,5],bytes([18])+raw58(wallet))
    ops=[create(1,rent+AMOUNT),init(1),create(2,rent),init(2),
         instruction(4,[1,5,2,0],bytes([12])+AMOUNT.to_bytes(8,'little')+bytes([9])),
         instruction(4,[1,0,0],bytes([9])),instruction(4,[2,0,0],bytes([9]))]
    # Three writable signers, three readonly unsigned program/mint keys.
    return bytes([3,0,3,6])+b''.join(raw58(k) for k in keys)+raw58(blockhash)+bytes([7])+b''.join(ops)


def validate_intent(i, wallet, source, destination):
    check(i.get('format')=='devnet-token-lifecycle-intent-1' and i.get('network')=='devnet'
          and i.get('genesis')==GENESIS['devnet'], 'intent-cluster')
    check([i.get(k) for k in ('wallet','source','destination')]==[wallet,source,destination], 'intent-accounts')
    check(i.get('amountLamports')==AMOUNT and i.get('maximumFeeLamports')==MAX_FEE
          and i.get('maximumRentPerAccountLamports')==MAX_RENT, 'intent-policy')
    check(integer(i.get('quotedFeeLamports')) and 0<i['quotedFeeLamports']<=MAX_FEE
          and integer(i.get('contextSlot')) and integer(i.get('lastValidBlockHeight')), 'intent-numbers')
    msg=message(wallet,source,destination,i['blockhash'],i['rentPerAccountLamports'])
    check(hashlib.sha256(msg).hexdigest()==i.get('messageSha256'), 'intent-message')
    return msg


def bound(plan, wallet, source, destination):
    msg=validate_intent(plan['intent'],wallet,source,destination)
    check(decode_wire(plan['signed_wire'])[1]==msg, 'signed-plan-mismatch')
    v=verify_signed_message(plan['signed_wire'])
    check(v['requiredSignatures']==3 and v['addressLookupCount']==0, 'signature-policy')
    return v


def balances(pre, post, fee, intent, success):
    check(fee is not None, 'receipt-fee-unavailable')
    check(integer(fee) and fee==intent['quotedFeeLamports'] and 0<fee<=MAX_FEE, 'receipt-fee-mismatch')
    check(isinstance(pre,list) and isinstance(post,list) and len(pre)==len(post)==6
          and all(integer(n) for n in pre+post), 'receipt-balances-unavailable')
    check(pre[1:3]==post[1:3]==[0,0], 'receipt-temporary-account-balance')
    check(pre[0]>=fee and post[0]==pre[0]-fee and pre[3:]==post[3:], 'receipt-balance-mismatch')
    if success:
        check(pre[0]>=2*intent['rentPerAccountLamports']+AMOUNT+fee, 'receipt-insufficient-upfront-funding')


def receipt(tx, status, plan):
    i=plan['intent']
    check(isinstance(tx,dict) and integer(tx.get('slot')) and tx['slot']==status['slot']
          and tx.get('version')=='legacy', 'receipt-slot-or-version-mismatch')
    check(tx.get('transaction')==[plan['signed_wire'],'base64'], 'receipt-wire-mismatch')
    meta=tx.get('meta')
    check(isinstance(meta,dict) and 'err' in meta, 'receipt-metadata-unavailable')
    check(meta['err']==status['err'], 'receipt-status-disagreement')
    success=meta['err'] is None
    balances(meta.get('preBalances'),meta.get('postBalances'),meta.get('fee'),i,success)
    check(meta.get('preTokenBalances') is not None and meta.get('postTokenBalances') is not None,
          'receipt-token-evidence-unavailable')
    check(meta.get('preTokenBalances')==[] and meta.get('postTokenBalances')==[]
          and meta.get('innerInstructions') in (None,[])
          and meta.get('loadedAddresses',{'writable':[],'readonly':[]})=={'writable':[],'readonly':[]},
          'receipt-unexpected-account-effects')
    return {'state':'finalized-success' if success else 'finalized-failure',
            'signature':plan['simulation']['signature'],'slot':tx['slot'],'feeLamports':meta['fee'],
            'walletBeforeLamports':str(meta['preBalances'][0]),'walletAfterLamports':str(meta['postBalances'][0]),
            'nativeBeforeLamports':[str(n) for n in meta['preBalances']],
            'nativeAfterLamports':[str(n) for n in meta['postBalances']],
            'wireSha256':plan['simulation']['wireSha256'],
            'temporaryAccountsFinalLamports':[0,0],
            'lifecycleCompleted':success,'intermediateTokenBalancesObserved':False,
            'evidenceBasis':'Exact signed seven-instruction contract plus RPC finalized outcome and complete native endpoint balances; transient token balances are not recorded.'}
