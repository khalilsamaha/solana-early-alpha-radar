"""Bounded verification of external native credits; no signing, sending or budget reset.

Only direct, signed System transfers to the wallet are supported. Discovery must
reach the previous exit signature and remain stable across a fresh balance read.
"""
from core import check, verify_wire, decode_wire
from recorded_capture import Client, GENESIS, SYSTEM
from reader import base58, integer as valid_integer, ALPHABET

VERSION = 'external-devnet-funding-1'
MAX_CREDITS = 16
COMPUTE = 'ComputeBudget111111111111111111111111111111'
SAFE_ERRORS = {
    'funding-history-incomplete', 'funding-history-order', 'funding-history-not-finalized',
    'funding-history-changed', 'funding-unsupported-transaction', 'funding-receipt-mismatch',
    'funding-balance-chain-mismatch', 'funding-snapshot-mismatch', 'funding-proof-shape',
    'funding-positive-credit-required', 'funding-transaction-unavailable',
}


class FundingRpc(Client):
    METHODS = ('getGenesisHash', 'getSignatureStatuses', 'getTransaction',
               'getMultipleAccounts', 'getSignaturesForAddress')
    REQUEST_CAP = 11 + MAX_CREDITS
    SIGNATURE_LIST_CAP = MAX_CREDITS + 1


def integer(value):
    check(valid_integer(value), 'funding-receipt-mismatch')
    return value


def window(rows, last):
    check(type(rows) is list and 1 <= len(rows) <= MAX_CREDITS + 1, 'funding-history-incomplete')
    result = []; signatures = set(); previous = None
    for row in rows:
        check(type(row) is dict, 'funding-proof-shape')
        base58(row.get('signature'), 64); slot = integer(row.get('slot'))
        check(row.get('confirmationStatus') == 'finalized' and 'err' in row and row['err'] is None,
              'funding-history-not-finalized')
        check(row['signature'] not in signatures and (previous is None or slot < previous), 'funding-history-order')
        signatures.add(row['signature']); previous = slot
        result.append({k: row[k] for k in ('signature', 'slot', 'err', 'confirmationStatus')})
        if row['signature'] == last['signature']:
            check(slot == last['slot'], 'funding-receipt-mismatch')
            return result
        check(slot > last['slot'], 'funding-history-incomplete')
    raise ValueError('funding-history-incomplete')


