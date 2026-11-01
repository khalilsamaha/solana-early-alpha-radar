"""Fresh scoped post-exit balances from four read-only devnet requests.

Internal collector only. An as-of observation cannot release commitments or
serve as a future spending permit. Public reports are not accepted as inputs.
"""
import base64
from copy import deepcopy
import json
import time
import urllib.error
import urllib.request

import exit_accounting as accounting
from contract import digest, fields, uint, SYSTEM, NATIVE
from core import check
from journal import read_only_journals
from recorded_capture import GENESIS, NoRedirect, loads
from state import account, token, mint, snapshot

VERSION='admission-exit-balance-1'
view=accounting.view
ENDPOINT='https://api.devnet.solana.com'
METHODS=('getGenesisHash','getMultipleAccounts','getBlockTime','getGenesisHash')
MAX_RESPONSE=32768
MAX_CAPTURE=65536
FRESH_MS=10000
CHAIN_AGE_MS=30000
ERRORS={'balance-accounting-required','balance-flat-exit-required','balance-scope','balance-stopped',
        'balance-source-changed','balance-expired','balance-clock','balance-cluster','balance-slot',
        'balance-chain-time','balance-wallet-changed','balance-token-changed','balance-mint-changed',
        'balance-token-control','balance-fee-shortfall','balance-request-order','balance-request-parameters',
        'balance-rpc-unavailable','balance-response-cap','balance-capture-cap','balance-unsupported-native'}


def context(book,root,wallet,pool,clock,*,_allow_stopped=False):
    """Replay owned effects and retain prepared accounts privately for comparison."""
    check(_allow_stopped or not accounting.submission.handoff.stopped(root,book),'balance-stopped')
    src=accounting.review(book);record=accounting.saved(book.db,clock())
    result=accounting.public(src,record)
    check(result['accountingUsable'],'balance-accounting-required')
    a=record['accounting']
    check(a['state']=='exit-position-flat-held' and a['ownedAcquiredResidualAtomic']=='0','balance-flat-exit-required')
    check(a['wallet']==wallet and book.policy['scope']['accounts']['pool']==pool,'balance-scope')
    check(a['sourceMint']!=NATIVE and a['acquiredMint']!=NATIVE,'balance-unsupported-native')
    prepared=accounting.submission.handoff.preparation.saved(book,clock())
    c=prepared['evidence']['capture'];rows=dict(zip(c['accountKeys'],c['evidence']['accounts']['result']['value']))
    keys=[wallet,a['sourceAccount'],a['acquiredAccount'],a['sourceMint'],a['acquiredMint']]
    check(len(set(keys))==5,'balance-scope')
    expected=deepcopy([rows[k] for k in keys])
    expected[0]['lamports']-=int(a['exitFeePaidLamports'])
    for row,value in zip(expected[1:3],(a['observedSourceAccountPostAtomic'],a['observedAcquiredAccountPostAtomic'])):
        raw=bytearray(base64.b64decode(row['data'][0],validate=True));raw[64:72]=int(value).to_bytes(8,'little')
        row['data']=[base64.b64encode(raw).decode(),'base64']
    admission=book.read()
    local=(view.read_locked(root,wallet,pool,clock,_closed_history=True) if _allow_stopped
           else view.read_locked(root,wallet,pool,clock))
    check(local['wallet']==wallet and local['pool']==pool and local['phase']=='closed' and
        local['nativeHeldLamports']=='0' and all(x['heldAtomic']=='0' for x in local['tokenAccounts']) and
        local['ledgerHeadSha256']==admission[0]['ledgerHeadSha256'] and
        local['cycleBindingSha256']==admission[0]['cycleBindingSha256'],'balance-source-changed')
    identity=dict(accountingSha256=digest(record),admissionSha256=digest(admission),
        sourceLedgerHeadSha256=local['ledgerHeadSha256'],sourceCycleBindingSha256=local['cycleBindingSha256'],
        policySha256=digest(book.policy),preparationSha256=digest(prepared),captureSha256=src['captureSha256'])
    return dict(identity=identity,accountKeys=keys,expectedAccounts=expected,receiptSlot=a['receiptSlot'],
        recordedAtMs=record['recordedAtMs'],feeHeldLamports=a['feeCommitmentRemainingLamports'],
        proceedsHeldAtomic=a['sourceProceedsHeldAtomic'],protectedInventoryAtomic=a['protectedAcquiredInventoryAtomic'])


def project(method,value):
    if method=='getMultipleAccounts':
        slot,rows=snapshot(value,5);clean=[]
        for row in rows:
            if row is None:clean.append(None);continue
            check(type(row) is dict,'balance-rpc-unavailable')
            data=row.get('data')
            check(type(data) is list and len(data)==2 and data[1]=='base64' and type(data[0]) is str and len(data[0])<=256,'balance-rpc-unavailable')
            clean.append({k:row[k] for k in ('owner','executable','lamports','data') if k in row})
        return dict(context=dict(slot=slot),value=clean)
    if method=='getGenesisHash':check(type(value) is str and len(value)<=44,'balance-cluster')
    else:uint(value,2**53-1,'balance-chain-time')
    return value


