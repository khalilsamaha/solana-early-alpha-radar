"""Replayable transaction identity check; never creates an intent or mutates a ledger."""
import json
from pathlib import Path
import subprocess
import sys

from recorded_capture import GENESIS, META, MAX_CAPTURE, SYSTEM, TOKEN
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'intent-journal'))
from wire import decode_wire, verify_signed_message
from reconcile import EvidenceError, binding, digest, token_maps
from reader import base58, integer


class CheckError(Exception):
    def __init__(self, state, reason): self.state, self.reason = state, reason


def require(ok, reason, state='mismatch'):
    if not ok: raise CheckError(state, reason)


def review(capture):
    result = {'format': 'recorded-chain-review-1', 'state': 'unknown', 'reason': None,
        'signatureVerified': False, 'rpcClusterIdentityMatched': False, 'rpcFinalized': False,
        'wireAndJsonMatched': False, 'lookupResolution': 'not-assessed', 'intentProven': False, 'executionApproved': False,
        'resubmitAllowed': False, 'ledgerUpdated': False, 'reviewNetworkRequests': 0,
        'limitations': ['RPC genesis and finality are trusted endpoint reports, not independent consensus proofs.',
            'Signatures authenticate signed bytes, not RPC balances or program execution results.',
            'A historical transaction cannot establish a prior registered intent; no intent is reconstructed.',
            'Identity verification does not prove a swap, safe program semantics, spendability or profitability.',
            'Legacy/v0 signed messages supported; ALT references are signed but resolved addresses remain RPC claims. Newer versions unsupported.',
            'Replay origin/time/request metadata are supplied provenance, not cryptographically authenticated.']}
    try:
        require(isinstance(capture, dict) and capture.get('format') == 'recorded-chain-capture-1', 'capture-format', 'invalid-input')
        require(len(json.dumps(capture, allow_nan=False)) <= MAX_CAPTURE, 'capture-byte-cap', 'invalid-input')
        result['captureSha256'] = digest(capture)
        network = capture['network']
        require(network in GENESIS, 'unsupported-network', 'invalid-input')
        require(capture.get('origin') in ('public-rpc-capture', 'synthetic-fixture'), 'capture-origin', 'invalid-input')
        result.update(network=network, origin=capture['origin'], capturedAtMs=capture.get('finishedAtMs'))
        require(integer(capture['startedAtMs']) and integer(capture['finishedAtMs']) and
                capture['finishedAtMs'] >= capture['startedAtMs'], 'invalid-capture-times', 'invalid-input')
        ev = capture['evidence']
        for key in ('genesisBefore', 'genesisAfter'):
            require(ev[key]['state'] == 'received', 'cluster-evidence-incomplete', 'unknown')
            require(ev[key].get('result') == GENESIS[network], 'network-genesis-mismatch')
        result['rpcClusterIdentityMatched'] = True
        signature = capture['signature']; base58(signature, 64)
        result['signature'] = signature
        selection = capture['selection']
        require(selection in ('recent-system-program-devnet', 'recent-token-program-devnet', 'explicit-signature'), 'invalid-selection', 'invalid-input')
        discovered = None
        if selection in ('recent-system-program-devnet', 'recent-token-program-devnet'):
            require(network == 'devnet', 'sample-network-mismatch')
            require(ev['discovery']['state'] == 'received', 'discovery-unavailable', 'unknown')
            rows = ev['discovery']['result']
            require(isinstance(rows, list) and len(rows) == 1, 'discovery-empty-or-invalid', 'unknown')
            discovered = rows[0]
            require(discovered['signature'] == signature and discovered['confirmationStatus'] == 'finalized', 'discovery-identity-mismatch')
        for key in ('transactionJson', 'transactionBase64', 'signatureStatus'):
            require(ev[key]['state'] == 'received', 'rpc-evidence-incomplete', 'unknown')
        tx, binary = ev['transactionJson']['result'], ev['transactionBase64']['result']
        status = ev['signatureStatus']['result']
        require(isinstance(status, dict) and isinstance(status.get('value'), list) and len(status['value']) == 1, 'invalid-status', 'invalid-input')
        row = status['value'][0]
        require(tx is not None and binary is not None and row is not None, 'transaction-history-unavailable', 'unknown')
        require(isinstance(row, dict) and row.get('confirmationStatus') == 'finalized', 'transaction-not-finalized', 'unknown')
        require(integer(tx.get('slot')) and integer(binary.get('slot')) and integer(row.get('slot')) and
                tx['slot'] == binary['slot'] == row['slot'], 'slot-disagreement')
        context = status.get('context', {}).get('slot')
        require(integer(context) and context >= row['slot'], 'invalid-status-context')
        require(tx['version'] == binary['version'], 'version-disagreement')
        meta, binary_meta = tx['meta'], binary['meta']
        require(isinstance(meta, dict) and isinstance(binary_meta, dict), 'transaction-metadata-unavailable', 'unknown')
        require('err' in meta and 'err' in row and row['err'] == meta['err'], 'status-error-disagreement')
        # Compare only the captured reconciliation fields, not nondeterministic RPC
        # decorations such as logs/returnData. Missing and empty remain distinct.
        require({k: meta[k] for k in META if k in meta} == {k: binary_meta[k] for k in META if k in binary_meta}, 'cross-encoding-metadata-disagreement')
        if discovered is not None:
            require(integer(discovered['slot']) and discovered['slot'] == tx['slot'] and discovered['err'] == meta['err'], 'discovery-slot-or-error-disagreement')
        result['rpcFinalized'] = True
        wire_data = binary['transaction']
        require(isinstance(wire_data, list) and len(wire_data) == 2 and wire_data[1] == 'base64', 'unsupported-binary-encoding', 'unsupported')
        parsed = decode_wire(wire_data[0])
        verified = verify_signed_message(wire_data[0])
        result['signatureVerified'] = True
        _, keys, normalized_instructions = binding(tx)
        require(verified['signatures'][0] == signature and verified['signatures'] == tx['transaction']['signatures'], 'transaction-signature-disagreement')
        def normalized(message, instructions):
            return {'header': message['header'], 'accountKeys': message['accountKeys'],
                'recentBlockhash': message['recentBlockhash'], 'addressTableLookups': message.get('addressTableLookups', []),
                'instructions': instructions}
        decoded = parsed[4]['transaction']['message']
        require(normalized(tx['transaction']['message'], normalized_instructions) == normalized(decoded, decoded['instructions'])
                and parsed[4]['version'] == tx['version'], 'wire-json-message-disagreement')
        if discovered is not None:
            sampled_program = TOKEN if selection == 'recent-token-program-devnet' else SYSTEM
            require(sampled_program in keys, 'sample-account-not-in-transaction')
        for field in ('preBalances', 'postBalances'):
            require(isinstance(meta.get(field), list) and len(meta[field]) == len(keys) and all(integer(v) for v in meta[field]), 'invalid-native-balances', 'invalid-input')
        require(integer(meta.get('fee')), 'invalid-fee', 'invalid-input')
        # Validate recorded token data if available. Absence stays explicit and does
        # not block cryptographic transaction identity (e.g. native-only transfer).
        token_state = 'unavailable'
        if meta.get('preTokenBalances') is not None and meta.get('postTokenBalances') is not None:
            token_maps(meta, keys)
            token_state = 'recorded'
        lookups = verified['addressLookupCount']
        result.update(state='signed-message-consistent-lookup-unverified' if lookups else 'signed-transaction-consistent',
            wireAndJsonMatched=True, lookupResolution='unverified-rpc-addresses' if lookups else 'not-required',
            addressLookupCount=lookups,
            slot=tx['slot'], version=tx['version'], wireSha256=verified['wireSha256'],
            wireMessageSha256=verified['wireMessageSha256'], requiredSignatures=verified['requiredSignatures'],
            transactionOutcome='rpc-reported-success' if meta['err'] is None else 'rpc-reported-failure',
            tokenEvidence=token_state, native={'feePayer': keys[0], 'feeLamports': str(meta['fee']),
                'feePayerDeltaLamports': str(meta['postBalances'][0] - meta['preBalances'][0])})
    except CheckError as e:
        result.update(state=e.state, reason=e.reason)
    except EvidenceError as e:
        result.update(state=e.state, reason=e.reason)
    except ValueError as e:
        known = str(e)
        if known in ('address-lookup-resolution-not-supported', 'unsupported-message-version'):
            result.update(state='unsupported', reason=known)
        elif known == 'invalid-ed25519-signature':
            result.update(state='mismatch', reason=known)
        elif known == 'node-runtime-unavailable':
            result.update(state='unknown', reason='signature-verifier-unavailable')
        else: result.update(state='invalid-input', reason='malformed-capture-or-wire')
    except (subprocess.SubprocessError, OSError):
        result.update(state='unknown', reason='signature-verifier-unavailable')
    except (KeyError, TypeError, AttributeError, IndexError, OverflowError, RecursionError):
        result.update(state='invalid-input', reason='malformed-capture-or-wire')
    return result
