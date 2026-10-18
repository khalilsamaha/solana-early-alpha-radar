"""Offline comparison of a prior declared intent with RPC-reported transaction evidence.

No transaction construction, signing, submission, RPC or execution ledger access.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'chain-reader'))
from reader import ALPHABET, U64, atomic, base58, integer, reconcile as chain_evidence

TOKEN = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
SYSTEM = '11111111111111111111111111111111'
NATIVE = 'So11111111111111111111111111111111111111112'
MAX_BYTES = 4 * 1024 * 1024


class EvidenceError(Exception):
    def __init__(self, state, reason):
        self.state, self.reason = state, reason


def require(condition, reason, state='mismatch'):
    if not condition:
        raise EvidenceError(state, reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def decode(value):
    require(isinstance(value, str) and len(value) <= 1800, 'invalid-instruction-data', 'unsupported')
    n = 0
    for c in value:
        require(c in ALPHABET, 'invalid-instruction-data', 'unsupported')
        n = n * 58 + ALPHABET.index(c)
    raw = b'\0' * (len(value) - len(value.lstrip('1'))) + n.to_bytes((n.bit_length() + 7) // 8, 'big')
    require(len(raw) <= 1232, 'instruction-byte-cap', 'unsupported')
    return raw


def compiled(row, keys):
    require(isinstance(row, dict) and set(row) <= {'programIdIndex', 'accounts', 'data', 'stackHeight'}, 'unsupported-instruction-shape', 'unsupported')
    require(integer(row.get('programIdIndex'), len(keys) - 1), 'instruction-program-index', 'unsupported')
    accounts = row.get('accounts')
    require(isinstance(accounts, list) and len(accounts) <= 256 and all(integer(i, len(keys) - 1) for i in accounts), 'instruction-account-index', 'unsupported')
    decode(row.get('data'))
    return {k: row[k] for k in ('programIdIndex', 'accounts', 'data')}


def binding(tx):
    """Canonical parsed-message binding, deliberately not the Solana wire-message hash."""
    version, message, meta = tx['version'], tx['transaction']['message'], tx['meta']
    require(version == 'legacy' or (type(version) is int and version == 0), 'unsupported-version', 'unsupported')
    require(set(message) <= {'accountKeys', 'header', 'instructions', 'recentBlockhash', 'addressTableLookups'}, 'unsupported-message-field', 'unsupported')
    static = message['accountKeys']; loaded = meta.get('loadedAddresses', {'writable': [], 'readonly': []})
    require(isinstance(static, list) and isinstance(loaded, dict) and set(loaded) == {'writable', 'readonly'}, 'invalid-account-keys', 'unsupported')
    require(all(isinstance(loaded[k], list) for k in loaded), 'invalid-loaded-addresses', 'unsupported')
    keys = static + loaded['writable'] + loaded['readonly']
    require(1 <= len(keys) <= 256 and len(set(keys)) == len(keys), 'duplicate-or-excessive-keys', 'unsupported')
    for key in keys:
        base58(key, 32)
    header = message['header']
    require(isinstance(header, dict) and set(header) == {'numRequiredSignatures', 'numReadonlySignedAccounts', 'numReadonlyUnsignedAccounts'}, 'invalid-header', 'unsupported')
    required = header['numRequiredSignatures']
    require(integer(required, len(static)) and required > 0 and integer(header['numReadonlySignedAccounts'], required - 1) and integer(header['numReadonlyUnsignedAccounts'], len(static) - required), 'invalid-header-counts', 'unsupported')
    base58(message['recentBlockhash'], 32)
    lookups = message.get('addressTableLookups', [])
    require(isinstance(lookups, list) and len(lookups) <= 256, 'invalid-lookups', 'unsupported')
    for lookup in lookups:
        require(isinstance(lookup, dict) and set(lookup) == {'accountKey', 'writableIndexes', 'readonlyIndexes'}, 'invalid-lookup', 'unsupported')
        base58(lookup['accountKey'], 32)
        for field in ('writableIndexes', 'readonlyIndexes'):
            require(isinstance(lookup[field], list) and len(lookup[field]) <= 256 and all(integer(i, 255) for i in lookup[field]), 'invalid-lookup-index', 'unsupported')
    require(len(loaded['writable']) == sum(len(l['writableIndexes']) for l in lookups) and len(loaded['readonly']) == sum(len(l['readonlyIndexes']) for l in lookups), 'loaded-address-count-mismatch', 'unsupported')
    require(version != 'legacy' or (not lookups and keys == static), 'legacy-loaded-addresses', 'unsupported')
    instructions = message['instructions']
    require(isinstance(instructions, list) and 1 <= len(instructions) <= 64, 'instruction-count', 'unsupported')
    normalized = {'bindingVersion': 'canonical-message-binding-1', 'version': version,
                  'message': {'accountKeys': static, 'header': header, 'recentBlockhash': message['recentBlockhash'],
                              'addressTableLookups': lookups, 'instructions': [compiled(i, keys) for i in instructions]},
                  'loadedAddresses': loaded}
    return digest(normalized), keys, normalized['message']['instructions']


def validate_intent(intent, *, wrapped_existing=False):
    fields = {'format', 'network', 'signature', 'wallet', 'messageSha256', 'preparedAtMs', 'walletPreLamports',
              'source', 'destination', 'inputAtomic', 'minimumOutputAtomic', 'maximumFeeLamports', 'maximumRentLamports'}
    require(isinstance(intent, dict) and set(intent) == fields and intent['format'] == 'transaction-intent-1', 'invalid-intent-schema', 'invalid-input')
    require(intent['network'] in ('devnet', 'mainnet-beta'), 'invalid-network', 'invalid-input')
    base58(intent['signature'], 64); base58(intent['wallet'], 32)
    require(isinstance(intent['messageSha256'], str) and re.fullmatch('[a-f0-9]{64}', intent['messageSha256']), 'invalid-message-binding', 'invalid-input')
    require(integer(intent['preparedAtMs']) and intent['preparedAtMs'] > 0, 'invalid-intent-time', 'invalid-input')
    for field in ('walletPreLamports', 'inputAtomic', 'minimumOutputAtomic', 'maximumFeeLamports', 'maximumRentLamports'):
        atomic(intent[field])
    require(atomic(intent['inputAtomic']) > 0 and atomic(intent['minimumOutputAtomic']) > 0, 'nonpositive-intent-amount', 'invalid-input')
    for field, lifecycles in (('source', ('existing', 'close')), ('destination', ('existing', 'create'))):
        account = intent[field]
        require(isinstance(account, dict) and set(account) == {'account', 'mint', 'programId', 'decimals', 'preAmountAtomic', 'lifecycle'}, 'invalid-token-contract', 'invalid-input')
        for key in ('account', 'mint', 'programId'): base58(account[key], 32)
        require(account['programId'] == TOKEN, 'token-program-not-supported', 'unsupported')
        if account['mint'] == NATIVE:
            require(wrapped_existing and account['lifecycle'] == 'existing', 'wrapped-native-lifecycle-not-supported' if wrapped_existing else 'wrapped-native-not-supported', 'unsupported')
            require(account['decimals'] == 9, 'wrapped-native-decimals-mismatch')
        require(integer(account['decimals'], 255) and account['lifecycle'] in lifecycles, 'invalid-token-contract', 'invalid-input')
        atomic(account['preAmountAtomic'])
        if account['lifecycle'] == 'create':
            require(atomic(account['preAmountAtomic']) == 0, 'new-account-prebalance-not-zero', 'invalid-input')
    require(intent['source']['account'] != intent['destination']['account'] and intent['source']['mint'] != intent['destination']['mint'], 'identical-input-output', 'invalid-input')
    require(intent['wallet'] not in (intent['source']['account'], intent['destination']['account']), 'wallet-token-account-overlap', 'invalid-input')


def token_maps(meta, keys):
    maps = []
    for field in ('preTokenBalances', 'postTokenBalances'):
        rows = meta.get(field)
        require(isinstance(rows, list) and len(rows) <= len(keys), 'token-balances-unavailable', 'unknown')
        mapped = {}
        for r in rows:
            require(isinstance(r, dict) and integer(r.get('accountIndex'), len(keys) - 1), 'invalid-token-index', 'unsupported')
            account = keys[r['accountIndex']]
            require(account not in mapped, 'duplicate-token-account', 'unsupported')
            require(all(isinstance(r.get(k), str) for k in ('owner', 'mint', 'programId')), 'token-identity-unavailable', 'unknown')
            for key in ('owner', 'mint', 'programId'): base58(r[key], 32)
            amount = r['uiTokenAmount']
            require(integer(amount['decimals'], 255), 'invalid-token-decimals', 'unsupported')
            mapped[account] = {'owner': r['owner'], 'mint': r['mint'], 'programId': r['programId'], 'decimals': amount['decimals'], 'amount': atomic(amount['amount'])}
        maps.append(mapped)
    return maps


def instructions(meta, outer, keys):
    inner = meta.get('innerInstructions')
    require(isinstance(inner, list) and len(inner) <= len(outer), 'inner-instructions-unavailable', 'unknown')
    grouped = {}
    for group in inner:
        require(isinstance(group, dict) and integer(group.get('index'), len(outer) - 1) and group['index'] not in grouped, 'invalid-inner-instruction-group', 'unsupported')
        rows = group['instructions']
        require(isinstance(rows, list) and len(rows) <= 256, 'inner-instruction-cap', 'unsupported')
        grouped[group['index']] = [compiled(r, keys) for r in rows]
    ordered = []
    for index, outer_row in enumerate(outer):
        for row in [outer_row] + grouped.get(index, []):
            ordered.append({'program': keys[row['programIdIndex']], 'accounts': [keys[i] for i in row['accounts']], 'data': decode(row['data'])})
    require(len(ordered) <= 256, 'total-instruction-cap', 'unsupported')
    return ordered


def transfer(op):
    # Only the standard single-authority transfer layouts are understood here.
    data, accounts = op['data'], op['accounts']
    return op['program'] == TOKEN and bool(data) and (
        (data[0] == 3 and len(data) == 9 and len(accounts) == 3) or
        (data[0] == 12 and len(data) == 10 and len(accounts) == 4))


def reconcile(bundle, *, wrapped_existing=False):
    result = {'format': 'intent-reconciliation-1', 'state': 'unknown', 'reason': None,
              'executionApproved': False, 'resubmitAllowed': False, 'ledgerUpdated': False, 'networkRequests': 0,
              'limitations': [
                  'Offline RPC evidence and caller-declared prior intent; neither signature nor registration time is cryptographically verified.',
                  'Canonical message binding is not a Solana wire-message signature check or independent validation of router instruction semantics.',
                  'Network is caller-labelled; no genesis identity is verified. Standard SPL token-to-token contracts only; wrapped SOL and Token-2022 are unsupported.',
                  'Balance consistency is not profitability, spendability or permission to trade. Mint/account extensions and off-transaction state are not checked.',
                  'Native balance reconciliation allows only transaction fees and explicitly proved account rent creation/refund. Unknown evidence never allows resubmission.',
                  'No execution or simulation ledger is updated. No signer, transaction builder or sender is included.']}
    if wrapped_existing:
        result['limitations'][2] = 'Network is caller-labelled; no genesis identity is verified. Standard SPL plus existing WSOL with consistent implied backing only; WSOL creation/closure and Token-2022 remain unsupported.'
    try:
        require(isinstance(bundle, dict) and set(bundle) == {'format', 'network', 'capturedAtMs', 'intent', 'rpcEvidence'} and bundle['format'] == 'intent-evidence-bundle-1', 'invalid-bundle-schema', 'invalid-input')
        intent, rpc = bundle['intent'], bundle['rpcEvidence']
        validate_intent(intent, wrapped_existing=wrapped_existing)
        result['intentSha256'] = digest(intent)
        require(bundle['network'] == intent['network'], 'network-label-mismatch')
        require(integer(bundle['capturedAtMs']) and bundle['capturedAtMs'] >= intent['preparedAtMs'], 'evidence-before-intent', 'invalid-input')
        result['evidenceSha256'] = digest(rpc)
        chain = chain_evidence(rpc, intent['signature'], intent['wallet'], intent['source']['mint'])
        result['chainState'] = chain['state']
        require(chain['state'] in ('finalized-success', 'finalized-failed'), 'chain-evidence-not-finalized-and-consistent', 'unknown')
        tx = rpc['transaction']['result']; meta = tx['meta']
        message_hash, keys, outer = binding(tx)
        require(message_hash == intent['messageSha256'], 'prepared-message-mismatch')
        require(keys[0] == intent['wallet'] and chain['nativeBalance']['walletIsFeePayer'], 'wallet-not-fee-payer', 'unsupported')
        native = chain['nativeBalance']
        fee = atomic(native['transactionFeeLamports'])
        require(fee <= atomic(intent['maximumFeeLamports']), 'fee-cap-exceeded')
        require(atomic(native['preLamports']) == atomic(intent['walletPreLamports']), 'wallet-prebalance-mismatch')
        pre, post = token_maps(meta, keys)
        required_accounts = {intent['source']['account'], intent['destination']['account']}
        for account in set(pre) | set(post):
            a, b = pre.get(account), post.get(account)
            if any(r and r['owner'] == intent['wallet'] for r in (a, b)) and account not in required_accounts:
                require(a == b, 'unexpected-wallet-token-change')
        failed = chain['state'] == 'finalized-failed'
        ops = instructions(meta, outer, keys) if not failed else []
        rent_spent = rent_refunded = 0
        observed = {}
        for side in ('source', 'destination'):
            contract = intent[side]; account = contract['account']
            require(account in keys, 'intent-account-not-in-transaction')
            index = keys.index(account)
            a, b = pre.get(account), post.get(account)
            identity = {k: contract[k] for k in ('mint', 'programId', 'decimals')}
            identity['owner'] = intent['wallet']
            for row in (a, b):
                if row is not None:
                    require(all(row[k] == v for k, v in identity.items()), 'token-account-identity-mismatch')
            lifecycle = contract['lifecycle']
            before_native, after_native = meta['preBalances'][index], meta['postBalances'][index]
            relevant = [o for o in ops if account in o['accounts'] and o['program'] in (TOKEN, SYSTEM)]
            if failed:
                require(a == b and before_native == after_native, 'failed-transaction-changed-account')
                require(a is not None or (lifecycle == 'create' and before_native == 0), 'failed-account-evidence-unavailable', 'unknown')
                before = after = a['amount'] if a else 0
            elif lifecycle == 'existing':
                require(a is not None and b is not None, 'existing-account-balance-missing', 'unknown')
                before, after = a['amount'], b['amount']
                if contract['mint'] == NATIVE:
                    reserve = before_native - before
                    require(reserve > 0 and after_native - after == reserve, 'wrapped-native-backing-mismatch')
                else:
                    require(before_native == after_native, 'unexpected-token-account-native-change')
                require(all(transfer(o) for o in relevant), 'unsupported-token-account-operation', 'unsupported')
            elif lifecycle == 'create':
                require(a is None and b is not None and before_native == 0 and after_native > 0, 'creation-evidence-incomplete', 'unknown')
                creates = [o for o in relevant if o['program'] == SYSTEM and len(o['data']) == 52 and o['data'][:4] == bytes(4) and o['accounts'] == [intent['wallet'], account]]
                initializes = [o for o in relevant if o['program'] == TOKEN and len(o['data']) == 33 and o['data'][0] == 18 and o['accounts'] == [account, contract['mint']]]
                require(len(creates) == len(initializes) == 1, 'creation-instructions-unproven', 'unknown')
                create, initialize = creates[0], initializes[0]
                require(relevant.index(create) < relevant.index(initialize), 'creation-order-mismatch')
                require(create['data'][20:] == decode(TOKEN) and int.from_bytes(create['data'][12:20], 'little') == 165 and initialize['data'][1:] == decode(intent['wallet']), 'creation-owner-or-space-mismatch')
                funded = int.from_bytes(create['data'][4:12], 'little')
                require(funded == after_native, 'creation-rent-mismatch')
                require(all(o in (create, initialize) or transfer(o) for o in relevant), 'unsupported-creation-operation', 'unsupported')
                rent_spent += funded; before, after = 0, b['amount']
            else:
                require(a is not None and b is None and before_native > 0 and after_native == 0, 'closure-evidence-incomplete', 'unknown')
                closes = [o for o in relevant if o['program'] == TOKEN and o['data'] == bytes([9]) and o['accounts'] == [account, intent['wallet'], intent['wallet']]]
                require(len(closes) == 1 and relevant[-1] == closes[0], 'closure-instruction-unproven', 'unknown')
                require(all(o == closes[0] or transfer(o) for o in relevant), 'unsupported-closure-operation', 'unsupported')
                rent_refunded += before_native; before, after = a['amount'], 0
            require(before == atomic(contract['preAmountAtomic']), 'token-prebalance-mismatch')
            observed[side] = {'preAtomic': str(before), 'postAtomic': str(after), 'deltaAtomic': str(after - before), 'lifecycle': lifecycle}
        require(rent_spent <= atomic(intent['maximumRentLamports']), 'rent-cap-exceeded')
        expected_delta = -fee - rent_spent + rent_refunded
        require(int(native['deltaLamports']) == expected_delta, 'unexplained-native-wallet-change')
        if failed:
            require(all(int(x['deltaAtomic']) == 0 for x in observed.values()), 'failed-token-balance-change')
        else:
            require(int(observed['source']['deltaAtomic']) == -atomic(intent['inputAtomic']), 'input-amount-mismatch')
            require(int(observed['destination']['deltaAtomic']) >= atomic(intent['minimumOutputAtomic']), 'minimum-output-not-met')
        result.update(state='finalized-failure-fee-only' if failed else 'balance-consistent-with-bound-message',
                      tokenAccounts=observed, native={'feeLamports': str(fee), 'rentSpentLamports': str(rent_spent),
                                                     'rentRefundedLamports': str(rent_refunded), 'walletDeltaLamports': str(expected_delta)})
    except EvidenceError as e:
        result.update(state=e.state, reason=e.reason)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError):
        result.update(state='invalid-input', reason='malformed-contract-or-evidence')
    return result
