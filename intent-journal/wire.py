"""Strict legacy/v0 wire decoding and Ed25519 verification using Node's crypto.

No private keys, message builder, sender, RPC or third-party packages.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'intent-lab'))
from reconcile import ALPHABET, binding


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def b58(raw):
    number, text = int.from_bytes(raw, 'big'), ''
    while number:
        number, digit = divmod(number, 58)
        text = ALPHABET[digit] + text
    return '1' * (len(raw) - len(raw.lstrip(b'\0'))) + text


class Cursor:
    def __init__(self, raw):
        self.raw, self.at = raw, 0

    def take(self, size):
        check(0 <= size <= len(self.raw) - self.at, 'truncated-wire')
        result = self.raw[self.at:self.at + size]
        self.at += size
        return result

    def byte(self):
        return self.take(1)[0]

    def count(self, maximum):
        value = 0
        for i in range(3):
            byte = self.byte()
            check(i < 2 or byte <= 3, 'shortvec-overflow')
            value |= (byte & 127) << (7 * i)
            if not byte & 128:
                check(i == 0 or byte != 0, 'noncanonical-shortvec')
                check(value <= maximum, 'wire-count-cap')
                return value
        raise ValueError('shortvec-overflow')


def parse(encoded):
    check(isinstance(encoded, str) and len(encoded) <= 1644, 'wire-byte-cap')
    raw = base64.b64decode(encoded, validate=True)
    check(base64.b64encode(raw).decode() == encoded and 1 <= len(raw) <= 1232, 'invalid-wire-encoding')
    c = Cursor(raw)
    signatures = [c.take(64) for _ in range(c.count(18))]
    check(bool(signatures), 'missing-signatures')
    start = c.at
    first = c.byte()
    version = 'legacy'
    if first & 128:
        check(first == 128, 'unsupported-message-version')
        version, first = 0, c.byte()
    header = dict(zip(('numRequiredSignatures', 'numReadonlySignedAccounts', 'numReadonlyUnsignedAccounts'),
                      (first, c.byte(), c.byte())))
    keys = [c.take(32) for _ in range(c.count(256))]
    check(first == len(signatures) and first <= len(keys), 'signature-count-mismatch')
    blockhash = b58(c.take(32))
    instructions = []
    for _ in range(c.count(64)):
        instructions.append({'programIdIndex': c.byte(), 'accounts': list(c.take(c.count(256))),
                             'data': b58(c.take(c.count(1232)))})
    lookups = []
    if version == 0:
        for _ in range(c.count(256)):
            lookups.append({'accountKey': b58(c.take(32)), 'writableIndexes': list(c.take(c.count(256))),
                            'readonlyIndexes': list(c.take(c.count(256)))})
    check(c.at == len(raw), 'trailing-wire-bytes')
    message = {'header': header, 'accountKeys': [b58(k) for k in keys], 'recentBlockhash': blockhash,
               'instructions': instructions}
    if version == 0:
        message['addressTableLookups'] = lookups
    # Resolve no lookup table from caller-supplied metadata. This journal deliberately
    # refuses ALT-bearing messages until an independently checked resolver exists.
    check(not lookups, 'address-lookup-resolution-not-supported')
    tx = {'version': version, 'transaction': {'signatures': [b58(s) for s in signatures], 'message': message},
          'meta': {'loadedAddresses': {'writable': [], 'readonly': []}}}
    canonical_hash = binding(tx)[0]  # header, key uniqueness and instruction bounds
    return raw, raw[start:], keys[:first], signatures, tx, canonical_hash


def verify_wire(encoded):
    raw, message, keys, signatures, tx, canonical_hash = parse(encoded)
    node = shutil.which('node')
    check(node is not None, 'node-runtime-unavailable')
    payload = {'message': base64.b64encode(message).decode(), 'signers': [
        {'key': base64.b64encode(k).decode(), 'signature': base64.b64encode(s).decode()}
        for k, s in zip(keys, signatures)]}
    # Strip NODE_OPTIONS and inherited preload hooks; never invoke a shell.
    p = subprocess.run([str(Path(node).resolve()), str(Path(__file__).with_name('verify-ed25519.mjs'))],
        input=json.dumps(payload), text=True, capture_output=True, timeout=5,
        env={'PATH': os.defpath})
    check(p.returncode == 0 and p.stdout == '{"valid":true}', 'invalid-ed25519-signature')
    return {'format': 'verified-wire-1', 'wireSha256': hashlib.sha256(raw).hexdigest(),
            'wireMessageSha256': hashlib.sha256(message).hexdigest(), 'canonicalMessageSha256': canonical_hash,
            'signatures': tx['transaction']['signatures'], 'wallet': tx['transaction']['message']['accountKeys'][0],
            'version': tx['version'], 'requiredSignatures': len(signatures), 'signatureVerified': True}
