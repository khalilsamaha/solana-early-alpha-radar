"""Bounded public RPC evidence reader. No signing, submission, or ledger mutation."""
import json
import urllib.error
import urllib.request

ENDPOINTS = {'devnet': 'https://api.devnet.solana.com', 'mainnet-beta': 'https://api.mainnet-beta.solana.com'}
MAX_BYTES = 4 * 1024 * 1024
ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
U64 = 2**64 - 1


def base58(value, length):
    if not isinstance(value, str) or not 1 <= len(value) <= 90:
        raise ValueError('Invalid public identifier')
    n = 0
    for c in value:
        if c not in ALPHABET:
            raise ValueError('Invalid public identifier')
        n = n * 58 + ALPHABET.index(c)
    decoded = b'\0' * (len(value) - len(value.lstrip('1')))
    decoded += n.to_bytes((n.bit_length() + 7) // 8, 'big')
    if len(decoded) != length:
        raise ValueError('Wrong public identifier length')
    return value


def integer(v, ceiling=U64):
    return type(v) is int and 0 <= v <= ceiling


def atomic(v):
    if not isinstance(v, str) or not v.isascii() or not v.isdecimal() or len(v) > 20 or (len(v) > 1 and v[0] == '0') or int(v) > U64:
        raise ValueError('Invalid atomic amount')
    return int(v)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def rpc(network, method, params, request_id, opener=None):
    if network not in ENDPOINTS or method not in ('getSignatureStatuses', 'getTransaction'):
        raise ValueError('RPC operation not allowed')
    request = urllib.request.Request(ENDPOINTS[network], method='POST', headers={'Content-Type': 'application/json'},
        data=json.dumps({'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params}).encode())
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=10) as response:
            body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            return {'state': 'response-too-large'}
        data = json.loads(body, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(data, dict) or data.get('jsonrpc') != '2.0' or type(data.get('id')) is not int or data['id'] != request_id:
            return {'state': 'invalid-rpc-envelope'}
        if 'error' in data:
            return {'state': 'rpc-error'}  # Never export arbitrary provider messages.
        return {'state': 'received', 'result': data['result']} if 'result' in data else {'state': 'invalid-rpc-envelope'}
    except urllib.error.HTTPError as e:
        return {'state': 'http-error', 'httpStatus': e.code}
    except (urllib.error.URLError, TimeoutError, OSError):
        return {'state': 'network-error'}
    except (ValueError, TypeError, RecursionError):
        return {'state': 'invalid-json'}


def fetch(network, signature, opener=None):
    base58(signature, 64)
    # Two bounded requests, no retry. Finalized transaction retrieval can legitimately return null.
    status = rpc(network, 'getSignatureStatuses', [[signature], {'searchTransactionHistory': True}], 1, opener)
    tx = rpc(network, 'getTransaction', [signature, {'commitment': 'finalized', 'encoding': 'json',
                                                  'maxSupportedTransactionVersion': 0}], 2, opener)
    return {'signatureStatus': status, 'transaction': tx}


def token_balances(meta, keys, wallet, mint):
    """Missing creation/closure sides stay unknown; never infer a zero balance."""
    result = {'state': 'unavailable', 'deltaAtomic': None, 'decimals': None, 'accounts': []}
    maps = []
    for side in ('preTokenBalances', 'postTokenBalances'):
        raw = meta.get(side)
        if not isinstance(raw, list) or len(raw) > len(keys):
            return result
        by_index = {}
        for row in raw:
            if not isinstance(row, dict) or not integer(row.get('accountIndex'), len(keys) - 1):
                raise ValueError('Invalid token balance index')
            idx = row['accountIndex']
            if idx in by_index:
                raise ValueError('Duplicate token balance index')
            base58(row.get('mint'), 32)
            # Unknown ownership can conceal a relevant wallet account.
            if not isinstance(row.get('owner'), str):
                return result
            base58(row['owner'], 32)
            amount = row.get('uiTokenAmount')
            if not isinstance(amount, dict) or not integer(amount.get('decimals'), 255):
                raise ValueError('Invalid token decimals')
            by_index[idx] = (row['owner'], row['mint'], amount['decimals'], atomic(amount.get('amount')))
        maps.append(by_index)
    pre, post = maps
    selected = {i for balances in maps for i, row in balances.items() if row[:2] == (wallet, mint)}
    if not selected:
        return result
    accounts, decimals = [], set()
    for i in sorted(selected):
        a, b = pre.get(i), post.get(i)
        if a is None or b is None or a[:3] != b[:3]:
            return {**result, 'state': 'incomplete-account-lifecycle-or-identity'}
        decimals.add(a[2])
        accounts.append({'account': keys[i], 'preAtomic': str(a[3]), 'postAtomic': str(b[3]), 'deltaAtomic': str(b[3] - a[3])})
    if len(decimals) != 1:
        raise ValueError('Inconsistent mint decimals')
    return {'state': 'recorded', 'decimals': decimals.pop(), 'accounts': accounts,
            'deltaAtomic': str(sum(int(a['deltaAtomic']) for a in accounts))}


def reconcile(bundle, signature, wallet, mint):
    for value, size in ((signature, 64), (wallet, 32), (mint, 32)):
        base58(value, size)
    result = {'format': 'chain-evidence-1', 'signature': signature, 'wallet': wallet, 'mint': mint,
              'state': 'unknown', 'executionApproved': False, 'resubmitAllowed': False, 'ledgerUpdated': False,
              'nativeBalance': None, 'tokenBalance': None,
              'limitations': [
                  'RPC-reported evidence is not independent cryptographic verification or intent validation.',
                  'Null or missing evidence never proves failure, expiry, non-submission or permission to resubmit.',
                  'Finalized success does not prove a swap, intended execution, security or profitability.',
                  'Native balance change includes fees, rent and transfers; token amounts are raw and are not spendability checks.',
                  'Account creation/closure, missing ownership and unsupported data leave token reconciliation unknown.',
                  'No simulation or production ledger is updated. This reader never signs or sends transactions.']}
    try:
        status_envelope, tx_envelope = bundle['signatureStatus'], bundle['transaction']
        result['requests'] = {k: bundle[k].get('state') for k in ('signatureStatus', 'transaction')}
        if status_envelope.get('state') != 'received' or tx_envelope.get('state') != 'received':
            result['state'] = 'rpc-evidence-unavailable'
            return result
        statuses = status_envelope['result']
        if not isinstance(statuses, dict) or not isinstance(statuses.get('value'), list) or len(statuses['value']) != 1:
            raise ValueError('Invalid status result')
        status, tx = statuses['value'][0], tx_envelope['result']
        if status is None:
            result['state'] = 'not-found-unknown' if tx is None else 'inconsistent-evidence'
            return result
        if not isinstance(status, dict) or 'err' not in status or not integer(status.get('slot')):
            raise ValueError('Invalid signature status')
        context = statuses.get('context', {}).get('slot')
        if not integer(context) or context < status['slot']:
            raise ValueError('Invalid status context')
        result['confirmationStatus'] = status.get('confirmationStatus') if status.get('confirmationStatus') in ('processed', 'confirmed', 'finalized') else None
        if status.get('confirmationStatus') != 'finalized':
            result['state'] = 'provisional-or-unconfirmed'
            return result
        if tx is None:
            result['state'] = 'finalized-transaction-unavailable'
            return result
        if tx.get('version') != 'legacy' and not (type(tx.get('version')) is int and tx['version'] == 0):
            raise ValueError('Unsupported transaction version')
        if not integer(tx.get('slot')) or tx['slot'] != status['slot']:
            raise ValueError('Transaction slot mismatch')
        transaction = tx['transaction']
        signatures = transaction['signatures']
        if not isinstance(signatures, list) or not signatures or signatures[0] != signature:
            raise ValueError('Transaction signature mismatch')
        for sig in signatures:
            base58(sig, 64)
        message, meta = transaction['message'], tx['meta']
        if not isinstance(meta, dict) or 'err' not in meta or meta['err'] != status['err']:
            raise ValueError('Transaction status disagreement')
        static = message['accountKeys']
        if not isinstance(static, list) or not 1 <= len(static) <= 256:
            raise ValueError('Invalid account keys')
        loaded = meta.get('loadedAddresses')
        if tx['version'] == 0 and not isinstance(loaded, dict):
            raise ValueError('Missing loaded addresses')
        loaded = loaded or {'writable': [], 'readonly': []}
        if not all(isinstance(loaded.get(k), list) for k in ('writable', 'readonly')):
            raise ValueError('Invalid loaded addresses')
        keys = static + loaded['writable'] + loaded['readonly']
        if tx['version'] == 'legacy' and len(keys) != len(static):
            raise ValueError('Unexpected legacy loaded addresses')
        if len(keys) > 256 or len(set(keys)) != len(keys):
            raise ValueError('Duplicate or excessive account keys')
        for key in keys:
            base58(key, 32)
        required = message['header']['numRequiredSignatures']
        if not integer(required, len(static)) or required < 1 or required != len(signatures):
            raise ValueError('Invalid signature header')
        if wallet not in keys or keys.index(wallet) >= required:
            result['state'] = 'wallet-not-a-required-signer'
            return result
        before, after, fee = meta['preBalances'], meta['postBalances'], meta['fee']
        if not all(isinstance(b, list) and len(b) == len(keys) and all(integer(x) for x in b) for b in (before, after)) or not integer(fee):
            raise ValueError('Invalid native balances')
        idx = keys.index(wallet)
        result.update(state='finalized-success' if meta['err'] is None else 'finalized-failed', slot=tx['slot'],
            nativeBalance={'preLamports': str(before[idx]), 'postLamports': str(after[idx]),
                           'deltaLamports': str(after[idx] - before[idx]), 'transactionFeeLamports': str(fee),
                           'walletIsFeePayer': idx == 0},
            tokenBalance=token_balances(meta, keys, wallet, mint))
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        result.update(state='inconsistent-or-unsupported-evidence', nativeBalance=None, tokenBalance=None)
    return result
