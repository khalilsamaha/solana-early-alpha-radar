"""Offline unsigned instruction-policy validation. No signer, RPC, or execution approval."""
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'intent-journal'))
from wire import b58, decode_wire
from reconcile import decode, EvidenceError

VERSION = 'cpmm-instruction-policy-1'
PROGRAM = 'DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb'
TOKEN = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
COMPUTE = 'ComputeBudget111111111111111111111111111111'
NATIVE = 'So11111111111111111111111111111111111111112'
SYSTEM = '11111111111111111111111111111111'
DISCRIMINATOR = hashlib.sha256(b'global:swap_base_input').digest()[:8]
ROLES = ('wallet', 'authority', 'config', 'pool', 'source', 'destination',
         'inputVault', 'outputVault', 'inputTokenProgram', 'outputTokenProgram',
         'inputMint', 'outputMint', 'observation')
POLICY_ROLES = tuple(r for r in ROLES if not r.endswith('TokenProgram'))
WRITABLE = {'wallet', 'pool', 'source', 'destination', 'inputVault', 'outputVault', 'observation'}
U64 = 2**64 - 1
POLICY_FIELDS = {'format', 'network', 'issuedAtMs', 'expiresAtMs', 'accounts', 'blockhash',
                 'amountIn', 'minimumAmountOut', 'maxComputeUnits', 'maxMicroLamportsPerCU',
                 'maxPriorityFeeLamports', 'maxTotalFeeLamports'}


class Rejected(ValueError):
    """Only fixed diagnostic codes, never provider/user text."""


def require(ok, code):
    if not ok:
        raise Rejected(code)


def fields(value, expected, code):
    require(type(value) is dict and set(value) == set(expected), code)


def uint(value, maximum, code, minimum=0):
    require(type(value) is int and minimum <= value <= maximum, code)
    return value


def atomic(value, code, positive=False):
    require(type(value) is str and len(value) <= 20 and re.fullmatch(r'0|[1-9][0-9]*', value), code)
    number = int(value)
    require(int(positive) <= number <= U64, code)
    return number


