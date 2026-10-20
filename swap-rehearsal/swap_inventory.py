"""Public existing-account inventory. Historical pool identity is not fresh preflight."""
import time
from swap_rehearsal import FLAGS, audit, Client, GENESIS, integer
from preflight import key
from state import snapshot, token, account, SYSTEM
from core import context_value, check


class InventoryRpc(Client):
    METHODS=('getGenesisHash','getMultipleAccounts','getTokenAccountsByOwner')
    REQUEST_CAP=5
    def __init__(self,opener=None):super().__init__('devnet',opener)

    def request(self,method,params):
        r=super().request(method,params)
        if r['state']!='received':return r
        try:
            if method=='getGenesisHash':
                check(type(r['result']) is str and len(r['result'])<=44,'inventory-genesis')
            elif method=='getTokenAccountsByOwner':
                slot,rows=context_value(r,0)
                check(type(rows) is list and len(rows)<=32,'inventory-row-cap')
                clean=[]
                for row in rows:
                    key(row['pubkey']);a=row['account']
                    check(type(a) is dict and type(a.get('data')) is list and len(a['data'])==2
                          and type(a['data'][0]) is str and len(a['data'][0])<=220,'inventory-account-cap')
                    clean.append(dict(pubkey=row['pubkey'],account={k:a[k] for k in ('owner','executable','lamports','data') if k in a}))
                r['result']={'context':{'slot':slot},'value':clean}
            elif method=='getMultipleAccounts':
                slot,rows=snapshot(r['result'],1)
                a=rows[0]
                if a is not None:
                    check(type(a) is dict and a.get('data')==['','base64'],'inventory-wallet-layout')
                    a={k:a[k] for k in ('owner','executable','lamports','data') if k in a}
                r['result']={'context':{'slot':slot},'value':[a]}
        except (ValueError,KeyError,TypeError,IndexError):
            r={'state':'invalid-inventory-response'};self.calls[-1]['state']=r['state']
        return r


def review(capture,wallet,evidence,*,pool_reviewer=audit):
    result=dict(format='devnet-swap-inventory-review-1',state='unavailable',wallet=wallet,**FLAGS,
                signingApproved=False,walletKeyRead=False,signaturesCreated=0,accountSelectionAutomatic=False)
    try:
        key(wallet)
        p=pool_reviewer(capture,now_ms=capture['finishedAtMs'])
        check(p['state']=='pinned-pool-snapshot','reviewed-pool-required')
        result.update(pool=p['poolReview']['pool'],poolIdentityAsOfMs=capture['finishedAtMs'],
                      poolIdentityHistorical=True,currentPoolPreflightVerified=False)
        check(evidence['genesisBefore'].get('result')==GENESIS['devnet']
              and evidence['genesisBefore']['state']=='received'
              and evidence['genesisAfter'].get('result')==GENESIS['devnet']
              and evidence['genesisAfter']['state']=='received','inventory-cluster')
        slot,rows=context_value(evidence['wallet'],p['snapshotSlot'])
        check(type(rows) is list and len(rows)==1,'inventory-wallet-shape')
        balance=0
        if rows[0] is not None:account(rows[0],SYSTEM,0);balance=rows[0]['lamports']
        result.update(walletLamports=str(balance),feeHeadroomForRehearsal=balance>=10000,mints=[])
        pool=p['poolReview']['poolState']
        all_keys=set()
        for i in range(2):
            mint=pool['mint'+str(i)];s,items=context_value(evidence['mint'+str(i)],slot);slot=s
            check(type(items) is list and len(items)<=32,'inventory-row-cap')
            accepted=[];unsupported=0
            for row in items:
                addr=key(row['pubkey']);check(addr not in all_keys,'inventory-duplicate-account');all_keys.add(addr)
                try:
                    t=token(row['account'],mint,wallet)
                    check(t['nativeReserve'] is None and t['delegate'] is None and t['closeAuthority'] is None,'inventory-account-options')
                    accepted.append(dict(account=addr,amountAtomic=t['amount']))
                except ValueError:unsupported+=1
            result['mints'].append(dict(mint=mint,existingSupportedAccounts=accepted,unsupportedAccounts=unsupported,
                   hasFundedAccount=any(int(a['amountAtomic'])>0 for a in accepted)))
        result.update(state='inventory-observed',lastContextSlot=slot,
                      limitations=['Accounts are public observations from separate requests, not one signing snapshot.',
                                   'No token acquisition, account creation, wallet signing or execution was performed.',
                                   'Missing accounts or balances are prerequisites; do not purchase tokens for this devnet check.'])
    except (ValueError,KeyError,TypeError,IndexError):result.update(state='unavailable',reason='inventory-evidence-incomplete-or-unsupported')
    return result


def _collect_inventory(capture,wallet,*,opener=None,pool_reviewer=audit):
    key(wallet);p=pool_reviewer(capture,now_ms=capture['finishedAtMs'])
    check(p['state']=='pinned-pool-snapshot','reviewed-pool-required')
    rpc=InventoryRpc(opener);e={};minimum=p['snapshotSlot']
    try:
        e['genesisBefore']=rpc.request('getGenesisHash',[])
        check(e['genesisBefore'].get('state')=='received' and e['genesisBefore'].get('result')==GENESIS['devnet'],'inventory-cluster')
        e['wallet']=rpc.request('getMultipleAccounts',[[wallet],{'encoding':'base64','commitment':'finalized','minContextSlot':minimum}])
        minimum,_=context_value(e['wallet'],minimum)
        for i in range(2):
            e['mint'+str(i)]=rpc.request('getTokenAccountsByOwner',[wallet,{'mint':p['poolReview']['poolState']['mint'+str(i)]},
                     {'encoding':'base64','commitment':'finalized','minContextSlot':minimum}])
            minimum,_=context_value(e['mint'+str(i)],minimum)
        e['genesisAfter']=rpc.request('getGenesisHash',[])
    except (ValueError,KeyError,TypeError,IndexError):pass
    return dict(format='devnet-swap-inventory-1',capturedAtMs=time.time_ns()//1000000,sourcePoolCapture=capture,
                evidence=e,review=review(capture,wallet,e,pool_reviewer=pool_reviewer),requests=rpc.calls,networkRequests=len(rpc.calls),**FLAGS)


def collect_inventory(capture,wallet,*,opener=None):
    return _collect_inventory(capture,wallet,opener=opener)
