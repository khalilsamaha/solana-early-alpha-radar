"""Current RPC lookup account consistency, never a historical-state or execution proof."""
import base64
import hashlib
import json
import time

from recorded_capture import Client, GENESIS, MAX_CAPTURE
from review import review, require, CheckError
from wire import decode_wire, b58
from reader import integer
from reconcile import digest

PROGRAM = 'AddressLookupTab1e1111111111111111111111111'
MAX_TABLES = 32
MAX_DATA = 56 + 256 * 32
U64 = 2**64 - 1


class LookupClient(Client):
    METHODS = ('getGenesisHash', 'getMultipleAccounts')
    REQUEST_CAP = 3

    def request(self, method, params):
        result = super().request(method, params)
        if method == 'getMultipleAccounts' and result['state'] == 'received':
            try:
                value = result['result']
                rows = value['value']
                if not isinstance(rows, list) or len(rows) != len(params[0]): raise ValueError()
                projected = []
                for row in rows:
                    if row is None: projected.append(None); continue
                    if not isinstance(row, dict): raise ValueError()
                    data = row.get('data')
                    if not isinstance(data, list) or len(data) != 2 or not isinstance(data[0], str) or len(data[0]) > 11000:
                        raise ValueError()
                    projected.append({k: row[k] for k in ('owner', 'executable', 'data') if k in row})
                result['result'] = {'context': {'slot': value['context']['slot']}, 'value': projected}
            except (KeyError, TypeError, ValueError):
                result = {'state': 'invalid-account-response'}
                self.calls[-1]['state'] = result['state']
        return result


def source_details(source):
    checked = review(source)
    require(checked['state'] in ('signed-transaction-consistent', 'signed-message-consistent-lookup-unverified'),
            'source-identity-not-verified', 'unknown')
    # Derive lookup keys and indices directly from authenticated wire bytes.
    message = decode_wire(source['evidence']['transactionBase64']['result']['transaction'][0])[4]['transaction']['message']
    descriptors = message.get('addressTableLookups', [])
    keys = list(dict.fromkeys(d['accountKey'] for d in descriptors))
    require(len(keys) <= MAX_TABLES, 'lookup-table-cap', 'unsupported')
    return checked, descriptors, keys


