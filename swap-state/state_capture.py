"""Bounded devnet reads, one latest transaction hint, no retries or transaction submission."""
import base64
import copy
import time
from state import (PROGRAM, GENESIS, StateError, decode_pool, account_keys, snapshot,
                   discover_pool, key, validate, integer, digest)
from contract import decode_wire
from recorded_capture import Client


class StateClient(Client):
    METHODS = ('getGenesisHash','getSignaturesForAddress','getTransaction','getMultipleAccounts',
               'getBlockTime','isBlockhashValid','getFeeForMessage')
    REQUEST_CAP = 7

    def __init__(self, opener=None):
        super().__init__('devnet',opener)

    def request(self, method, params):
        if method == 'getMultipleAccounts' and (not isinstance(params,list) or not params or
                not isinstance(params[0],list) or not 1 <= len(params[0]) <= 11):
            raise ValueError('Account request cap')
        result = super().request(method,params)
        if method == 'getMultipleAccounts' and result['state'] == 'received':
            try:
                slot, rows = snapshot(result['result'],len(params[0]))
                selected = []
                for row in rows:
                    if row is None:
                        selected.append(None); continue
                    if type(row) is not dict: raise ValueError()
                    data = row.get('data')
                    if type(data) is not list or len(data) != 2 or data[1] != 'base64' or type(data[0]) is not str or len(data[0]) > 6000:
                        raise ValueError()
                    selected.append({k:row[k] for k in ('data','owner','executable','lamports') if k in row})
                result['result'] = {'context':{'slot':slot},'value':selected}
            except (KeyError,TypeError,ValueError):
                result = {'state':'invalid-account-response'}
                self.calls[-1]['state'] = result['state']
        elif method in ('getFeeForMessage','isBlockhashValid') and result['state'] == 'received':
            try:
                v = result['result']; slot = v['context']['slot']
                if not integer(slot): raise ValueError()
                value = v['value']
                if method == 'getFeeForMessage' and value is not None and not integer(value): raise ValueError()
                if method == 'isBlockhashValid' and type(value) is not bool: raise ValueError()
                result['result'] = {'context':{'slot':slot},'value':value}
            except (KeyError,TypeError,ValueError):
                result = {'state':'invalid-context-response'}
                self.calls[-1]['state'] = result['state']
        elif method in ('getGenesisHash','getBlockTime') and result['state'] == 'received':
            value = result['result']
            valid = type(value) is str and len(value) <= 44 if method == 'getGenesisHash' else value is None or integer(value)
            if not valid:
                result = {'state':'invalid-scalar-response'}
                self.calls[-1]['state'] = result['state']
        return result


def collect(*, pool=None, sample=False, packet=None, opener=None, now=None, monotonic=None):
    now = now or (lambda:time.time_ns()//1000000)
    monotonic = monotonic or time.monotonic
    if int(pool is not None)+int(bool(sample))+int(packet is not None) != 1:
        raise ValueError('Select one capture mode')
    # Freeze public caller data before any injectable transport or concurrent caller can mutate it.
    packet = copy.deepcopy(packet)
    start = now(); start_mono = monotonic()
    if packet is not None:
        checked = validate(packet,now_ms=start)
        if checked['state'] != 'instruction-policy-match': raise ValueError('Packet not current or supported')
        pool = packet['policy']['accounts']['pool']
    if pool is not None: key(pool)
    client = StateClient(opener)
    ev = {name:{'state':'not-requested'} for name in ('genesisBefore','discovery','transaction','bootstrap',
        'accounts','blockTime','blockhash','fee','genesisAfter')}
    capture = {'format':'cpmm-state-capture-1','network':'devnet','origin':'public-rpc-capture',
               'selection':'prior-packet' if packet is not None else 'latest-program-transaction' if sample else 'explicit-pool',
               'pool':pool,'packet':packet,'startedAtMs':start,'evidence':ev,'requests':client.calls,
               'transactionsSent':0,'signaturesCreated':0,'ledgerUpdated':False}

    def fetch(name, method, params):
        if monotonic()-start_mono >= 30:
            raise StateError('capture-time-budget','unavailable')
        if packet is not None and now() >= packet['policy']['expiresAtMs']:
            raise StateError('packet-expired-during-capture','unavailable')
        ev[name] = client.request(method,params)
        if ev[name]['state'] != 'received': raise StateError('rpc-stopped-'+name,'unavailable')
        return ev[name]['result']

    try:
        if fetch('genesisBefore','getGenesisHash',[]) != GENESIS['devnet']:
            raise StateError('wrong-cluster')
        minimum_slot = 0
        if sample:
            rows = fetch('discovery','getSignaturesForAddress',[PROGRAM,{'limit':1,'commitment':'finalized'}])
            if not rows or rows[0].get('confirmationStatus') != 'finalized' or rows[0].get('err') is not None:
                raise StateError('no-successful-finalized-latest-transaction','unavailable')
            from reader import base58
            base58(rows[0].get('signature'),64)
            tx = fetch('transaction','getTransaction',[rows[0]['signature'],{
                'encoding':'json','commitment':'finalized','maxSupportedTransactionVersion':0}])
            pool = discover_pool(rows,tx); capture['pool'] = pool; minimum_slot = rows[0]['slot']
        first = fetch('bootstrap','getMultipleAccounts',[[pool],{
            'encoding':'base64','commitment':'finalized','minContextSlot':minimum_slot}])
        first_slot, first_rows = snapshot(first,1)
        if first_slot < minimum_slot: raise StateError('discovery-slot-regression')
        parsed = decode_pool(first_rows[0])
        keys = account_keys(pool,parsed,packet); capture['accountKeys'] = keys
        batch = fetch('accounts','getMultipleAccounts',[keys,{
            'encoding':'base64','commitment':'finalized','minContextSlot':first_slot}])
        slot, _ = snapshot(batch,len(keys)); capture['blockTimeSlot'] = slot
        if slot < first_slot: raise StateError('snapshot-slot-regression')
        fetch('blockTime','getBlockTime',[slot])
        if packet is not None:
            options = {'commitment':'finalized','minContextSlot':slot}
            fetch('blockhash','isBlockhashValid',[packet['policy']['blockhash'],options])
            message = decode_wire(packet['unsignedTransactionBase64'])[1]
            capture['messageSha256'] = checked['wireMessageSha256']
            fetch('fee','getFeeForMessage',[base64.b64encode(message).decode(),options])
        fetch('genesisAfter','getGenesisHash',[])
    except StateError as exc:
        capture['stoppedReason'] = exc.reason
    except (ValueError,TypeError,KeyError,IndexError):
        capture['stoppedReason'] = 'invalid-capture-input-or-response'
    capture.update(finishedAtMs=now(),rpcRequestsAttempted=len(client.calls))
    return capture
