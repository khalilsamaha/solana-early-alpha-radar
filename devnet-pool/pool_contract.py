"""Fixed devnet CPMM initialization policy and exact account-effect verification."""
import base64
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for name in ('devnet-token-pair', 'swap-program', 'swap-preflight'):
    sys.path.insert(0, str(ROOT / name))
from pair_contract import keys_check, SUPPLY, DECIMALS
from core import check, raw58, integer, GENESIS, decode_wire, b58
from wire import verify_signed_message
from state import (TOKEN, SYSTEM, PROGRAM, AUTHORITY, NATIVE, account, mint, token,
                   configuration, decode_pool, anchor, u64)
from program import program_pointer, deployment, IDENTITY_FIELDS
from baseline import BASELINE

CHILD = 'controlled-pool-v1'
CONFIG = '8Pg5wr9H5i2GKbiH8315UiM1W9LJQT2tNiuqBeaoGKjz'
FEE_RECEIVER = '3oE58BKVt8KuYkGxx8zBojugnymWmBiyafWgMrnb6eYy'
ATA = 'ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL'
RENT = 'SysvarRent111111111111111111111111111111111'
COMPUTE = 'ComputeBudget111111111111111111111111111111'
DEPOSIT = 500000000  # 500 of each six-decimal test token; 500 remain.
MAX_FEE = 10000
MAX_CREATION_FEE = 150000000
MAX_SPEND = 190000000
COMPUTE_UNITS = 300000
SIZES = (82,165,637,4075)
RENT_CAPS = {82:2000000,165:2500000,637:5000000,4075:25000000}
WRITABLE = ('wallet','pool','lpMint','holder0','holder1','lpHolder','vault0','vault1','feeReceiver','observation')
READONLY = ('config','authority','mint0','mint1','tokenProgram','associatedTokenProgram','systemProgram','rent','program','compute')
ROLES = WRITABLE + READONLY
IX_ROLES = ('wallet','config','authority','pool','mint0','mint1','lpMint','holder0','holder1','lpHolder',
            'vault0','vault1','feeReceiver','observation','tokenProgram','tokenProgram','tokenProgram',
            'associatedTokenProgram','systemProgram','rent')
NEW_SIZES = {'pool':637,'lpMint':82,'lpHolder':165,'vault0':165,'vault1':165,'observation':4075}
DISCRIMINATOR = hashlib.sha256(b'global:initialize').digest()[:8]
P = 2**255-19
D = (-121665 * pow(121666,P-2,P)) % P