class Rpc:
    """Exact request order/parameters, no redirects/retries, bounded bytes/time."""
    def __init__(self,root,ctx,clock,monotonic,opener):
        self.root=root;self.ctx=ctx;self.clock=clock;self.monotonic=monotonic
        self.start=clock();self.last=self.start;self.mono=monotonic();self.last_mono=self.mono
        self.calls=[];self.slot=None;self.total=0
        self.opener=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    def current(self):
        stamp=self.clock();elapsed=self.monotonic()
        check(type(stamp) is int and self.last<=stamp<self.start+FRESH_MS,'balance-expired')
        check(self.last_mono<=elapsed<self.mono+FRESH_MS/1000,'balance-expired')
        check(not view.cycles.c.submit.swap.stop(self.root),'balance-stopped')
        self.last=stamp;self.last_mono=elapsed
        return stamp
    def request(self,method,params):
        stamp=self.current();i=len(self.calls)
        check(i<4 and method==METHODS[i],'balance-request-order')
        expected=[] if i in (0,3) else ([self.ctx['accountKeys'],dict(encoding='base64',commitment='finalized',minContextSlot=self.ctx['receiptSlot'])] if i==1 else [self.slot])
        check(params==expected and (i!=2 or self.slot is not None),'balance-request-parameters')
        self.calls.append(dict(method=method,parametersSha256=digest(params),requestedAtMs=stamp))
        request=urllib.request.Request(ENDPOINT,method='POST',headers={'Content-Type':'application/json'},
            data=json.dumps(dict(jsonrpc='2.0',id=i+1,method=method,params=params)).encode())
        try:
            remaining=min((self.start+FRESH_MS-stamp)/1000,self.mono+FRESH_MS/1000-self.last_mono)
            with self.opener.open(request,timeout=remaining) as response:raw=response.read(MAX_RESPONSE+1)
            self.current();self.total+=len(raw)
            check(len(raw)<=MAX_RESPONSE,'balance-response-cap');check(self.total<=MAX_CAPTURE,'balance-capture-cap')
            data=loads(raw)
            check(type(data) is dict and data.get('jsonrpc')=='2.0' and type(data.get('id')) is int and data['id']==i+1 and
                'result' in data and 'error' not in data,'balance-rpc-unavailable')
            value=project(method,data['result'])
            if i==1:self.slot=value['context']['slot']
            self.calls[-1]['receivedAtMs']=self.last
            return dict(state='received',result=value,receivedAtMs=self.last)
        except (urllib.error.URLError,TimeoutError,OSError):
            raise ValueError('balance-rpc-unavailable') from None


def review(ctx,capture,now):
    """Private raw collector replay; no report import or release side effects."""
    fields(capture,{'format','network','identity','accountKeys','startedAtMs','finishedAtMs','evidence','requestTrace'},'balance-capture-schema')
    check(len(json.dumps(capture).encode())<=MAX_CAPTURE,'balance-capture-cap')
    check(capture['format']==VERSION+'-capture' and capture['network']=='devnet' and capture['identity']==ctx['identity'] and
        capture['accountKeys']==ctx['accountKeys'],'balance-scope')
    start=capture['startedAtMs'];finish=capture['finishedAtMs']
    uint(start,now,'balance-clock',minimum=ctx['recordedAtMs']);uint(finish,now,'balance-clock',minimum=start)
    check(now<start+FRESH_MS,'balance-expired')
    ev=capture['evidence'];fields(ev,{'genesisBefore','accounts','blockTime','genesisAfter'},'balance-evidence-schema')
    trace=capture['requestTrace'];check(type(trace) is list and len(trace)==4,'balance-request-order')
    last=start
    for i,name in enumerate(('genesisBefore','accounts','blockTime','genesisAfter')):
        item=ev[name];fields(item,{'state','result','receivedAtMs'},'balance-item-schema')
        check(item['state']=='received','balance-rpc-unavailable')
        row=trace[i];fields(row,{'method','parametersSha256','requestedAtMs','receivedAtMs'},'balance-trace-schema')
        check(row['method']==METHODS[i] and row['receivedAtMs']==item['receivedAtMs'],'balance-request-order')
        uint(row['requestedAtMs'],finish,'balance-clock',minimum=last)
        uint(item['receivedAtMs'],finish,'balance-clock',minimum=row['requestedAtMs']);last=item['receivedAtMs']
    check(ev['genesisBefore']['result']==ev['genesisAfter']['result']==GENESIS['devnet'],'balance-cluster')
    slot,rows=snapshot(ev['accounts']['result'],5)
    uint(slot,2**53-1,'balance-slot',minimum=ctx['receiptSlot'])
    expected_params=[[],[ctx['accountKeys'],dict(encoding='base64',commitment='finalized',minContextSlot=ctx['receiptSlot'])],[slot],[]]
    check(all(row['parametersSha256']==digest(p) for row,p in zip(trace,expected_params)),'balance-request-parameters')
    block=ev['blockTime']['result'];uint(block,2**53-1,'balance-chain-time')
    check(now-CHAIN_AGE_MS<=block*1000<=start+2000,'balance-chain-time')
    wallet,source,acquired,sm,am=rows;keys=ctx['accountKeys']
    account(wallet,SYSTEM,0)
    check(wallet['lamports']==ctx['expectedAccounts'][0]['lamports'],'balance-wallet-changed')
    check(wallet['lamports']>=int(ctx['feeHeldLamports']),'balance-fee-shortfall')
    for i,row in enumerate((source,acquired),1):
        parsed=token(row,keys[i+2],keys[0])
        check(parsed['delegate'] is None and parsed['delegatedAmount']=='0' and parsed['closeAuthority'] is None,'balance-token-control')
        check(all(row[k]==ctx['expectedAccounts'][i][k] for k in ('owner','executable','lamports','data')),'balance-token-changed')
    for i,row in enumerate((sm,am),3):
        mint(row)
        check(all(row[k]==ctx['expectedAccounts'][i][k] for k in ('owner','executable','lamports','data')),'balance-mint-changed')
    return dict(accountingSha256=ctx['identity']['accountingSha256'],snapshotSlot=slot,blockTime=block,
        observedAtMs=ev['accounts']['receivedAtMs'],validUntilExclusiveMs=start+FRESH_MS,
        walletLamports=str(wallet['lamports']),sourceAccountAtomic=token(source,keys[3],keys[0])['amount'],
        acquiredAccountAtomic=token(acquired,keys[4],keys[0])['amount'],
        feeHeldLamports=ctx['feeHeldLamports'],sourceProceedsHeldAtomic=ctx['proceedsHeldAtomic'],
        protectedInventoryAtomic=ctx['protectedInventoryAtomic'],ownedAcquiredResidualAtomic='0')


