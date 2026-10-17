"""Synthetic intent/RPC bundles. No real signatures, wallets or swap programs."""
import copy
from reconcile import TOKEN, SYSTEM, binding
from reader import ALPHABET


def encode(raw):
    n, out = int.from_bytes(raw, 'big'), ''
    while n:
        n, rest = divmod(n, 58); out = ALPHABET[rest] + out
    return '1' * (len(raw) - len(raw.lstrip(b'\0'))) + out


def pub(i): return encode(bytes([i]) * 32)


def fixture(lifecycle='existing', failed=False):
    wallet, source, destination, pool_in, pool_out, authority, input_mint, output_mint, router, extra = [pub(i) for i in range(2, 12)]
    keys = [wallet, source, destination, pool_in, pool_out, authority, input_mint, output_mint, TOKEN, SYSTEM, router, extra]
    signature = encode(bytes([1]) * 64)
    rent, fee = 2039280, 5000
    def ix(program, accounts, data):
        return {'programIdIndex': keys.index(program), 'accounts': [keys.index(a) for a in accounts], 'data': encode(data)}
    def token(account, mint, owner, amount):
        return {'accountIndex': keys.index(account), 'mint': mint, 'owner': owner, 'programId': TOKEN,
                'uiTokenAmount': {'amount': str(amount), 'decimals': 6}}
    pre = [token(source, input_mint, wallet, 1000), token(destination, output_mint, wallet, 0),
           token(pool_in, input_mint, authority, 10000), token(pool_out, output_mint, authority, 10000)]
    post = copy.deepcopy(pre)
    amount_in = 1000 if lifecycle == 'close' else 100
    for row, amount in zip(post, [1000 - amount_in, 200, 10000 + amount_in, 9800]):
        row['uiTokenAmount']['amount'] = str(amount)
    native_pre = [10000000, rent, rent, rent, rent] + [1] * 7
    native_post = native_pre.copy(); native_post[0] -= fee
    ops = [ix(TOKEN, [source, pool_in, wallet], bytes([3]) + amount_in.to_bytes(8, 'little')),
           ix(TOKEN, [pool_out, destination, authority], bytes([3]) + (200).to_bytes(8, 'little'))]
    if lifecycle == 'create':
        pre = [r for r in pre if r['accountIndex'] != 2]; native_pre[2] = 0; native_post[0] -= rent
        from reconcile import decode
        ops = [ix(SYSTEM, [wallet, destination], bytes(4) + rent.to_bytes(8, 'little') + (165).to_bytes(8, 'little') + decode(TOKEN)),
               ix(TOKEN, [destination, output_mint], bytes([18]) + decode(wallet))] + ops
    if lifecycle == 'close':
        post = [r for r in post if r['accountIndex'] != 1]; native_post[1] = 0; native_post[0] += rent
        ops.append(ix(TOKEN, [source, wallet, wallet], bytes([9])))
    error = {'InstructionError': [0, 'InvalidArgument']} if failed else None
    if failed:
        post = copy.deepcopy(pre); native_post = native_pre.copy(); native_post[0] -= fee
    tx = {'slot': 100, 'version': 'legacy', 'transaction': {'signatures': [signature], 'message': {
        'accountKeys': keys, 'recentBlockhash': pub(20),
        'header': {'numRequiredSignatures': 1, 'numReadonlySignedAccounts': 0, 'numReadonlyUnsignedAccounts': 7},
        'instructions': [ix(router, keys[:9], bytes([1]))]}},
        'meta': {'err': error, 'fee': fee, 'preBalances': native_pre, 'postBalances': native_post,
                 'preTokenBalances': pre, 'postTokenBalances': post,
                 'innerInstructions': [] if failed else [{'index': 0, 'instructions': ops}]}}
    intent = {'format': 'transaction-intent-1', 'network': 'devnet', 'signature': signature,
        'wallet': wallet, 'messageSha256': binding(tx)[0], 'preparedAtMs': 1800000000000,
        'walletPreLamports': '10000000',
        'source': {'account': source, 'mint': input_mint, 'programId': TOKEN, 'decimals': 6, 'preAmountAtomic': '1000', 'lifecycle': 'close' if lifecycle == 'close' else 'existing'},
        'destination': {'account': destination, 'mint': output_mint, 'programId': TOKEN, 'decimals': 6, 'preAmountAtomic': '0', 'lifecycle': 'create' if lifecycle == 'create' else 'existing'},
        'inputAtomic': str(amount_in), 'minimumOutputAtomic': '180', 'maximumFeeLamports': '10000', 'maximumRentLamports': str(rent)}
    return {'format': 'intent-evidence-bundle-1', 'network': 'devnet', 'capturedAtMs': 1800000005000,
        'intent': intent, 'rpcEvidence': {'signatureStatus': {'state': 'received', 'result': {
            'context': {'slot': 110}, 'value': [{'slot': 100, 'err': error, 'confirmationStatus': 'finalized'}]}},
            'transaction': {'state': 'received', 'result': tx}}}