def on_curve(raw):
    """Compressed Edwards-y decompression existence; never used to sign/verify."""
    check(type(raw) is bytes and len(raw)==32,'pda-point-size')
    y = (int.from_bytes(raw,'little') & ((1<<255)-1)) % P
    numerator = (y*y-1) % P; denominator = (D*y*y+1) % P
    if not denominator: return False
    x2 = numerator * pow(denominator,P-2,P) % P
    return x2 == 0 or pow(x2,(P-1)//2,P)==1


def create_pda(seeds, program=PROGRAM):
    check(type(seeds) is list and len(seeds)<=16 and all(type(s) is bytes and len(s)<=32 for s in seeds),'pda-seeds')
    raw = hashlib.sha256(b''.join(seeds)+raw58(program)+b'ProgramDerivedAddress').digest()
    check(not on_curve(raw),'pda-on-curve')
    return b58(raw)


def pda(seeds, program=PROGRAM):
    check(type(seeds) is list and len(seeds)<16 and all(type(s) is bytes and len(s)<=32 for s in seeds),'pda-seeds')
    for bump in range(255,-1,-1):
        try: return create_pda(seeds+[bytes([bump])],program),bump
        except ValueError as e:
            if str(e)!='pda-on-curve': raise
    raise ValueError('pda-unavailable')


def addresses(pair):
    keys_check(pair)
    ordered=sorted(((pair['mintA'],pair['holderA']),(pair['mintB'],pair['holderB'])),key=lambda x:raw58(x[0]))
    m0,h0=ordered[0];m1,h1=ordered[1]
    pool,_=pda([b'pool',raw58(CONFIG),raw58(m0),raw58(m1)])
    lp,_=pda([b'pool_lp_mint',raw58(pool)])
    a=dict(wallet=pair['wallet'],pool=pool,lpMint=lp,holder0=h0,holder1=h1,
           lpHolder=pda([raw58(pair['wallet']),raw58(TOKEN),raw58(lp)],ATA)[0],
           vault0=pda([b'pool_vault',raw58(pool),raw58(m0)])[0],
           vault1=pda([b'pool_vault',raw58(pool),raw58(m1)])[0],feeReceiver=FEE_RECEIVER,
           observation=pda([b'observation',raw58(pool)])[0],config=CONFIG,authority=AUTHORITY,
           mint0=m0,mint1=m1,tokenProgram=TOKEN,associatedTokenProgram=ATA,
           systemProgram=SYSTEM,rent=RENT,program=PROGRAM,compute=COMPUTE)
    check(pda([b'vault_and_lp_mint_auth_seed'])==(AUTHORITY,255),'authority-anchor')
    check(len(set(a.values()))==len(ROLES),'pool-role-alias')
    return a


def message(pair,blockhash):
    a=addresses(pair);keys=[a[n] for n in ROLES]
    def ix(program,roles,data):
        return bytes([keys.index(program),len(roles),*[ROLES.index(n) for n in roles],len(data)])+data
    ops=[ix(COMPUTE,[],b'\x02'+COMPUTE_UNITS.to_bytes(4,'little')),ix(COMPUTE,[],b'\x03'+bytes(8)),
         ix(PROGRAM,IX_ROLES,DISCRIMINATOR+DEPOSIT.to_bytes(8,'little')*2+bytes(8))]
    msg=bytes([1,0,len(READONLY),len(keys)])+b''.join(raw58(k) for k in keys)+raw58(blockhash)+bytes([3])+b''.join(ops)
    check(len(msg)+65<=1232,'pool-wire-cap');return msg


def rent_total(rents):
    check(type(rents) is dict and set(rents)==set(map(str,SIZES)),'pool-rent-schema')
    for size,cap in RENT_CAPS.items():check(integer(rents[str(size)]) and 0<rents[str(size)]<=cap,'pool-rent-cap')
    return sum(rents[str(size)] for size in NEW_SIZES.values())


def intent_message(i,pair):
    check(type(i) is dict and i.get('format')=='devnet-pool-intent-1' and i.get('network')=='devnet'
          and i.get('genesis')==GENESIS['devnet'] and i.get('pairAccounts')==pair,'pool-intent-identity')
    a=addresses(pair);check(i.get('accounts')==a,'pool-intent-addresses')
    check(i.get('depositAtomicPerMint')==str(DEPOSIT) and i.get('openTime')==0
          and i.get('maximumFeeLamports')==MAX_FEE and i.get('maximumCreationFeeLamports')==MAX_CREATION_FEE
          and i.get('maximumSpendLamports')==MAX_SPEND and i.get('computeUnits')==COMPUTE_UNITS,'pool-intent-policy')
    for name in ('contextSlot','lastValidBlockHeight','recordedAtMs','expiresAtMs','walletObservedLamports','quotedFeeLamports','creationFeeLamports'):
        check(integer(i.get(name)),'pool-intent-number')
    check(0<i['quotedFeeLamports']<=MAX_FEE and 0<=i['creationFeeLamports']<=MAX_CREATION_FEE
          and i['contextSlot']>0 and i['lastValidBlockHeight']>0 and i['expiresAtMs']==i['recordedAtMs']+30000,'pool-intent-bounds')
    total=rent_total(i['rents'])+i['creationFeeLamports']+MAX_FEE
    check(total<=MAX_SPEND and i['walletObservedLamports']>=total,'pool-insufficient-balance-or-cap')
    check(type(i.get('preAccounts')) is list and len(i['preAccounts'])==len(ROLES),'pool-pre-accounts')
    pre_state(i['preAccounts'],pair,i['rents'],i['creationFeeLamports'])
    check(i['preAccounts'][0]['lamports']==i['walletObservedLamports'],'pool-wallet-binding')
    msg=message(pair,i['blockhash']);check(hashlib.sha256(msg).hexdigest()==i.get('messageSha256'),'pool-intent-message')
    return msg


def bound(i,pair,wire):
    check(decode_wire(wire)[1]==intent_message(i,pair),'pool-signed-message')
    v=verify_signed_message(wire)
    check(v['requiredSignatures']==1 and v['addressLookupCount']==0 and v['version']=='legacy','pool-signatures')
    return v


def clean_token(row,m,owner,amount):
    t=token(row,m,owner)
    check(t['amount']==str(amount) and t['delegate'] is None and t['closeAuthority'] is None
          and t['delegatedAmount']=='0','pool-token-state')
    return t


def config_fee(row):
    configuration(row);raw=account(row,PROGRAM,236)
    check(raw[9]==0,'pool-creation-disabled')
    fee=u64(raw,36);check(fee<=MAX_CREATION_FEE,'pool-creation-fee-cap');return fee


def pre_state(rows,pair,rents,fee):
    a=addresses(pair);check(type(rows) is list and len(rows)==len(ROLES),'pool-account-count')
    r=dict(zip(ROLES,rows));account(r['wallet'],SYSTEM,0)
    for name in NEW_SIZES:check(r[name] is None,'pool-account-already-exists')
    check(config_fee(r['config'])==fee,'pool-config-fee-changed')
    for n in (0,1):
        check(mint(r['mint'+str(n)])==dict(supply=str(SUPPLY),decimals=DECIMALS,mintAuthority=None,freezeAuthority=None),'pool-test-mint')
        clean_token(r['holder'+str(n)],a['mint'+str(n)],a['wallet'],SUPPLY)
    raw=account(r['feeReceiver'],TOKEN,165);owner=b58(raw[32:64])
    t=token(r['feeReceiver'],NATIVE,owner)
    check(t['delegate'] is None and t['closeAuthority'] is None and t['delegatedAmount']=='0','pool-fee-receiver-options')
    rent_total(rents)
    return a


def pin(rows,slot,baseline=None):
    baseline=BASELINE if baseline is None else baseline
    check(type(rows) is list and len(rows)==2,'pool-program-count')
    pointer=program_pointer(rows[0]);d=deployment(rows[1],slot)
    actual=dict(program=PROGRAM,programDataAddress=pointer,**d)
    check(slot>=baseline['observedSlot'] and all(actual[k]==baseline['identity'][k] for k in IDENTITY_FIELDS),'pool-deployment-changed')
    return {k:actual[k] for k in IDENTITY_FIELDS}


def native_balances(pre,post,fee,i,success):
    check(type(fee) is int and 0<fee==i['quotedFeeLamports']<=MAX_FEE,'receipt-fee-mismatch')
    check(type(pre) is list and type(post) is list and len(pre)==len(post)==len(ROLES)
          and all(integer(n) for n in pre+post),'receipt-native-missing')
    expected=pre.copy();expected[0]-=fee
    check(pre[0]==i['walletObservedLamports'],'receipt-wallet-prebalance')
    for name,size in NEW_SIZES.items():
        idx=ROLES.index(name);check(pre[idx]==0,'receipt-pool-existed')
        if success:expected[idx]=i['rents'][str(size)]
    if success:
        expected[0]-=rent_total(i['rents'])+i['creationFeeLamports']
        expected[ROLES.index('feeReceiver')]+=i['creationFeeLamports']
    check(expected==post and min(post)>=0,'receipt-native-deltas')


def token_rows(rows,i,success,post):
    check(type(rows) is list,'receipt-token-missing')
    a=i['accounts'];pre=dict(zip(ROLES,i['preAccounts']))
    fee_raw=account(pre['feeReceiver'],TOKEN,165);fee_owner=b58(fee_raw[32:64]);fee_state=token(pre['feeReceiver'],NATIVE,fee_owner)
    expected={'holder0':(a['mint0'],a['wallet'],SUPPLY-(DEPOSIT if success and post else 0),6),
              'holder1':(a['mint1'],a['wallet'],SUPPLY-(DEPOSIT if success and post else 0),6),
              'feeReceiver':(NATIVE,fee_owner,int(fee_state['amount'])+(int(fee_state['nativeSurplus'])+i['creationFeeLamports'] if success and post and i['creationFeeLamports'] else 0),9)}
    if success and post:
        expected.update(vault0=(a['mint0'],AUTHORITY,DEPOSIT,6),vault1=(a['mint1'],AUTHORITY,DEPOSIT,6),
                        lpHolder=(a['lpMint'],a['wallet'],DEPOSIT-100,9))
    found={}
    for r in rows:
        check(type(r) is dict and type(r.get('accountIndex')) is int and r['accountIndex'] not in found,'receipt-token-index')
        u=r.get('uiTokenAmount');check(type(u) is dict and type(u.get('decimals')) is int,'receipt-token-amount')
        check(r.get('programId')==TOKEN,'receipt-token-program')
        found[r['accountIndex']]=(r.get('mint'),r.get('owner'),u.get('amount'),u['decimals'])
    check(found=={ROLES.index(k):(m,o,str(n),d) for k,(m,o,n,d) in expected.items()},'receipt-token-deltas')


def account_states(rows,i,*,simulation=False):
    a=i['accounts'];check(type(rows) is list and len(rows)==len(ROLES),'pool-post-account-count')
    r=dict(zip(ROLES,rows));before=dict(zip(ROLES,i['preAccounts']))
    for n in (0,1):
        m='mint'+str(n);h='holder'+str(n);v='vault'+str(n)
        check(mint(r[m])==mint(before[m]),'pool-mint-changed')
        clean_token(r[h],a[m],a['wallet'],SUPPLY-DEPOSIT)
        clean_token(r[v],a[m],AUTHORITY,DEPOSIT)
    check(mint(r['lpMint'])==dict(supply=str(DEPOSIT-100),decimals=9,mintAuthority=AUTHORITY,freezeAuthority=None),'pool-lp-mint')
    clean_token(r['lpHolder'],a['lpMint'],a['wallet'],DEPOSIT-100)
    p=decode_pool(r['pool']);raw=account(r['pool'],PROGRAM,637)
    for name in ('config','vault0','vault1','lpMint','mint0','mint1','observation'):check(p[name]==a[name],'pool-post-binding')
    check(p['creator']==a['wallet'] and p['status']==0 and p['decimals0']==p['decimals1']==6
          and not p['creatorFeeEnabled'] and p['creatorFeeOn']==0 and p['accruedFees0']==p['accruedFees1']==0
          and raw[330]==9 and u64(raw,333)==DEPOSIT and p['openTime']>0,'pool-post-state')
    obs=account(r['observation'],PROGRAM,4075);anchor(obs,'ObservationState')
    check(obs[8:11]==bytes(3) and b58(obs[11:43])==a['pool'],'pool-oracle-binding')
    for name,size in NEW_SIZES.items():check(r[name]['lamports']==i['rents'][str(size)],'pool-post-rent')
    if simulation:
        for name in READONLY:
            check(r[name]==before[name],'pool-readonly-changed')
        for name in ('holder0','holder1'):check(r[name]['lamports']==before[name]['lamports'],'pool-holder-rent-changed')
        fee=ROLES.index('feeReceiver');pre=before['feeReceiver'];post=r['feeReceiver']
        raw=account(pre,TOKEN,165);owner=b58(raw[32:64]);t=token(post,NATIVE,owner)
        check(post['lamports']==pre['lamports']+i['creationFeeLamports'],'pool-fee-native')
        pre_t=token(pre,NATIVE,owner)
        check(t['nativeReserve']==pre_t['nativeReserve'] and t['delegate']==pre_t['delegate'] and t['closeAuthority']==pre_t['closeAuthority'],'pool-fee-options')
        expected=int(pre_t['amount'])+(int(pre_t['nativeSurplus'])+i['creationFeeLamports'] if i['creationFeeLamports'] else 0)
        check(t['amount']==str(expected),'pool-fee-sync')
        account(r['wallet'],SYSTEM,0)
        check(r['wallet']['lamports']==i['walletObservedLamports']-rent_total(i['rents'])-i['creationFeeLamports']-i['quotedFeeLamports'],'pool-post-wallet')
    return dict(pool=a['pool'],reservesAtomic=[str(DEPOSIT)]*2,remainingHolderAtomic=[str(SUPPLY-DEPOSIT)]*2,
                lpMint=a['lpMint'],lpHolder=a['lpHolder'],lpSupplyAtomic=str(DEPOSIT-100),
                poolAccountingLpSupplyAtomic=str(DEPOSIT),lockedLpAtomic='100',openTime=p['openTime'])


def receipt(tx,st,i,wire):
    check(type(tx) is dict and integer(tx.get('slot')) and tx['slot']==st['slot'] and tx.get('version')=='legacy','receipt-slot-or-version')
    check(tx.get('transaction')==[wire,'base64'],'receipt-wire-mismatch')
    meta=tx.get('meta');check(type(meta) is dict and 'err' in meta,'receipt-metadata-missing')
    check(meta['err']==st['err'],'receipt-status-disagreement');success=meta['err'] is None
    native_balances(meta.get('preBalances'),meta.get('postBalances'),meta.get('fee'),i,success)
    token_rows(meta.get('preTokenBalances'),i,success,False);token_rows(meta.get('postTokenBalances'),i,success,True)
    check(meta.get('loadedAddresses',{'writable':[],'readonly':[]})=={'writable':[],'readonly':[]},'receipt-extra-addresses')
    v=bound(i,i['pairAccounts'],wire)
    return dict(state='finalized-success' if success else 'finalized-failure',signature=v['signatures'][0],
        wireSha256=v['wireSha256'],messageSha256=v['wireMessageSha256'],slot=tx['slot'],feeLamports=meta['fee'],
        walletBeforeLamports=str(meta['preBalances'][0]),walletAfterLamports=str(meta['postBalances'][0]),
        rentLockedLamports=str(rent_total(i['rents']) if success else 0),creationFeeLamports=str(i['creationFeeLamports'] if success else 0),
        evidenceBasis='Exact signed bytes and native/token effects in the RPC receipt; account snapshot is separate.')
