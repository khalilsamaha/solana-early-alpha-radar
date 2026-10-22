"""Fresh legacy CPMM packet from an independently supplied scope. No key access or send."""
import base64
import copy
import hashlib
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'swap-rehearsal'))
from swap_rehearsal import (SCOPE_FIELDS, policy_check, Session, CHILD, report, stop, prepare)
from contract import (POLICY_ROLES, WRITABLE, TOKEN, PROGRAM, COMPUTE, ROLES,
                      DISCRIMINATOR, key, decode, digest, fields, atomic, uint, U64)
from recorded_capture import Client, GENESIS
from core import check, context_value


class PacketRpc(Client):
    METHODS = ('getGenesisHash', 'getLatestBlockhash', 'getFeeForMessage')
    REQUEST_CAP = 4
    def __init__(self, opener=None):
        super().__init__('devnet', opener)


def scope_check(scope):
    fields(scope, SCOPE_FIELDS | {'format'}, 'scope-schema')
    check(scope['format'] == 'devnet-swap-scope-1' and scope['network'] == 'devnet', 'scope-network')
    fields(scope['accounts'], POLICY_ROLES, 'scope-accounts')
    for v in scope['accounts'].values(): key(v)
    check(len(set(scope['accounts'].values())) == len(POLICY_ROLES), 'scope-role-alias')
    uint(scope['maxComputeUnits'], 300000, 'scope-compute', minimum=1)
    for f in ('amountIn', 'minimumAmountOut', 'maxTotalFeeLamports'):
        atomic(scope[f], 'scope-amount', positive=True)
    for f in ('maxMicroLamportsPerCU', 'maxPriorityFeeLamports'): atomic(scope[f], 'scope-cap')
    check(int(scope['amountIn']) <= 1000 and int(scope['maxTotalFeeLamports']) <= 10000
          and int(scope['maxMicroLamportsPerCU']) <= 10000 and
          int(scope['maxPriorityFeeLamports']) <= min(3000, int(scope['maxTotalFeeLamports'])), 'scope-hard-cap')


def message(scope, blockhash):
    """Canonical fixed-width message; all vectors <128 so one-byte shortvec is exact."""
    scope_check(scope); key(blockhash)
    a = dict(scope['accounts'], inputTokenProgram=TOKEN, outputTokenProgram=TOKEN)
    keys = [a[r] for r in POLICY_ROLES if r in WRITABLE]
    keys += [a[r] for r in POLICY_ROLES if r not in WRITABLE] + [TOKEN, PROGRAM, COMPUTE]
    check(len(keys) == len(set(keys)) == 14, 'reserved-or-duplicate-key')
    def instruction(program, accounts, data):
        check(len(accounts) < 128 and len(data) < 128, 'fixed-message-vector')
        return bytes([keys.index(program), len(accounts), *[keys.index(k) for k in accounts], len(data)]) + data
    instructions = [
        instruction(COMPUTE, [], b'\x02' + scope['maxComputeUnits'].to_bytes(4, 'little')),
        instruction(COMPUTE, [], b'\x03' + bytes(8)),  # Deliberately zero priority price.
        instruction(PROGRAM, [a[r] for r in ROLES], DISCRIMINATOR +
                    int(scope['amountIn']).to_bytes(8, 'little') + int(scope['minimumAmountOut']).to_bytes(8, 'little'))]
    return bytes([1, 0, 7, len(keys)]) + b''.join(decode(k) for k in keys) + decode(blockhash) + bytes([3]) + b''.join(instructions)


def build(scope, *, opener=None, now=None):
    now = now or (lambda: time.time_ns() // 1000000)
    scope = copy.deepcopy(scope); scope_check(scope)
    # Validate before RPC, including reserved keys and hard caps. This fee is only a
    # local schema probe and is never returned or passed to the signer.
    start = now()
    def packet_for(blockhash, fee, at):
        p = {k: copy.deepcopy(scope[k]) for k in SCOPE_FIELDS}
        p.update(format='cpmm-instruction-policy-1', issuedAtMs=start, expiresAtMs=start + 15000, blockhash=blockhash)
        msg = message(scope, blockhash)
        return dict(format='unsigned-cpmm-contract-1', policy=p,
                    unsignedTransactionBase64=base64.b64encode(b'\x01' + bytes(64) + msg).decode(),
                    feeAssertion=dict(format='message-fee-assertion-1', network='devnet',
                                      messageSha256=hashlib.sha256(msg).hexdigest(), observedAtMs=at, lamports=str(fee)))
    probe = packet_for(scope['accounts']['wallet'], 1, start)
    policy_check(scope, probe, scope['accounts']['wallet'], start)
    rpc = PacketRpc(opener); ev = {}
    def fetch(name, method, params):
        check(start <= now() < start + 15000, 'packet-build-time-budget')
        item = rpc.request(method, params)
        check(item['state'] == 'received', 'packet-rpc-unavailable')
        ev[name] = dict(item, receivedAtMs=now())
        return item
    check(fetch('genesisBefore', 'getGenesisHash', [])['result'] == GENESIS['devnet'], 'packet-cluster')
    slot, value = context_value(fetch('blockhash', 'getLatestBlockhash', [{'commitment': 'finalized'}]), 0)
    blockhash = key(value['blockhash']); uint(value['lastValidBlockHeight'], U64, 'block-height', minimum=1)
    msg = message(scope, blockhash)
    _, fee = context_value(fetch('fee', 'getFeeForMessage', [base64.b64encode(msg).decode(),
                              {'commitment': 'finalized', 'minContextSlot': slot}]), slot)
    uint(fee, 10000, 'fee-unavailable-or-over-cap', minimum=1)
    check(fetch('genesisAfter', 'getGenesisHash', [])['result'] == GENESIS['devnet'], 'packet-cluster')
    packet = packet_for(blockhash, fee, ev['fee']['receivedAtMs'])
    policy_check(scope, packet, scope['accounts']['wallet'], now())
    return dict(format='fresh-devnet-swap-packet-1', packet=packet, scopeSha256=digest(scope),
                evidence=ev, requests=rpc.calls, networkRequests=len(rpc.calls),
                signaturesCreated=0, transactionsSent=0, signingApproved=False,
                lastValidBlockHeight=value['lastValidBlockHeight'],
                note='Scope and minimum output preserved. Zero priority price. Fresh account/program preflight is still required.')


def prepare_fresh(home, wallet, scope, *, opener=None):
    """One process avoids manual packet expiry; existing one-shot directory is never reset."""
    scope_check(scope); check(scope['accounts']['wallet'] == wallet, 'explicit-wallet-mismatch')
    with Session(home) as s:
        check(s.wallet == wallet, 'explicit-wallet-mismatch')
        if os.path.lexists(s.home / CHILD): return report(s.home)
        check(not stop(s.home), 'stop-marker')
    built = build(scope, opener=opener)
    # prepare reacquires the durable session lock, checks STOP and existing state, and
    # independently repeats the current pool/program/account/fee checks before signing.
    result = prepare(home, wallet, scope, built['packet'], opener=opener)
    result['packetBuild'] = {k: v for k, v in built.items() if k != 'packet'}
    return result
