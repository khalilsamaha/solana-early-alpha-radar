"""Offline ordered entry/exit message contract; no RPC, signer or execution path.

This is a separate ATOMIC transaction, not two delayed transactions. Its fee is
unknown until that exact combined message is priced. A trace alone is not a
simulation pass: final account effects, fee and collection still need review.
"""
import base64
from copy import deepcopy
import hashlib

import projected_exit
from contract import (COMPUTE, DISCRIMINATOR, PROGRAM, TOKEN, ROLES, WRITABLE, EvidenceError,
                      U64, atomic, decode, decode_wire, digest, fields)
from core import check
from fresh_packet import scope_check
from swap_rehearsal import scope_for

VERSION = 'atomic-roundtrip-rehearsal-1'
DRAFT_FIELDS = {'format', 'network', 'entryScope', 'exitScope', 'referenceBlockhash',
                'parentSimulationSha256', 'parentProjectionSha256',
                'unsignedTransactionBase64'}


def _instruction(keys, program, accounts, data):
    check(len(accounts) < 128 and len(data) < 128, 'atomic-vector')
    return bytes([keys.index(program), len(accounts),
                  *[keys.index(k) for k in accounts], len(data)]) + data


def _swap(keys, scope):
    a = dict(scope['accounts'], inputTokenProgram=TOKEN, outputTokenProgram=TOKEN)
    data = (DISCRIMINATOR + int(scope['amountIn']).to_bytes(8, 'little') +
            int(scope['minimumAmountOut']).to_bytes(8, 'little'))
    return _instruction(keys, PROGRAM, [a[k] for k in ROLES], data)


