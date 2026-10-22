"""One combined finalized batch for program, pool and optional wallet; no signer or sender."""
import base64
import copy
import time
from preflight import (PROGRAM, GENESIS, StateError, need, snapshot, received, decode_pool,
                       account_keys, program_pointer, key, validate, integer, BASELINE)
from program import MAX_BASE64
from contract import decode_wire
from recorded_capture import Client


class PreflightClient(Client):
    METHODS = ('getGenesisHash', 'getMultipleAccounts', 'getBlockTime', 'isBlockhashValid', 'getFeeForMessage')
    REQUEST_CAP = 8

    def __init__(self, opener=None):
        super().__init__('devnet', opener)

    def request(self, method, params):
        if method == 'getMultipleAccounts':
            need(type(params) is list and len(params) == 2 and type(params[0]) is list and
                 len(params[0]) in (1, 9, 12) and type(params[1]) is dict and
                 params[1].get('commitment') == 'finalized' and params[1].get('encoding') == 'base64' and
                 'dataSlice' not in params[1], 'account-request-shape', 'invalid-input')
        item = super().request(method, params)
        if item['state'] != 'received': return item
        try:
            value = item['result']
            if method == 'getMultipleAccounts':
                slot, rows = snapshot(value, len(params[0])); clean=[]
                for i, row in enumerate(rows):
                    if row is None: clean.append(None); continue
                    data = row.get('data') if type(row) is dict else None
                    cap = MAX_BASE64 if len(rows) > 1 and i == len(rows)-1 else 6000
                    if (type(data) is not list or len(data) != 2 or data[1] != 'base64' or
                            type(data[0]) is not str or len(data[0]) > cap): raise ValueError()
                    clean.append({k:row[k] for k in ('data','owner','executable','lamports') if k in row})
                item['result'] = {'context':{'slot':slot},'value':clean}
            elif method in ('getFeeForMessage', 'isBlockhashValid'):
                slot = value['context']['slot']; v = value['value']
                if not integer(slot,1): raise ValueError()
                if method == 'getFeeForMessage' and v is not None and not integer(v): raise ValueError()
                if method == 'isBlockhashValid' and type(v) is not bool: raise ValueError()
                item['result'] = {'context':{'slot':slot},'value':v}
            elif method == 'getGenesisHash':
                if type(value) is not str or len(value) > 44: raise ValueError()
            elif value is not None and not integer(value): raise ValueError()
        except (ValueError, TypeError, KeyError, StateError):
            item = {'state':'invalid-preflight-response'}; self.calls[-1]['state']=item['state']
        return item


def _collect(*, pool=None, packet=None, opener=None, now=None, monotonic=None, baseline):
    now = now or (lambda:time.time_ns()//1000000); monotonic = monotonic or time.monotonic
    need((pool is None) != (packet is None), 'select-pool-or-packet', 'invalid-input')
    packet = copy.deepcopy(packet); baseline = copy.deepcopy(baseline)
    start, started_mono = now(), monotonic()
    if packet is not None:
        checked = validate(packet,now_ms=start)
        need(checked['state'] == 'instruction-policy-match', 'packet-not-current-or-supported', 'unavailable')
        pool = packet['policy']['accounts']['pool']
    key(pool)
    client = PreflightClient(opener)
    ev={n:{'state':'not-requested'} for n in ('genesisBefore','programBootstrap','poolBootstrap','accounts',
                                           'blockTime','blockhash','fee','genesisAfter')}
    c=dict(format='swap-preflight-capture-1',network='devnet',origin='public-rpc-capture',pool=pool,
           packet=packet,selection='prior-packet' if packet is not None else 'explicit-pool',
           evidence=ev,startedAtMs=start,requests=client.calls,transactionsSent=0,signaturesCreated=0,ledgerUpdated=False)

    def fetch(name,method,params):
        need(monotonic()-started_mono < 30,'capture-time-budget','unavailable')
        if packet is not None:
            need(validate(packet,now_ms=now())['state'] == 'instruction-policy-match',
                 'packet-expired-during-capture','unavailable')
        ev[name]=client.request(method,params)
        ev[name]['receivedAtMs']=now()
        need(ev[name]['state']=='received','rpc-stopped-'+name,'unavailable')
        return ev[name]['result']

    try:
        need(fetch('genesisBefore','getGenesisHash',[])==GENESIS['devnet'],'wrong-cluster')
        opts={'encoding':'base64','commitment':'finalized','minContextSlot':baseline['observedSlot']}
        p=fetch('programBootstrap','getMultipleAccounts',[[PROGRAM],opts]); pslot,prows=snapshot(p,1)
        need(pslot>=baseline['observedSlot'],'program-bootstrap-predates-baseline')
        pointer=program_pointer(prows[0])
        need(pointer==baseline['identity']['programDataAddress'],'program-pointer-differs-from-baseline')
        b=fetch('poolBootstrap','getMultipleAccounts',[[pool],dict(opts,minContextSlot=pslot)])
        bslot,brows=snapshot(b,1); need(bslot>=pslot,'bootstrap-slot-regression')
        keys=account_keys(pool,decode_pool(brows[0]),packet)
        need(pointer not in keys,'programdata-role-alias'); c['accountKeys']=keys+[pointer]
        batch=fetch('accounts','getMultipleAccounts',[c['accountKeys'],dict(opts,minContextSlot=bslot)])
        slot,rows=snapshot(batch,len(keys)+1); need(slot>=bslot,'snapshot-slot-regression')
        c['blockTimeSlot']=slot
        need(program_pointer(rows[7])==pointer,'program-pointer-changed')
        # Stop early on deployment drift before requesting message-specific evidence.
        from program import deployment, IDENTITY_FIELDS
        identity=dict(deployment(rows[-1],slot),program=PROGRAM,programDataAddress=pointer)
        need(all(identity[k]==baseline['identity'][k] for k in IDENTITY_FIELDS),'deployment-differs-from-pinned-observation')
        fetch('blockTime','getBlockTime',[slot])
        if packet is not None:
            opts={'commitment':'finalized','minContextSlot':slot}
            fetch('blockhash','isBlockhashValid',[packet['policy']['blockhash'],opts])
            c['messageSha256']=checked['wireMessageSha256']
            raw_message=decode_wire(packet['unsignedTransactionBase64'])[1]
            fetch('fee','getFeeForMessage',[base64.b64encode(raw_message).decode(),opts])
        fetch('genesisAfter','getGenesisHash',[])
    except StateError as exc:c['stoppedReason']=exc.reason
    except (ValueError,TypeError,KeyError,IndexError):c['stoppedReason']='invalid-capture-input-or-response'
    c.update(finishedAtMs=now(),rpcRequestsAttempted=len(client.calls))
    return c


def collect(*, pool=None, packet=None, opener=None, now=None, monotonic=None):
    return _collect(pool=pool,packet=packet,opener=opener,now=now,monotonic=monotonic,baseline=BASELINE)
