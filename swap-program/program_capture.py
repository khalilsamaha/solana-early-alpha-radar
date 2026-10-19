"""Five bounded read requests for one fixed devnet program; no retry or signer."""
import time
from program import (PROGRAM, GENESIS, MAX_BASE64, StateError, integer, snapshot,
                     program_pointer)
from recorded_capture import Client


class ProgramClient(Client):
    METHODS = ('getGenesisHash', 'getMultipleAccounts', 'getBlockTime')
    REQUEST_CAP = 5

    def __init__(self, opener=None):
        super().__init__('devnet', opener)

    def request(self, method, params):
        if method == 'getMultipleAccounts':
            if (type(params) is not list or len(params) != 2 or type(params[0]) is not list or
                    len(params[0]) not in (1, 2) or params[0][0] != PROGRAM or
                    params[1].get('encoding') != 'base64' or params[1].get('commitment') != 'finalized' or
                    'dataSlice' in params[1]):
                raise ValueError('Unsupported account request')
        item = super().request(method, params)
        if item['state'] != 'received':
            return item
        try:
            value = item['result']
            if method == 'getMultipleAccounts':
                slot, rows = snapshot(value, len(params[0]))
                selected = []
                for row in rows:
                    if row is None:
                        selected.append(None)
                        continue
                    if type(row) is not dict:
                        raise ValueError()
                    data = row.get('data')
                    if (type(data) is not list or len(data) != 2 or data[1] != 'base64' or
                            type(data[0]) is not str or len(data[0]) > MAX_BASE64):
                        raise ValueError()
                    selected.append({k: row[k] for k in ('data', 'owner', 'executable', 'lamports') if k in row})
                item['result'] = {'context': {'slot': slot}, 'value': selected}
            elif method == 'getGenesisHash':
                if type(value) is not str or len(value) > 44:
                    raise ValueError()
            elif value is not None and not integer(value):
                raise ValueError()
        except (StateError, ValueError, TypeError, KeyError):
            item = {'state': 'invalid-program-response'}
            self.calls[-1]['state'] = item['state']
        return item


def collect(*, opener=None, now=None, monotonic=None):
    now = now or (lambda: time.time_ns() // 1000000)
    monotonic = monotonic or time.monotonic
    start, start_mono = now(), monotonic()
    client = ProgramClient(opener)
    ev = {n: {'state': 'not-requested'} for n in
          ('genesisBefore', 'bootstrap', 'accounts', 'blockTime', 'genesisAfter')}
    capture = dict(format='swap-program-capture-1', network='devnet', program=PROGRAM,
                   origin='public-rpc-capture', startedAtMs=start, evidence=ev, requests=client.calls,
                   transactionsSent=0, signaturesCreated=0, ledgerUpdated=False)

    def fetch(name, method, params):
        if monotonic() - start_mono >= 30:
            raise StateError('capture-time-budget', 'unavailable')
        ev[name] = client.request(method, params)
        if ev[name]['state'] != 'received':
            raise StateError('rpc-stopped-' + name, 'unavailable')
        return ev[name]['result']

    try:
        if fetch('genesisBefore', 'getGenesisHash', []) != GENESIS['devnet']:
            raise StateError('wrong-cluster')
        options = {'encoding': 'base64', 'commitment': 'finalized'}
        first = fetch('bootstrap', 'getMultipleAccounts', [[PROGRAM], options])
        slot, rows = snapshot(first, 1)
        address = program_pointer(rows[0])
        capture['accountKeys'] = [PROGRAM, address]
        batch = fetch('accounts', 'getMultipleAccounts', [capture['accountKeys'], dict(options, minContextSlot=slot)])
        final_slot, final_rows = snapshot(batch, 2)
        if final_slot < slot:
            raise StateError('snapshot-slot-regression')
        if program_pointer(final_rows[0]) != address:
            raise StateError('program-pointer-changed')
        capture['blockTimeSlot'] = final_slot
        fetch('blockTime', 'getBlockTime', [final_slot])
        fetch('genesisAfter', 'getGenesisHash', [])
    except StateError as exc:
        capture['stoppedReason'] = exc.reason
    except (ValueError, TypeError, KeyError, IndexError):
        capture['stoppedReason'] = 'invalid-capture-input-or-response'
    capture.update(finishedAtMs=now(), rpcRequestsAttempted=len(client.calls))
    return capture
