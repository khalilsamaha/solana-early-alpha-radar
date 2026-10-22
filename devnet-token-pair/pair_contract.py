"""Exact atomic two-mint standard SPL setup; all supplies and authority effects fixed."""
import hashlib
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'devnet-rehearsal'))
sys.path.insert(0,str(ROOT/'swap-state'))
from core import check, raw58, integer, GENESIS, decode_wire
from wire import verify_signed_message
from state import mint, token, account, TOKEN, SYSTEM

SUPPLY=1000000000
DECIMALS=6
MAX_MINT_RENT=2000000
MAX_HOLDER_RENT=2500000
MAX_FEE=50000
MAX_SPEND=6000000
CHILD='test-token-pair-v1'
NAMES=('wallet','mintA','holderA','mintB','holderB')


def keys_check(keys):
    check(type(keys) is dict and set(keys)==set(NAMES),'pair-account-schema')
    for k in keys.values(): raw58(k)
    check(len(set(keys.values())|{TOKEN,SYSTEM})==7,'pair-account-alias')


def message(keys,blockhash,mint_rent,holder_rent):
    keys_check(keys)
    check(integer(mint_rent) and 0<mint_rent<=MAX_MINT_RENT and
          integer(holder_rent) and 0<holder_rent<=MAX_HOLDER_RENT,'pair-rent-cap')
    check(2*(mint_rent+holder_rent)+MAX_FEE<=MAX_SPEND,'pair-total-cap')
    def ix(p,accounts,data):return bytes([p,len(accounts),*accounts,len(data)])+data
    def create(idx,size,rent):return ix(5,[0,idx],bytes(4)+rent.to_bytes(8,'little')+size.to_bytes(8,'little')+raw58(TOKEN))
    ops=[]
    for m,h in ((1,2),(3,4)):
        ops += [create(m,82,mint_rent),ix(6,[m],bytes([20,DECIMALS])+raw58(keys['wallet'])+b'\0'),
                create(h,165,holder_rent),ix(6,[h,m],b'\x12'+raw58(keys['wallet'])),
                ix(6,[m,h,0],b'\x0e'+SUPPLY.to_bytes(8,'little')+bytes([DECIMALS])),
                ix(6,[m,0],bytes([6,0,0]))]
    msg=bytes([5,0,2,7])+b''.join(raw58(keys[k]) for k in NAMES)+raw58(SYSTEM)+raw58(TOKEN)+raw58(blockhash)+bytes([12])+b''.join(ops)
    check(1+5*64+len(msg)<=1232,'pair-wire-cap')
    return msg


def intent_message(i,keys):
    check(type(i) is dict and i.get('format')=='devnet-token-pair-intent-1' and i.get('network')=='devnet'
          and i.get('genesis')==GENESIS['devnet'] and i.get('accounts')==keys,'pair-intent-identity')
    check(i.get('supplyAtomicPerMint')==str(SUPPLY) and i.get('decimals')==DECIMALS
          and i.get('mintAuthorityAfter') is None and i.get('freezeAuthority') is None
          and i.get('maximumFeeLamports')==MAX_FEE and i.get('maximumSpendLamports')==MAX_SPEND,'pair-intent-policy')
    for name in ('contextSlot','lastValidBlockHeight','recordedAtMs','expiresAtMs','walletObservedLamports','quotedFeeLamports'):
        check(integer(i.get(name)),'pair-intent-number')
    check(0<i['quotedFeeLamports']<=MAX_FEE and i['contextSlot']>0 and i['lastValidBlockHeight']>0
          and i['expiresAtMs']==i['recordedAtMs']+30000,'pair-intent-bounds')
    msg=message(keys,i['blockhash'],i['mintRentLamports'],i['holderRentLamports'])
    check(i['walletObservedLamports']>=2*(i['mintRentLamports']+i['holderRentLamports'])+MAX_FEE,'pair-insufficient-balance')
    check(hashlib.sha256(msg).hexdigest()==i.get('messageSha256'),'pair-intent-message')
    return msg


def bound(i,keys,wire):
    check(decode_wire(wire)[1]==intent_message(i,keys),'pair-signed-message')
    v=verify_signed_message(wire)
    check(v['requiredSignatures']==5 and v['addressLookupCount']==0 and v['version']=='legacy','pair-signatures')
    return v


