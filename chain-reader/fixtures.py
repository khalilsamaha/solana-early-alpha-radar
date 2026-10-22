"""Synthetic public identifiers and RPC responses; not chain observations."""
from reader import ALPHABET


def encode(raw):
    n, out = int.from_bytes(raw, 'big'), ''
    while n:
        n, remainder = divmod(n, 58)
        out = ALPHABET[remainder] + out
    return '1' * (len(raw) - len(raw.lstrip(b'\0'))) + out


SIGNATURE = encode(bytes([1]) * 64)
WALLET, MINT, ACCOUNT = [encode(bytes([i]) * 32) for i in (2, 3, 4)]


def fixture():
    def balance(amount):
        return {'accountIndex': 1, 'mint': MINT, 'owner': WALLET,
                'uiTokenAmount': {'amount': str(amount), 'decimals': 6}}
    return {'signatureStatus': {'state': 'received', 'result': {'context': {'slot': 120}, 'value': [
        {'slot': 100, 'err': None, 'confirmationStatus': 'finalized'}]}},
        'transaction': {'state': 'received', 'result': {'slot': 100, 'version': 'legacy',
            'transaction': {'signatures': [SIGNATURE], 'message': {
                'accountKeys': [WALLET, ACCOUNT], 'header': {'numRequiredSignatures': 1}}},
            'meta': {'err': None, 'fee': 5000, 'preBalances': [10000000, 2000000],
                     'postBalances': [9995000, 2000000], 'preTokenBalances': [balance(0)],
                     'postTokenBalances': [balance(123456)]}}}}