def instruction_bytes(value):
    check(type(value) is str and 1 <= len(value) <= 20 and all(c in ALPHABET for c in value),
          'funding-unsupported-transaction')
    number = 0
    for c in value: number = number * 58 + ALPHABET.index(c)
    return bytes(len(value)-len(value.lstrip('1'))) + number.to_bytes((number.bit_length()+7)//8, 'big')


def credit(tx, discovery, wallet):
    check(type(tx) is dict and tx.get('slot') == discovery['slot'] and (tx.get('version') == 'legacy' or type(tx.get('version')) is int and tx['version'] == 0),
          'funding-receipt-mismatch')
    encoded = tx.get('transaction')
    check(type(encoded) is list and len(encoded) == 2 and encoded[1] == 'base64', 'funding-unsupported-transaction')
    verified = verify_wire(encoded[0])
    message = decode_wire(encoded[0])[4]['transaction']['message']
    keys = message['accountKeys']; header = message['header']
    check(verified['version'] == tx['version'] and verified['signatures'] == [discovery['signature']],
          'funding-receipt-mismatch')
    check(len(keys) in (3, 4) and keys[1] == wallet and keys[0] != wallet
          and set(keys[2:]) == ({SYSTEM} if len(keys) == 3 else {SYSTEM, COMPUTE})
          and header == dict(numRequiredSignatures=1, numReadonlySignedAccounts=0,
                             numReadonlyUnsignedAccounts=len(keys)-2), 'funding-unsupported-transaction')
    amount = None; compute_seen = set()
    for ix in message['instructions']:
        program = keys[ix['programIdIndex']]; data = instruction_bytes(ix['data'])
        if program == SYSTEM:
            check(amount is None and ix['accounts'] == [0, 1] and len(data) == 12
                  and data[:4] == bytes([2, 0, 0, 0]), 'funding-unsupported-transaction')
            amount = int.from_bytes(data[4:], 'little')
            check(amount > 0, 'funding-positive-credit-required')
        else:
            check(program == COMPUTE and ix['accounts'] == [] and data[0] not in compute_seen
                  and ((data[0] == 2 and len(data) == 5 and 0 < int.from_bytes(data[1:], 'little') <= 1400000)
                       or (data[0] == 3 and len(data) == 9)), 'funding-unsupported-transaction')
            compute_seen.add(data[0])
    check(amount is not None, 'funding-positive-credit-required')
    meta = tx.get('meta')
    check(type(meta) is dict and 'err' in meta and meta['err'] is None
          and meta.get('innerInstructions') in (None, [])
          and meta.get('preTokenBalances') == [] and meta.get('postTokenBalances') == []
          and meta.get('loadedAddresses', dict(writable=[], readonly=[])) == dict(writable=[], readonly=[]),
          'funding-unsupported-transaction')
    before, after = meta.get('preBalances'), meta.get('postBalances')
    check(type(before) is list and type(after) is list and len(before) == len(after) == len(keys),
          'funding-receipt-mismatch')
    before = [integer(x) for x in before]; after = [integer(x) for x in after]; fee = integer(meta.get('fee'))
    expected = before.copy(); expected[0] -= amount + fee; expected[1] += amount
    check(after == expected, 'funding-receipt-mismatch')
    return dict(signature=discovery['signature'], slot=discovery['slot'], source=keys[0],
                creditLamports=str(amount), walletBeforeLamports=str(before[1]), walletAfterLamports=str(after[1]),
                walletFeeLamports='0', wireSha256=verified['wireSha256'])


def verify(proof, last, wallet, balances):
    check(type(proof) is dict and proof.get('format') == VERSION, 'funding-proof-shape')
    rows = window(proof['historyBefore'], last)
    check(rows == window(proof['historyAfter'], last), 'funding-history-changed')
    txs = proof['transactions']
    check(type(txs) is list and 1 <= len(txs) == len(rows)-1 <= MAX_CREDITS, 'funding-proof-shape')
    receipts = [credit(tx, row, wallet) for tx, row in zip(txs, rows[:-1])]
    native = integer(int(last['walletAfterLamports'])); total = 0
    for receipt in reversed(receipts):
        check(receipt['walletBeforeLamports'] == str(native), 'funding-balance-chain-mismatch')
        native += int(receipt['creditLamports']); total += int(receipt['creditLamports'])
        check(receipt['walletAfterLamports'] == str(native), 'funding-balance-chain-mismatch')
    check(integer(balances['slot']) >= rows[0]['slot'] and balances['walletLamports'] == str(native),
          'funding-snapshot-mismatch')
    return dict(format=VERSION, state='verified-external-native-credits', credits=len(receipts),
                externalCreditLamports=str(total), historicalClosingLamports=last['walletAfterLamports'],
                reconciledStartingLamports=str(native), walletFeeLamports='0',
                receipts=list(reversed(receipts)), spendingAllowanceIncreased=False,
                evidenceScope='Finalized direct native transfers from one RPC; not proof of faucet identity or current balance')


def collect(source, capture, rpc, now, received):
    last = source['exitReceipt']; wallet = source['scope']['accounts']['wallet']
    params = [wallet, dict(limit=MAX_CREDITS+1, commitment='finalized', minContextSlot=last['slot'])]
    first = window(received(rpc.request('getSignaturesForAddress', params)), last)
    check(len(first) > 1, 'funding-positive-credit-required')
    transactions = []
    for row in first[:-1]:
        tx = received(rpc.request('getTransaction', [row['signature'],
            dict(encoding='base64', commitment='finalized', maxSupportedTransactionVersion=0)]))
        check(tx is not None, 'funding-transaction-unavailable')
        credit(tx, row, wallet)  # Refuse unsupported activity before collecting more.
        transactions.append(tx)
    # Re-read balances after receipts; no use of an old balance to seal a new proof.
    old_slot = received(capture['accounts'])['context']['slot']
    capture['accounts'] = rpc.request('getMultipleAccounts', [capture['accountKeys'],
        dict(encoding='base64', commitment='finalized', minContextSlot=max(old_slot, first[0]['slot']))])
    capture['accountsReceivedAtMs'] = now()
    snapshot_slot = received(capture['accounts'])['context']['slot']
    check(integer(snapshot_slot) >= max(old_slot, first[0]['slot']), 'funding-snapshot-mismatch')
    params[1]['minContextSlot'] = snapshot_slot
    second = window(received(rpc.request('getSignaturesForAddress', params)), last)
    check(first == second, 'funding-history-changed')
    capture['genesisAfter'] = received(rpc.request('getGenesisHash', []))
    check(capture['genesisAfter'] == GENESIS['devnet'], 'wrong-cluster')
    capture['finishedAtMs'] = now()
    return dict(format=VERSION, historyBefore=first, historyAfter=second, transactions=transactions)
