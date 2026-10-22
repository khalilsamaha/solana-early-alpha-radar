"""Offline signed-token receipt accounting. Never signs, submits or writes a ledger."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'intent-journal'))
from wire import verify_wire
from reconcile import (EvidenceError, require, binding, token_maps, instructions, transfer,
                       reconcile, TOKEN, SYSTEM, NATIVE, atomic, digest)

FLAGS = {'networkRequests': 0, 'transactionsSent': 0, 'executionApproved': False,
         'resubmitAllowed': False, 'productionLedgerUpdated': False}


def transfer_flows(intent, tx, observed):
    """Check decoded standard-token movements against wallet account balance changes.

    Inner instruction bytes and balances are RPC claims, not authenticated by signatures.
    Router semantics are deliberately not inferred from token movements.
    """
    _, keys, outer = binding(tx)
    meta = tx['meta']
    pre, post = token_maps(meta, keys)
    ops = instructions(meta, outer, keys)
    # Do not let offsetting native transfers or unrelated authority changes hide
    # behind a net wallet delta that happens to equal the fee.
    for op in ops:
        if intent['wallet'] not in op['accounts']:
            continue
        if op['program'] == SYSTEM:
            require(intent['destination']['lifecycle'] == 'create' and
                    op['accounts'] == [intent['wallet'], intent['destination']['account']] and
                    len(op['data']) == 52 and op['data'][:4] == bytes(4),
                    'unsupported-wallet-native-operation', 'unsupported')
        elif op['program'] == TOKEN:
            allowed_move = transfer(op) and (
                op['accounts'][0] == intent['source']['account'] or
                op['accounts'][2 if op['data'][0] == 12 else 1] == intent['destination']['account'])
            allowed_close = (intent['source']['lifecycle'] == 'close' and op['data'] == bytes([9]) and
                             op['accounts'] == [intent['source']['account'], intent['wallet'], intent['wallet']])
            require(allowed_move or allowed_close, 'unsupported-wallet-token-operation', 'unsupported')
    flows = {}
    for side in ('source', 'destination'):
        contract = intent[side]; account = contract['account']
        relevant = [o for o in ops if account in o['accounts'] and o['program'] == TOKEN]
        moves = [o for o in relevant if transfer(o)]
        require(bool(moves), 'token-transfer-evidence-missing', 'unknown')
        if contract['lifecycle'] == 'create':
            starts = [i for i, o in enumerate(relevant) if o['data'][:1] == bytes([18])]
            require(len(starts) == 1 and all(relevant.index(o) > starts[0] for o in moves),
                    'transfer-before-initialization')
        total = 0
        for move in moves:
            data, accounts = move['data'], move['accounts']
            checked = data[0] == 12
            source, destination, authority = accounts[0], accounts[2 if checked else 1], accounts[-1]
            require(source != destination, 'self-transfer-not-supported', 'unsupported')
            if side == 'source':
                require(source == account and authority == intent['wallet'], 'unexpected-source-direction-or-authority')
                counterparty = destination
            else:
                require(destination == account, 'unexpected-destination-direction')
                counterparty = source
            if checked:
                require(accounts[1] == contract['mint'] and data[-1] == contract['decimals'],
                        'checked-transfer-mint-or-decimals-mismatch')
            identity = [m[counterparty] for m in (pre, post) if counterparty in m]
            require(bool(identity), 'counterparty-token-identity-unavailable', 'unknown')
            require(all(all(row[k] == contract[k] for k in ('mint', 'programId', 'decimals')) for row in identity),
                    'counterparty-token-identity-mismatch')
            require(all(row['owner'] == identity[0]['owner'] for row in identity), 'counterparty-owner-changed')
            if side == 'destination':
                # Delegated/multisig authorities require additional account-state evidence.
                require(authority == identity[0]['owner'], 'counterparty-authority-not-supported', 'unsupported')
            amount = int.from_bytes(data[1:9], 'little')
            require(amount > 0, 'zero-transfer-not-supported', 'unsupported')
            total += amount
        expected = abs(int(observed[side]['deltaAtomic']))
        require(total == expected, 'transfer-flow-balance-mismatch')
        flows[side] = {'transfers': len(moves), 'amountAtomic': str(total)}
    return flows


def audit(package):
    result = {'format': 'signed-token-reconciliation-1', 'state': 'unknown', 'reason': None,
              'signatureVerified': False, **FLAGS,
              'limitations': [
                  'Signatures authenticate message bytes, not RPC finality, token balances or inner instructions.',
                  'Prior intent timing and network are caller assertions; this offline tool does not establish durable pre-submission registration or genesis identity.',
                  'Balance and transfer consistency does not decode router semantics or prove spendability, profitability or trade eligibility.',
                  'WSOL supports existing accounts only. Positive unchanged lamports-minus-token-amount is an implied backing reserve, not verified account data or rent exemption.',
                  'ALT, Token-2022, WSOL wrap/unwrap, delegated/multisig transfers and unrecorded lifecycle operations remain unsupported.',
                  'This report is not an execution-ledger input. Scanner, quote observer, signing and submission policies are unchanged.']}
    try:
        require(isinstance(package, dict) and set(package) == {'format', 'signedTransactionBase64', 'bundle'}
                and package['format'] == 'signed-token-evidence-1', 'invalid-package-schema', 'invalid-input')
        bundle = package['bundle']; intent = bundle['intent']
        try:
            verified = verify_wire(package['signedTransactionBase64'])
        except ValueError:
            raise EvidenceError('unsupported-or-invalid-wire', 'signed-wire-verification-failed')
        result.update(signatureVerified=True, wireSha256=verified['wireSha256'],
                      wireMessageSha256=verified['wireMessageSha256'])
        require(verified['signatures'][0] == intent['signature'] and verified['wallet'] == intent['wallet']
                and verified['canonicalMessageSha256'] == intent['messageSha256'], 'signed-intent-identity-mismatch')
        comparison = reconcile(bundle, wrapped_existing=True)
        require(comparison['state'] in ('balance-consistent-with-bound-message', 'finalized-failure-fee-only'),
                comparison['reason'] or 'balance-evidence-incomplete', comparison['state'])
        tx = bundle['rpcEvidence']['transaction']['result']
        require(tx['transaction']['signatures'] == verified['signatures'], 'receipt-signature-vector-mismatch')
        failed = comparison['state'] == 'finalized-failure-fee-only'
        keys = binding(tx)[1]
        pre, post = token_maps(tx['meta'], keys)
        managed = {intent[s]['account'] for s in ('source', 'destination')}
        for account in set(pre) | set(post):
            if account not in managed and any(m.get(account, {}).get('owner') == intent['wallet'] for m in (pre, post)):
                i = keys.index(account)
                require(tx['meta']['preBalances'][i] == tx['meta']['postBalances'][i],
                        'unexpected-other-wallet-account-native-change')
        flows = {} if failed else transfer_flows(intent, tx, comparison['tokenAccounts'])
        backing = {}
        keys = binding(tx)[1]
        for side in ('source', 'destination'):
            if intent[side]['mint'] == NATIVE:
                i = keys.index(intent[side]['account']); amounts = comparison['tokenAccounts'][side]
                reserve = tx['meta']['preBalances'][i] - atomic(amounts['preAtomic'])
                require(reserve > 0 and tx['meta']['postBalances'][i] - atomic(amounts['postAtomic']) == reserve,
                        'wrapped-native-backing-mismatch')
                backing[side] = {'impliedBackingReserveLamports': str(reserve)}
        result.update(state='finalized-failure-fee-only' if failed else 'signed-token-accounting-consistent',
                      intentSha256=digest(intent), evidenceSha256=digest(bundle['rpcEvidence']),
                      slot=tx['slot'], tokenAccounts=comparison['tokenAccounts'], native=comparison['native'],
                      transferFlows=flows, wrappedNative=backing)
    except EvidenceError as e:
        result.update(state=e.state, reason=e.reason)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError, RecursionError):
        result.update(state='invalid-input', reason='malformed-contract-or-evidence')
    return result