def key(value):
    require(type(value) is str and 32 <= len(value) <= 44, 'invalid-public-key')
    try:
        raw = decode(value)
    except (ValueError, TypeError, KeyError, EvidenceError):
        raise Rejected('invalid-public-key') from None
    require(len(raw) == 32 and b58(raw) == value, 'invalid-public-key')
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def _validate(packet, now_ms):
    fields(packet, {'format', 'policy', 'unsignedTransactionBase64', 'feeAssertion'}, 'packet-schema')
    require(packet['format'] == 'unsigned-cpmm-contract-1', 'packet-format')
    p = packet['policy']
    fields(p, POLICY_FIELDS, 'policy-schema')
    require(p['format'] == VERSION and p['network'] == 'devnet', 'unsupported-policy-or-network')
    now = uint(now_ms, 2**53 - 1, 'invalid-clock')
    start = uint(p['issuedAtMs'], 2**53 - 1, 'invalid-policy-time')
    end = uint(p['expiresAtMs'], 2**53 - 1, 'invalid-policy-time')
    require(start <= now < end and 0 < end - start <= 15000, 'policy-expired-or-future')
    fields(p['accounts'], POLICY_ROLES, 'account-policy-schema')
    accounts = {r: key(p['accounts'][r]) for r in POLICY_ROLES}
    require(len(set(accounts.values())) == len(accounts), 'role-alias')
    require(not set(accounts.values()) & {PROGRAM, TOKEN, COMPUTE, NATIVE, SYSTEM}, 'reserved-role-key')
    accounts.update(inputTokenProgram=TOKEN, outputTokenProgram=TOKEN)
    key(p['blockhash'])
    amount = atomic(p['amountIn'], 'invalid-input-amount', positive=True)
    minimum = atomic(p['minimumAmountOut'], 'invalid-minimum-output', positive=True)
    max_cu = uint(p['maxComputeUnits'], 1400000, 'invalid-compute-cap', minimum=1)
    max_price = atomic(p['maxMicroLamportsPerCU'], 'invalid-price-cap')
    max_priority = atomic(p['maxPriorityFeeLamports'], 'invalid-priority-cap')
    max_fee = atomic(p['maxTotalFeeLamports'], 'invalid-fee-cap', positive=True)
    require(max_priority <= max_fee, 'inconsistent-fee-caps')

    try:
        raw, message_bytes, signers, signatures, tx = decode_wire(packet['unsignedTransactionBase64'])
    except (ValueError, TypeError, IndexError, KeyError):
        raise Rejected('malformed-or-unsupported-wire') from None
    require(len(signers) == 1 and signatures == [bytes(64)], 'requires-one-unsigned-signature')
    m = tx['transaction']['message']
    require(not m.get('addressTableLookups'), 'lookup-tables-unsupported')
    keys = m['accountKeys']
    require(keys[0] == accounts['wallet'], 'fee-payer-mismatch')
    require(m['recentBlockhash'] == p['blockhash'], 'blockhash-mismatch')
    expected_writable = {accounts[r] for r in WRITABLE}
    h = m['header']
    actual_writable = set(keys[:h['numRequiredSignatures'] - h['numReadonlySignedAccounts']])
    actual_writable.update(keys[h['numRequiredSignatures']:len(keys) - h['numReadonlyUnsignedAccounts']])
    require(actual_writable == expected_writable, 'writable-privilege-mismatch')
    require(set(keys) == set(accounts.values()) | {PROGRAM, COMPUTE}, 'unexpected-or-missing-account')
    instructions = m['instructions']
    require(len(instructions) == 3, 'instruction-count')
    limit_ix, price_ix, swap_ix = instructions
    for ix in (limit_ix, price_ix):
        require(keys[ix['programIdIndex']] == COMPUTE and not ix['accounts'], 'compute-instruction-contract')
    limit_data, price_data = decode(limit_ix['data']), decode(price_ix['data'])
    require(len(limit_data) == 5 and limit_data[0] == 2, 'compute-limit-instruction')
    require(len(price_data) == 9 and price_data[0] == 3, 'compute-price-instruction')
    units, price = int.from_bytes(limit_data[1:], 'little'), int.from_bytes(price_data[1:], 'little')
    require(1 <= units <= max_cu and price <= max_price, 'compute-budget-exceeded')
    priority = (units * price + 999999) // 1000000
    require(priority <= max_priority, 'priority-fee-exceeded')
    require(keys[swap_ix['programIdIndex']] == PROGRAM, 'swap-program-mismatch')
    require([keys[i] for i in swap_ix['accounts']] == [accounts[r] for r in ROLES], 'swap-account-role-mismatch')
    swap_data = decode(swap_ix['data'])
    require(len(swap_data) == 24 and swap_data[:8] == DISCRIMINATOR, 'unsupported-swap-instruction')
    require(int.from_bytes(swap_data[8:16], 'little') == amount, 'input-amount-mismatch')
    require(int.from_bytes(swap_data[16:24], 'little') == minimum, 'minimum-output-mismatch')

    message_hash = hashlib.sha256(message_bytes).hexdigest()
    fee = packet['feeAssertion']
    fields(fee, {'format', 'network', 'messageSha256', 'observedAtMs', 'lamports'}, 'fee-assertion-schema')
    require(fee['format'] == 'message-fee-assertion-1' and fee['network'] == 'devnet', 'fee-assertion-network')
    require(fee['messageSha256'] == message_hash, 'fee-message-mismatch')
    fee_at = uint(fee['observedAtMs'], 2**53 - 1, 'invalid-fee-time')
    require(start <= fee_at <= now and now - fee_at <= 10000, 'fee-assertion-stale-or-future')
    total_fee = atomic(fee['lamports'], 'invalid-fee-assertion', positive=True)
    require(priority <= total_fee <= max_fee, 'total-fee-outside-bounds')
    return {'state': 'instruction-policy-match', 'policySha256': digest(p),
            'wireMessageSha256': message_hash, 'unsignedWireSha256': hashlib.sha256(raw).hexdigest(),
            'messageVersion': tx['version'], 'program': PROGRAM, 'instruction': 'swap_base_input',
            'accounts': accounts, 'amountIn': str(amount), 'minimumAmountOut': str(minimum),
            'computeUnits': units, 'microLamportsPerCU': str(price),
            'priorityFeeLamports': str(priority), 'assertedTotalFeeLamports': str(total_fee),
            'validUntilExclusiveMs': min(end, fee_at + 10001)}


def validate(packet, *, now_ms):
    """Compare public bytes with caller-supplied prior policy. Match is never signing permission."""
    result = {'format': VERSION, 'networkRequests': 0, 'transactionsSent': 0,
              'signaturesCreated': 0, 'ledgerUpdated': False, 'signingApproved': False,
              'executionApproved': False, 'accountStateVerified': False,
              'clusterVerified': False, 'blockhashValidityVerified': False,
              'deployedProgramVerified': False, 'feeAssertionVerified': False,
              'priorPolicyProven': False, 'simulationVerified': False}
    try:
        result.update(_validate(packet, now_ms))
    except Rejected as exc:
        result.update(state='rejected', reason=str(exc))
    return result
