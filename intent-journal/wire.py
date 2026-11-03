"""Strict legacy/v0 wire decoding and Ed25519 verification using Node's crypto.

No private keys, message builder, sender, RPC or third-party packages.
"""
import base64
from contextlib import contextmanager
from contextvars import ContextVar
import time
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'intent-lab'))
from reconcile import ALPHABET, binding


# Opt-in only: the ordinary verifier and all senders keep their original behavior.
# This memo stores only successful authentication of exact canonical wire bytes;
# it never stores file state, parsed receipts, deadlines or authorization results.
_SIGNATURE_SCOPE = ContextVar('exact_signature_verification_scope', default=None)
MAX_SIGNATURE_MEMO = 64


@contextmanager
def signature_verification_scope(*, reuse_current=False):
    """Isolate by default; a trusted nested phase may explicitly join its owner.

    Shared-phase counters are deltas; memoEntries is the owner's current gauge.
    Only the owner clears the bounded set, including on exceptional exit.
    """
    check(type(reuse_current) is bool, 'signature-scope-mode')
    if reuse_current:
        scope = _SIGNATURE_SCOPE.get()
        check(scope is not None, 'signature-scope-owner-required')
        accepted, counts = scope
        before = dict(counts)
        def phase_snapshot():
            return dict(version=counts['version'], sharedWithParent=True,
                **{k: counts[k] - before[k] for k in counts if k != 'version'},
                memoEntries=len(accepted), maximumMemoEntries=MAX_SIGNATURE_MEMO)
        yield phase_snapshot
        return
    accepted = set()
    counts = dict(version='exact-signature-replay-1', verificationCalls=0,
                  verifierProcesses=0, memoHits=0, capacityBypasses=0,
                  verifierElapsedMs=0.0)
    token = _SIGNATURE_SCOPE.set((accepted, counts))
    def snapshot():
        return dict(counts, memoEntries=len(accepted), maximumMemoEntries=MAX_SIGNATURE_MEMO)
    try:
        yield snapshot
    finally:
        accepted.clear()
        _SIGNATURE_SCOPE.reset(token)


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


def decode_wire(encoded):
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
    total = len(keys) + sum(len(l['writableIndexes']) + len(l['readonlyIndexes']) for l in lookups)
    check(1 <= total <= 256 and len(set(keys)) == len(keys), 'duplicate-or-excessive-keys')
    check(0 <= header['numReadonlySignedAccounts'] < first and
          header['numReadonlyUnsignedAccounts'] <= len(keys) - first, 'invalid-header-counts')
    check(bool(instructions) and all(i['programIdIndex'] < total and all(a < total for a in i['accounts'])
                                    for i in instructions), 'instruction-index-or-count')
    tx = {'version': version, 'transaction': {'signatures': [b58(s) for s in signatures], 'message': message},
          'meta': {'loadedAddresses': {'writable': [], 'readonly': []}}}
    return raw, raw[start:], keys[:first], signatures, tx


def parse(encoded):
    parts = decode_wire(encoded)
    tx = parts[4]
    # Journal behavior stays strict; descriptor verification is not ALT resolution.
    check(not tx['transaction']['message'].get('addressTableLookups'), 'address-lookup-resolution-not-supported')
    canonical_hash = binding(tx)[0]  # header, key uniqueness and instruction bounds
    return (*parts, canonical_hash)


def verify_signed_message(encoded):
    """Authenticate wire bytes and lookup descriptors; does NOT resolve ALT addresses."""
    raw, message, keys, signatures, tx = decode_wire(encoded)
    scope = _SIGNATURE_SCOPE.get()
    accepted, counts = scope if scope is not None else (None, None)
    if counts is not None: counts['verificationCalls'] += 1
    if accepted is not None and raw in accepted:
        counts['memoHits'] += 1
    else:
        node = shutil.which('node')
        check(node is not None, 'node-runtime-unavailable')
        payload = {'message': base64.b64encode(message).decode(), 'signers': [
            {'key': base64.b64encode(k).decode(), 'signature': base64.b64encode(s).decode()}
            for k, s in zip(keys, signatures)]}
        # Strip NODE_OPTIONS and inherited preload hooks; never invoke a shell.
        started = time.perf_counter()
        if counts is not None: counts['verifierProcesses'] += 1
        try:
            p = subprocess.run([str(Path(node).resolve()), str(Path(__file__).with_name('verify-ed25519.mjs'))],
                input=json.dumps(payload), text=True, capture_output=True, timeout=5,
                env={'PATH': os.defpath})
        finally:
            if counts is not None:
                counts['verifierElapsedMs'] += (time.perf_counter() - started) * 1000
        check(p.returncode == 0 and p.stdout == '{"valid":true}', 'invalid-ed25519-signature')
        if accepted is not None:
            if len(accepted) < MAX_SIGNATURE_MEMO: accepted.add(raw)
            else: counts['capacityBypasses'] += 1
    return {'format': 'verified-wire-1', 'wireSha256': hashlib.sha256(raw).hexdigest(),
            'wireMessageSha256': hashlib.sha256(message).hexdigest(),
            'signatures': tx['transaction']['signatures'], 'wallet': tx['transaction']['message']['accountKeys'][0],
            'version': tx['version'], 'requiredSignatures': len(signatures), 'signatureVerified': True,
            'addressLookupCount': len(tx['transaction']['message'].get('addressTableLookups', []))}


def verify_wire(encoded):
    canonical_hash = parse(encoded)[5]
    verified = verify_signed_message(encoded)
    # Preserve the prior journal identity contract and idempotent registration hash.
    del verified['addressLookupCount']
    return {**verified, 'canonicalMessageSha256': canonical_hash}
