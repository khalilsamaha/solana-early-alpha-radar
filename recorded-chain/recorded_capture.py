"""Bounded, public, read-only Solana transaction capture. Never retries or sends."""
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'chain-reader'))
from reader import ENDPOINTS, NoRedirect, base58, integer

GENESIS = {
    'devnet': 'EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG',
    'mainnet-beta': '5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d',
}
SYSTEM = '11111111111111111111111111111111'
TOKEN = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
MAX_RESPONSE = 4 * 1024 * 1024
MAX_CAPTURE = 20 * 1024 * 1024
META = ('err', 'fee', 'preBalances', 'postBalances', 'preTokenBalances', 'postTokenBalances',
        'innerInstructions', 'loadedAddresses')


def unique(pairs):
    data = {}
    for key, value in pairs:
        if key in data: raise ValueError('Duplicate JSON key')
        data[key] = value
    return data


def loads(raw):
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def project_transaction(tx):
    if tx is None: return None
    if not isinstance(tx, dict): raise ValueError('Invalid transaction result')
    result = {k: tx[k] for k in ('slot', 'version', 'transaction') if k in tx}
    meta = tx.get('meta')
    if meta is not None and not isinstance(meta, dict): raise ValueError('Invalid metadata')
    result['meta'] = {k: meta[k] for k in META if k in meta} if meta is not None else None
    # Logs, memo text from discovery, returnData, arbitrary provider error text and
    # unrelated account/program data are never copied into the capture.
    return result


class Client:
    METHODS = ('getGenesisHash', 'getSignaturesForAddress', 'getTransaction', 'getSignatureStatuses')
    REQUEST_CAP = 6
    SIGNATURE_LIST_CAP = 1

    def __init__(self, network, opener=None):
        if network not in ENDPOINTS: raise ValueError('Unsupported network')
        self.network, self.calls = network, []
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, method, params):
        if method not in self.METHODS:
            raise ValueError('RPC method not allowed')
        if len(self.calls) >= self.REQUEST_CAP: raise ValueError('RPC request cap')
        request_id = len(self.calls) + 1
        record = {'method': method, 'id': request_id}
        if method == 'getTransaction': record['encoding'] = params[1]['encoding']
        self.calls.append(record)
        request = urllib.request.Request(ENDPOINTS[self.network], method='POST',
            headers={'Content-Type': 'application/json'}, data=json.dumps({
                'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params}).encode())
        started = time.monotonic()
        try:
            with self.opener.open(request, timeout=10) as response:
                raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE: result = {'state': 'response-too-large'}
            else:
                envelope = loads(raw)
                if not isinstance(envelope, dict) or envelope.get('jsonrpc') != '2.0' or type(envelope.get('id')) is not int or envelope['id'] != request_id:
                    result = {'state': 'invalid-rpc-envelope'}
                elif 'error' in envelope: result = {'state': 'rpc-error'}
                elif 'result' not in envelope: result = {'state': 'invalid-rpc-envelope'}
                else:
                    value = envelope['result']
                    if method == 'getTransaction': value = project_transaction(value)
                    elif method == 'getSignaturesForAddress':
                        if not isinstance(value, list) or len(value) > self.SIGNATURE_LIST_CAP: raise ValueError('Discovery cap')
                        value = [{k: row[k] for k in ('signature', 'slot', 'err', 'confirmationStatus') if k in row} for row in value]
                    result = {'state': 'received', 'result': value}
        except urllib.error.HTTPError as e:
            result = {'state': 'http-error', 'httpStatus': e.code}
        except (urllib.error.URLError, TimeoutError, OSError):
            result = {'state': 'network-error'}
        except (ValueError, TypeError, KeyError, RecursionError):
            result = {'state': 'invalid-response'}
        record.update(state=result['state'], elapsedMs=round((time.monotonic() - started) * 1000))
        return result


def collect(network='devnet', signature=None, sample=False, opener=None, *, sample_program=SYSTEM):
    if network not in GENESIS or sample != (signature is None) or (sample and network != 'devnet'):
        raise ValueError('Use explicit signature/network or one devnet sample')
    if sample_program not in (SYSTEM, TOKEN) or (not sample and sample_program != SYSTEM):
        raise ValueError('Unsupported sample program')
    if signature is not None: base58(signature, 64)
    client = Client(network, opener)
    evidence = {k: {'state': 'not-requested'} for k in
                ('genesisBefore', 'discovery', 'transactionJson', 'transactionBase64', 'signatureStatus', 'genesisAfter')}
    report = {'format': 'recorded-chain-capture-1', 'origin': 'public-rpc-capture', 'network': network,
        'selection': ('recent-token-program-devnet' if sample_program == TOKEN else 'recent-system-program-devnet') if sample else 'explicit-signature',
        'signature': signature, 'startedAtMs': time.time_ns() // 1000000,
        'evidence': evidence, 'requests': client.calls, 'transactionsSent': 0, 'ledgerUpdated': False}

    def fetch(key, method, params):
        evidence[key] = client.request(method, params)
        return evidence[key]['state'] == 'received'

    def sequence():
        if not fetch('genesisBefore', 'getGenesisHash', []): return
        if evidence['genesisBefore']['result'] != GENESIS[network]: return
        if sample:
            if not fetch('discovery', 'getSignaturesForAddress', [sample_program, {'limit': 1, 'commitment': 'finalized'}]): return
            rows = evidence['discovery']['result']
            if not rows: return
            candidate = rows[0]
            try:
                base58(candidate.get('signature'), 64)
                if candidate.get('confirmationStatus') != 'finalized' or not integer(candidate.get('slot')): return
            except ValueError: return
            report['signature'] = candidate['signature']
        for key, encoding in (('transactionJson', 'json'), ('transactionBase64', 'base64')):
            if not fetch(key, 'getTransaction', [report['signature'], {
                'commitment': 'finalized', 'encoding': encoding, 'maxSupportedTransactionVersion': 0}]): return
        if not fetch('signatureStatus', 'getSignatureStatuses', [[report['signature']], {'searchTransactionHistory': True}]): return
        fetch('genesisAfter', 'getGenesisHash', [])

    sequence()
    report['finishedAtMs'] = time.time_ns() // 1000000
    report['rpcRequestsAttempted'] = len(client.calls)
    return report
