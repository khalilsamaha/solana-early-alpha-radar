"""Synthetic unsigned messages only. Account keys are hashes, not funded accounts."""
import base64
import hashlib
import struct
from contract import PROGRAM, TOKEN, COMPUTE, ROLES, POLICY_ROLES, WRITABLE, b58, decode

NOW = 1800000000000  # Fixed synthetic clock, never evidence of current chain state.


def fake_key(label):
    return b58(hashlib.sha256(('radar-synthetic-cpmm-' + label).encode()).digest())


def short(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result + bytes([value]))


def encode(message, version='legacy', signatures=None):
    """Test serializer, intentionally separate from the production parser."""
    h = message['header']
    body = bytearray(b'\x80' if version == 0 else b'')
    body += bytes(h[k] for k in ('numRequiredSignatures', 'numReadonlySignedAccounts', 'numReadonlyUnsignedAccounts'))
    body += short(len(message['accountKeys']))
    body += b''.join(decode(k) for k in message['accountKeys'])
    body += decode(message['recentBlockhash'])
    body += short(len(message['instructions']))
    for ix in message['instructions']:
        data = decode(ix['data'])
        body += bytes([ix['programIdIndex']]) + short(len(ix['accounts'])) + bytes(ix['accounts'])
        body += short(len(data)) + data
    if version == 0:
        lookups = message.get('addressTableLookups', [])
        body += short(len(lookups))
        for row in lookups:
            body += decode(row['accountKey'])
            for field in ('writableIndexes', 'readonlyIndexes'):
                body += short(len(row[field])) + bytes(row[field])
    signatures = [bytes(64)] if signatures is None else signatures
    raw = short(len(signatures)) + b''.join(signatures) + body
    return base64.b64encode(raw).decode(), hashlib.sha256(body).hexdigest()


def fixture(version='legacy'):
    roles = {r: fake_key(r) for r in POLICY_ROLES}
    writable = [roles[r] for r in POLICY_ROLES if r in WRITABLE]
    readonly = [roles[r] for r in POLICY_ROLES if r not in WRITABLE] + [TOKEN, PROGRAM, COMPUTE]
    keys = writable + readonly
    all_roles = dict(roles, inputTokenProgram=TOKEN, outputTokenProgram=TOKEN)
    message = {'header': {'numRequiredSignatures': 1, 'numReadonlySignedAccounts': 0,
                         'numReadonlyUnsignedAccounts': len(readonly)},
               'accountKeys': keys, 'recentBlockhash': fake_key('blockhash'),
               'instructions': [
                   {'programIdIndex': keys.index(COMPUTE), 'accounts': [], 'data': b58(struct.pack('<BI', 2, 200000))},
                   {'programIdIndex': keys.index(COMPUTE), 'accounts': [], 'data': b58(struct.pack('<BQ', 3, 1))},
                   {'programIdIndex': keys.index(PROGRAM), 'accounts': [keys.index(all_roles[r]) for r in ROLES],
                    # Anchor discriminator independently frozen from its named global instruction.
                    'data': b58(bytes.fromhex('8fbe5adac41e33de') + struct.pack('<QQ', 100, 190))}]}
    encoded, message_hash = encode(message, version)
    return {'format': 'unsigned-cpmm-contract-1', 'unsignedTransactionBase64': encoded,
            'policy': {'format': 'cpmm-instruction-policy-1', 'network': 'devnet',
                       'issuedAtMs': NOW - 1000, 'expiresAtMs': NOW + 14000, 'accounts': roles,
                       'blockhash': message['recentBlockhash'], 'amountIn': '100', 'minimumAmountOut': '190',
                       'maxComputeUnits': 300000, 'maxMicroLamportsPerCU': '10',
                       'maxPriorityFeeLamports': '3', 'maxTotalFeeLamports': '6000'},
            'feeAssertion': {'format': 'message-fee-assertion-1', 'network': 'devnet',
                             'messageSha256': message_hash, 'observedAtMs': NOW - 500, 'lamports': '5001'}}


def edit_wire(packet, change, *, version=None, signatures=None, rebind_fee=True):
    from contract import decode_wire
    tx = decode_wire(packet['unsignedTransactionBase64'])[4]
    message = tx['transaction']['message']
    change(message)
    encoded, message_hash = encode(message, tx['version'] if version is None else version, signatures)
    packet['unsignedTransactionBase64'] = encoded
    if rebind_fee:
        packet['feeAssertion']['messageSha256'] = message_hash
    return packet


def instruction_data(packet, index, raw):
    return edit_wire(packet, lambda m: m['instructions'][index].update(data=b58(raw)))