class _Review:
    """Private snapshot; never built from a public success summary."""
    def __init__(self, inputs, request):
        self.__inputs = deepcopy(inputs)
        parent = projected_exit._Review(self.__inputs, request)
        self.__post = parent.post()
        reverse = parent.build()
        check(parent.assess(reverse)['state'] == 'projected-reverse-message-consistent',
              'atomic-parent-reverse')
        self.__entry = scope_for(self.__inputs['packet']['policy'])
        self.__exit = reverse['scope']
        scope_check(self.__entry); scope_check(self.__exit)
        check(self.__entry['maxComputeUnits'] == self.__exit['maxComputeUnits'], 'atomic-compute-scope')
        _, _, _, _, tx = decode_wire(self.__inputs['packet']['unsignedTransactionBase64'])
        self.__keys = tx['transaction']['message']['accountKeys']
        self.__blockhash = self.__inputs['packet']['policy']['blockhash']

    def build(self):
        keys = self.__keys
        # Use the entry account order. Reverse roles must be re-indexed against
        # these keys; concatenating independently compiled instructions is wrong.
        h = bytes([1, 0, 7, len(keys)])
        ix = [
            _instruction(keys, COMPUTE, [], b'\x02' + self.__entry['maxComputeUnits'].to_bytes(4, 'little')),
            _instruction(keys, COMPUTE, [], b'\x03' + bytes(8)),
            _swap(keys, self.__entry), _swap(keys, self.__exit)]
        msg = h + b''.join(decode(k) for k in keys) + decode(self.__blockhash) + bytes([4]) + b''.join(ix)
        wire = b'\x01' + bytes(64) + msg
        check(len(wire) <= 1232, 'atomic-wire-size')
        return dict(format=VERSION+'-draft', network='devnet',
                    entryScope=deepcopy(self.__entry), exitScope=deepcopy(self.__exit),
                    referenceBlockhash=self.__blockhash,
                    parentSimulationSha256=self.__post['evidence']['fullSimulationSha256'],
                    parentProjectionSha256=self.__post['evidence']['projectionSha256'],
                    unsignedTransactionBase64=base64.b64encode(wire).decode())

    def parent(self):
        return deepcopy(self.__post)

    def binding(self, draft):
        fields(draft, DRAFT_FIELDS, 'atomic-draft-fields')
        check(draft['format'] == VERSION+'-draft' and draft['network'] == 'devnet', 'atomic-network')
        check(digest(draft['entryScope']) == digest(self.__entry) and
              digest(draft['exitScope']) == digest(self.__exit), 'atomic-scope')
        e = self.__post['evidence']
        check(draft['parentSimulationSha256'] == e['fullSimulationSha256'] and
              draft['parentProjectionSha256'] == e['projectionSha256'], 'atomic-parent-binding')
        check(draft['referenceBlockhash'] == self.__blockhash, 'atomic-blockhash')
        check(type(draft['unsignedTransactionBase64']) is str and
              len(draft['unsignedTransactionBase64']) <= 1644, 'atomic-encoded-size')
        raw, msg, signers, signatures, tx = decode_wire(draft['unsignedTransactionBase64'])
        check(len(raw) <= 1232 and tx['version'] == 'legacy' and
              len(signers) == 1 and signatures == [bytes(64)], 'atomic-unsigned-legacy')
        m = tx['transaction']['message']; keys = m['accountKeys']; h = m['header']
        a = self.__entry['accounts']
        check(keys == self.__keys and keys[0] == a['wallet'] and
              m['recentBlockhash'] == self.__blockhash, 'atomic-keys-blockhash')
        writable = set(keys[:h['numRequiredSignatures']-h['numReadonlySignedAccounts']])
        writable.update(keys[h['numRequiredSignatures']:len(keys)-h['numReadonlyUnsignedAccounts']])
        check(writable == {a[k] for k in WRITABLE}, 'atomic-privileges')
        instructions = m['instructions']; check(len(instructions) == 4, 'atomic-instruction-count')
        limit, price = instructions[:2]
        for ix in (limit, price):
            check(keys[ix['programIdIndex']] == COMPUTE and ix['accounts'] == [], 'atomic-compute')
        check(decode(limit['data']) == b'\x02'+self.__entry['maxComputeUnits'].to_bytes(4, 'little'),
              'atomic-compute-limit')
        check(decode(price['data']) == b'\x03'+bytes(8), 'atomic-priority')
        for ix, scope in zip(instructions[2:], (self.__entry, self.__exit)):
            roles = dict(scope['accounts'], inputTokenProgram=TOKEN, outputTokenProgram=TOKEN)
            check(keys[ix['programIdIndex']] == PROGRAM and
                  [keys[i] for i in ix['accounts']] == [roles[k] for k in ROLES], 'atomic-swap-roles')
            data = decode(ix['data'])
            check(len(data) == 24 and data[:8] == DISCRIMINATOR and
                  int.from_bytes(data[8:16], 'little') == int(scope['amountIn']) and
                  int.from_bytes(data[16:24], 'little') == int(scope['minimumAmountOut']), 'atomic-swap-amounts')
        return dict(parentSimulationSha256=e['fullSimulationSha256'],
            parentProjectionSha256=e['projectionSha256'], parentMessageSha256=e['messageSha256'],
            draftSha256=digest(draft), messageSha256=hashlib.sha256(msg).hexdigest(),
            unsignedWireSha256=hashlib.sha256(raw).hexdigest(), transactionBytes=len(raw),
            entryInputAtomic=self.__entry['amountIn'],
            entryMinimumOutputAtomic=self.__entry['minimumAmountOut'],
            acquiredAtomic=self.__exit['amountIn'],
            projectedFinalOutputAtomic=self.__post['projection']['projectedOutputAtomic'],
            exitMinimumOutputAtomic=self.__exit['minimumAmountOut'],
            computeUnitsShared=self.__entry['maxComputeUnits'], priorityPriceMicroLamports='0',
            instructionOrder=['compute-limit', 'zero-priority', 'entry-swap', 'exit-swap'],
            transactionCount=1, signatureCount=1, quantityBasis='exact-simulated-entry-acquisition',
            feeBasis='combined-message-not-yet-priced', blockhashBasis='entry-reference-only',
            evaluatedAtMs=e['evaluatedAtMs'])

    def trace(self, draft, groups):
        """Strict compiled TransferChecked traces; unknown CPI stays unavailable.

        Existing destination inventory can hide an entry shortfall in final net
        balances. Require the first leg's actual reported transfer to equal the
        entire second leg input, and record each intermediate balance separately.
        Caller-supplied traces are NOT live request/response evidence.
        """
        binding = self.binding(draft)
        check(type(groups) is list and len(groups) == 2, 'atomic-trace-groups')
        bykey = dict(zip(self.__inputs['capture']['accountKeys'],
                        self.__inputs['capture']['evidence']['accounts']['result']['value']))
        from state import account, u64
        a = self.__entry['accounts']; keys = self.__keys
        names = ('source', 'destination', 'inputVault', 'outputVault')
        amounts = {a[n]: u64(account(bykey[a[n]], TOKEN, 165), 64) for n in names}
        before = amounts.copy(); intermediate = None
        output = self.__post['projection']['projectedOutputAtomic']
        for index, group, scope, acquired in zip((2, 3), groups,
                (self.__entry, self.__exit), (self.__exit['amountIn'], output)):
            fields(group, {'index', 'instructions'}, 'atomic-trace-group')
            check(type(group['index']) is int and group['index'] == index, 'atomic-trace-order')
            ins = group['instructions']; check(type(ins) is list and len(ins) == 2, 'atomic-trace-count')
            s = scope['accounts']
            transfers = [(s['source'], s['inputMint'], s['inputVault'], s['wallet'], scope['amountIn']),
                         (s['outputVault'], s['outputMint'], s['destination'], s['authority'], acquired)]
            for ix, (src, mint, dst, authority, amount) in zip(ins, transfers):
                fields(ix, {'programIdIndex', 'accounts', 'data', 'stackHeight'}, 'atomic-trace-instruction')
                check(type(ix['programIdIndex']) is int and 0 <= ix['programIdIndex'] < len(keys) and
                      keys[ix['programIdIndex']] == TOKEN, 'atomic-trace-program')
                indices = ix['accounts']
                check(type(indices) is list and len(indices) == 4 and
                      all(type(i) is int and 0 <= i < len(keys) for i in indices), 'atomic-trace-indices')
                check([keys[i] for i in indices] == [src, mint, dst, authority], 'atomic-trace-roles')
                check(type(ix['stackHeight']) is int and ix['stackHeight'] == 2, 'atomic-trace-depth')
                check(type(ix['data']) is str and 1 <= len(ix['data']) <= 16, 'atomic-trace-data-size')
                data = decode(ix['data'])
                decimals = account(bykey[mint], TOKEN, 82)[44]
                check(len(data) == 10 and data[0] == 12 and data[9] == decimals and
                      int.from_bytes(data[1:9], 'little') == int(amount), 'atomic-trace-amount')
                qty = atomic(amount, 'atomic-transfer-quantity', positive=True)
                check(amounts[src] >= qty and amounts[dst]+qty <= U64, 'atomic-trace-balance')
                amounts[src] -= qty; amounts[dst] += qty
            if index == 2: intermediate = amounts.copy()
        check(amounts[a['destination']] == before[a['destination']], 'atomic-acquired-residual')
        return dict(binding=binding, traceSha256=digest(groups),
            balances={n:dict(beforeAtomic=str(before[a[n]]), afterEntryAtomic=str(intermediate[a[n]]),
                            afterExitAtomic=str(amounts[a[n]])) for n in names},
            originalTokenChangeAtomic=str(amounts[a['source']]-before[a['source']]),
            residualAcquiredAtomic='0', orderedTransfers=4)