@view.cycles.binding.operation
def collect(home,wallet,pool,*,opener=None,clock=view.now,monotonic=time.monotonic,_evidence_sink=None):
    check(_evidence_sink is None or callable(_evidence_sink),'balance-sink')
    result=dict(format=VERSION,state='unavailable',diagnosticCode=None,networkRequests=0,requestMethods=[],
        snapshot=None,balanceReconciliationPassed=False,evidencePersisted=False,sourceStateChanged=False,
        databaseConnectionsReadOnly=True,reservationReleased=False,fundsAvailableForNewEntry=False,
        walletWideReservationsKnown=False,nextCycleAuthorized=False,executionApproved=False,runtimeIntegrated=False,
        privateKeyAccessed=False,signaturesCreated=0,transactionsSent=0,
        limitations=['Finalized RPC as-of balance consistency, not independent chain proof or future spendability.',
            'Four read-only requests maximum; no retries. Freshness includes final source replay.',
            'Any unexplained balance change, including a deposit, blocks reconciliation.',
            'Local locks cannot stop external wallet activity. No durable release or new allocation is authorized.'])
    rpc=None
    try:
        with view.cycles.c.source_lock(home,wallet) as root,read_only_journals():
            book=accounting.submission.transport._open(root,wallet,pool,clock)
            try:
                ctx=context(book,root,wallet,pool,clock)
                rpc=Rpc(root,ctx,clock,monotonic,opener);ev={}
                ev['genesisBefore']=rpc.request('getGenesisHash',[])
                check(ev['genesisBefore']['result']==GENESIS['devnet'],'balance-cluster')
                ev['accounts']=rpc.request('getMultipleAccounts',[ctx['accountKeys'],dict(encoding='base64',commitment='finalized',minContextSlot=ctx['receiptSlot'])])
                check(rpc.slot>=ctx['receiptSlot'],'balance-slot')
                ev['blockTime']=rpc.request('getBlockTime',[rpc.slot]);ev['genesisAfter']=rpc.request('getGenesisHash',[])
                finish=rpc.current()
                capture=dict(format=VERSION+'-capture',network='devnet',identity=ctx['identity'],accountKeys=ctx['accountKeys'],
                    startedAtMs=rpc.start,finishedAtMs=finish,evidence=ev,requestTrace=deepcopy(rpc.calls))
                # Replay from the journal again while the cooperating wallet lock is held.
                after=context(book,root,wallet,pool,clock)
                check(after==ctx,'balance-source-changed')
                stamp=rpc.current();checked=review(after,capture,stamp)
                if _evidence_sink is not None:
                    envelope=deepcopy(capture);rpc.current();_evidence_sink(envelope)
                # A slow sink never extends validity or yields a successful summary.
                rpc.current()
                result.update(state='exit-balances-match-held',snapshot=checked,balanceReconciliationPassed=True)
            finally:book.close()
    except (ValueError,KeyError,TypeError,IndexError,OSError,view.sqlite3.Error) as exc:
        result['diagnosticCode']=str(exc) if str(exc) in ERRORS else 'balance-evidence-unavailable'
    finally:
        if rpc is not None:result.update(networkRequests=len(rpc.calls),requestMethods=[x['method'] for x in rpc.calls])
    return result