def native_balances(pre,post,fee,i,success):
    check(type(fee) is int and 0<fee==i['quotedFeeLamports']<=MAX_FEE,'receipt-fee-mismatch')
    check(type(pre) is list and type(post) is list and len(pre)==len(post)==7 and
          all(integer(n) for n in pre+post),'receipt-native-missing')
    check(pre[1:5]==[0]*4,'receipt-accounts-existed')
    check(pre[0]==i['walletObservedLamports'],'receipt-wallet-prebalance')
    expected=pre.copy();expected[0]-=fee
    if success:
        rents=[i['mintRentLamports'],i['holderRentLamports']]*2
        expected[0]-=sum(rents);expected[1:5]=rents
    check(post==expected and min(post)>=0,'receipt-native-deltas')


def token_balances(rows,keys,success):
    check(type(rows) is list,'receipt-token-missing')
    if not success:
        check(rows==[],'receipt-failed-token-effects');return
    check(len(rows)==2,'receipt-token-count')
    indexed={}
    for r in rows:
        check(type(r) is dict and type(r.get('accountIndex')) is int and r['accountIndex'] in (2,4)
              and r['accountIndex'] not in indexed,'receipt-token-index')
        indexed[r['accountIndex']]=r
    for idx,m in ((2,'mintA'),(4,'mintB')):
        r=indexed[idx];a=r.get('uiTokenAmount')
        check(r.get('mint')==keys[m] and r.get('owner')==keys['wallet'] and r.get('programId')==TOKEN
              and type(a) is dict and a.get('amount')==str(SUPPLY) and type(a.get('decimals')) is int
              and a['decimals']==DECIMALS,'receipt-token-identity-or-amount')


def account_states(rows,i):
    keys=i['accounts'];check(type(rows) is list and len(rows)==4,'pair-snapshot-count')
    out=[]
    for j,suffix in ((0,'A'),(2,'B')):
        m=mint(rows[j]);t=token(rows[j+1],keys['mint'+suffix],keys['wallet'])
        check(m==dict(supply=str(SUPPLY),decimals=DECIMALS,mintAuthority=None,freezeAuthority=None),'pair-mint-state')
        check(t['amount']==str(SUPPLY) and t['nativeReserve'] is None and t['delegate'] is None
              and t['delegatedAmount']=='0' and t['closeAuthority'] is None,'pair-holder-state')
        check(rows[j]['lamports']==i['mintRentLamports'] and rows[j+1]['lamports']==i['holderRentLamports'],'pair-account-rent')
        out.append(dict(mint=keys['mint'+suffix],holder=keys['holder'+suffix],**m,holderAmountAtomic=t['amount'],
                        mintRentLamports=rows[j]['lamports'],holderRentLamports=rows[j+1]['lamports']))
    return out


def receipt(tx,st,i,wire):
    check(type(tx) is dict and integer(tx.get('slot')) and tx['slot']==st['slot'] and tx.get('version')=='legacy','receipt-slot-or-version')
    check(tx.get('transaction')==[wire,'base64'],'receipt-wire-mismatch')
    meta=tx.get('meta');check(type(meta) is dict and 'err' in meta,'receipt-metadata-missing')
    check(meta['err']==st['err'],'receipt-status-disagreement');success=meta['err'] is None
    native_balances(meta.get('preBalances'),meta.get('postBalances'),meta.get('fee'),i,success)
    check(meta.get('preTokenBalances')==[],'receipt-pretoken-effects')
    token_balances(meta.get('postTokenBalances'),i['accounts'],success)
    check(meta.get('innerInstructions') in (None,[]) and
          meta.get('loadedAddresses',{'writable':[],'readonly':[]})=={'writable':[],'readonly':[]},'receipt-extra-effects')
    v=bound(i,i['accounts'],wire)
    return dict(state='finalized-success' if success else 'finalized-failure',signature=v['signatures'][0],
                wireSha256=v['wireSha256'],messageSha256=v['wireMessageSha256'],slot=tx['slot'],
                feeLamports=meta['fee'],walletBeforeLamports=str(meta['preBalances'][0]),
                walletAfterLamports=str(meta['postBalances'][0]),rentLockedLamports=str(2*(i['mintRentLamports']+i['holderRentLamports']) if success else 0),
                evidenceBasis='Verified signed bytes and RPC finalized receipt; post-transaction account state is checked separately.')