def _empty():
    return dict(format=VERSION, state='unavailable', reasons=[], binding=None,
        atomicRehearsalOnly=True, twoTransactionExecutionVerified=False,
        liveCollectorVerified=False, simulationVerified=False, exitSimulationVerified=False,
        feeVerified=False, combinedFeeLamports=None, oracleEffectsReviewed=False,
        validForSubmission=False, signingApproved=False, executionApproved=False,
        actualEntryExecuted=False, roundTripFundingEstablished=False, mainnetSupported=False,
        netProfit=None, networkRequests=0, signaturesCreated=0, transactionsSent=0,
        limitations=[
            'One combined atomic draft; not two delayed transactions or their fee/failure model.',
            'Entry and reverse quantities derive from raw prior unsigned entry evidence.',
            'Combined fee is unknown; entry or separate-exit fees cannot be copied onto this message.',
            'No fresh blockhash, simulation transport, final-state review, signer or sender.',
            'Trace checks alone do not authenticate RPC evidence or validate oracle/final account effects.'])


def build(inputs, request):
    return _Review(inputs, request).build()


def assess(inputs, request, draft):
    result = _empty()
    try:
        result['binding'] = _Review(inputs, request).binding(draft)
        result['state'] = 'atomic-draft-consistent'
    except (ValueError, KeyError, TypeError, IndexError, OverflowError, EvidenceError):
        result['reasons'] = ['atomic-draft-rejected']
    return result


def assess_trace(inputs, request, draft, groups):
    result = _empty(); result.update(trace=None, orderedTokenFlowsMatched=False)
    try:
        result['trace'] = _Review(inputs, request).trace(draft, groups)
        result['binding'] = result['trace'].pop('binding')
        result.update(state='atomic-transfer-trace-consistent', orderedTokenFlowsMatched=True)
    except (ValueError, KeyError, TypeError, IndexError, OverflowError, EvidenceError):
        result['reasons'] = ['atomic-transfer-trace-rejected']
    return result