def collect_lookups(source, opener=None):
    checked, _, keys = source_details(source)
    client = LookupClient(source['network'], opener)
    ev = {k: {'state': 'not-requested'} for k in ('genesisBefore', 'accounts', 'genesisAfter')}
    captured = {'format': 'lookup-capture-1', 'sourceCaptureSha256': digest(source),
        'network': source['network'], 'signature': checked['signature'], 'transactionSlot': checked['slot'],
        'accountKeys': keys, 'startedAtMs': time.time_ns() // 1000000, 'evidence': ev, 'requests': client.calls}
    if keys:
        ev['genesisBefore'] = client.request('getGenesisHash', [])
        if ev['genesisBefore'] == {'state': 'received', 'result': GENESIS[source['network']]}:
            ev['accounts'] = client.request('getMultipleAccounts', [keys,
                {'encoding': 'base64', 'commitment': 'finalized', 'minContextSlot': checked['slot']}])
            if ev['accounts']['state'] == 'received':
                ev['genesisAfter'] = client.request('getGenesisHash', [])
    captured.update(finishedAtMs=time.time_ns() // 1000000, rpcRequestsAttempted=len(client.calls), transactionsSent=0)
    return captured


def decode_account(account, context):
    require(account is not None, 'lookup-account-unavailable', 'unknown')
    require(isinstance(account, dict), 'invalid-account', 'invalid-input')
    require(account.get('owner') == PROGRAM, 'lookup-owner-mismatch')
    require(account.get('executable') is False, 'lookup-account-executable')
    data = account.get('data')
    require(isinstance(data, list) and len(data) == 2 and data[1] == 'base64', 'account-encoding', 'unsupported')
    require(isinstance(data[0], str) and len(data[0]) <= 11000, 'account-size-cap', 'invalid-input')
    raw = base64.b64decode(data[0], validate=True)
    require(base64.b64encode(raw).decode() == data[0] and 56 <= len(raw) <= MAX_DATA and
            (len(raw) - 56) % 32 == 0, 'invalid-account-layout', 'invalid-input')
    require(int.from_bytes(raw[:4], 'little') == 1, 'unsupported-table-state', 'unsupported')
    deactivation = int.from_bytes(raw[4:12], 'little')
    extended = int.from_bytes(raw[12:20], 'little')
    start, authority = raw[20], raw[21]
    require(authority in (0, 1), 'invalid-authority-option', 'invalid-input')
    # Bincode Option<Pubkey> + u16 padding. Metadata writer zeroes leftovers.
    padding = raw[54:56] if authority else raw[22:56]
    require(not any(padding), 'unsupported-metadata-padding', 'unsupported')
    addresses = [b58(raw[i:i+32]) for i in range(56, len(raw), 32)]
    require(start <= len(addresses) and extended <= context and
            (deactivation == U64 or extended <= deactivation <= context), 'invalid-metadata-slots', 'invalid-input')
    return {'addresses': addresses, 'lastExtendedSlot': extended, 'lastExtendedStartIndex': start,
        'deactivationSlot': deactivation, 'authorityPresent': bool(authority),
        'dataSha256': hashlib.sha256(raw).hexdigest()}


def review_lookups(source, capture):
    result = {'format': 'lookup-review-1', 'state': 'unknown', 'reason': None,
        'addressesMatched': False, 'historicalStateProven': False, 'executionApproved': False,
        'ledgerUpdated': False, 'resubmitAllowed': False, 'reviewNetworkRequests': 0,
        'limitations': [
            'Account bytes, owner, cluster and context are reports from one RPC endpoint, not independent state proofs.',
            'minContextSlot is a lower bound, not a request for historical account state.',
            'Matching current addresses cannot establish historical table existence, full lifecycle or program semantics.',
            'Later extension and deactivation leave historical availability unknown; no slot-hash history is reconstructed.',
            'This report never relaxes journal ALT rejection or authorizes execution.']}
    try:
        checked, descriptors, keys = source_details(source)
        require(isinstance(capture, dict) and capture.get('format') == 'lookup-capture-1', 'capture-format', 'invalid-input')
        require(len(json.dumps(capture, allow_nan=False)) <= MAX_CAPTURE, 'capture-byte-cap', 'invalid-input')
        require(capture['sourceCaptureSha256'] == digest(source) and capture['network'] == source['network'] and
                capture['signature'] == checked['signature'] and type(capture['transactionSlot']) is int and
                capture['transactionSlot'] == checked['slot'] and capture['accountKeys'] == keys, 'capture-source-disagreement')
        require(integer(capture['startedAtMs']) and integer(capture['finishedAtMs']) and
                capture['startedAtMs'] <= capture['finishedAtMs'], 'capture-time-invalid', 'invalid-input')
        result.update(sourceCaptureSha256=digest(source), lookupCaptureSha256=digest(capture),
            signature=checked['signature'], network=source['network'], transactionSlot=checked['slot'])
        if not keys:
            result.update(state='not-required', reason='no-signed-lookup-references')
            return result
        ev = capture['evidence']
        for key in ('genesisBefore', 'genesisAfter'):
            require(ev[key]['state'] == 'received', 'cluster-evidence-incomplete', 'unknown')
            require(ev[key].get('result') == GENESIS[source['network']], 'network-genesis-mismatch')
        require(ev['accounts']['state'] == 'received', 'account-evidence-unavailable', 'unknown')
        response = ev['accounts']['result']; context = response['context']['slot']; rows = response['value']
        require(integer(context) and context >= checked['slot'], 'account-context-before-transaction')
        require(isinstance(rows, list) and len(rows) == len(keys), 'account-count-mismatch')
        tables = {k: decode_account(v, context) for k, v in zip(keys, rows)}
        resolved = {'writable': [], 'readonly': []}
        summaries = []
        for descriptor in descriptors:
            table = tables[descriptor['accountKey']]
            indices = descriptor['writableIndexes'] + descriptor['readonlyIndexes']
            require(all(i < len(table['addresses']) for i in indices), 'lookup-index-out-of-range')
            for kind in resolved:
                resolved[kind].extend(table['addresses'][i] for i in descriptor[kind + 'Indexes'])
            extended = table['lastExtendedSlot']; txslot = checked['slot']
            temporal = 'compatible-with-reported-metadata'
            if extended > txslot: temporal = 'unknown-later-extension'
            elif extended == txslot and any(i >= table['lastExtendedStartIndex'] for i in indices):
                temporal = 'incompatible-same-slot-extension'
            if table['deactivationSlot'] < txslot: temporal = 'unknown-deactivation-history'
            summaries.append({'accountKey': descriptor['accountKey'], 'addressCount': len(table['addresses']),
                **{k: v for k, v in table.items() if k != 'addresses'}, 'temporalAssessment': temporal})
        result.update(accountContextSlot=context, tables=summaries, resolvedAddressCount=sum(map(len, resolved.values())))
        expected = source['evidence']['transactionJson']['result']['meta']['loadedAddresses']
        require(resolved == expected, 'loaded-address-disagreement')
        result['addressesMatched'] = True
        require(not any(t['temporalAssessment'] == 'incompatible-same-slot-extension' for t in summaries),
                'same-slot-address-not-active')
        result.update(state='current-lookup-addresses-consistent',
            temporalAssessment='unknown' if any(t['temporalAssessment'].startswith('unknown') for t in summaries)
            else 'compatible-with-reported-metadata')
    except CheckError as e:
        result.update(state=e.state, reason=e.reason)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError, RecursionError):
        result.update(state='invalid-input', reason='malformed-lookup-evidence')
    return result
