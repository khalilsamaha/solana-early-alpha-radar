"""Read-only deployment observations, not program trust or execution authorization."""
import base64
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'swap-state'))
from state import (PROGRAM, LOADER, GENESIS, StateError, need, integer, account,
                   received, snapshot, b58, digest)

MAX_ACCOUNT = 2 * 1024 * 1024
MAX_BASE64 = 4 * ((MAX_ACCOUNT + 2) // 3)
IDENTITY_FIELDS = ('program', 'programDataAddress', 'deploymentSlot', 'upgradeAuthority',
                   'accountDataBytes', 'payloadBytes', 'payloadSha256', 'metadataSha256')


def boundaries():
    return dict(signingApproved=False, executionApproved=False, transactionsSent=0,
                signaturesCreated=0, ledgerUpdated=False, sourceEquivalenceVerified=False,
                programSafetyVerified=False, independentConsensusVerified=False,
                futureUpgradePrevented=False)


def program_pointer(row):
    raw = account(row, LOADER, 36, True)
    need(raw[:4] == b'\x02\0\0\0' and raw[4:] != bytes(32),
         'program-account-layout', 'unsupported')
    return b58(raw[4:])


def deployment(row, slot):
    need(row is not None, 'programdata-unavailable', 'unavailable')
    need(type(row) is dict, 'programdata-shape', 'invalid-input')
    need(row.get('owner') == LOADER and row.get('executable') is False,
         'programdata-owner-or-executable')
    need(integer(row.get('lamports'), 1), 'programdata-lamports')
    data = row.get('data')
    need(type(data) is list and len(data) == 2 and data[1] == 'base64' and
         type(data[0]) is str and len(data[0]) <= MAX_BASE64,
         'programdata-encoding-or-cap', 'unsupported')
    try:
        raw = base64.b64decode(data[0], validate=True)
    except ValueError:
        raise StateError('programdata-base64', 'invalid-input') from None
    need(base64.b64encode(raw).decode() == data[0], 'programdata-noncanonical', 'invalid-input')
    need(109 <= len(raw) <= MAX_ACCOUNT, 'programdata-size', 'unsupported')
    need(raw[:4] == b'\x03\0\0\0', 'programdata-tag', 'unsupported')
    deployed_slot = int.from_bytes(raw[4:12], 'little')
    need(deployed_slot <= slot, 'deployment-slot-after-snapshot')
    # Bincode Option<Pubkey>: one-byte tag, not the four-byte SPL COption.
    need(raw[12] in (0, 1), 'programdata-authority-option', 'unsupported')
    authority = b58(raw[13:45]) if raw[12] else None
    payload = raw[45:]
    # Only identify the ELF envelope. This is deliberately not a verifier or loader.
    need(payload[:7] == b'\x7fELF\x02\x01\x01', 'program-payload-envelope', 'unsupported')
    return dict(deploymentSlot=deployed_slot, upgradeAuthority=authority,
                accountDataBytes=len(raw), payloadBytes=len(payload),
                payloadSha256=hashlib.sha256(payload).hexdigest(),
                metadataSha256=hashlib.sha256(raw[:45]).hexdigest(),
                accountDataSha256=hashlib.sha256(raw).hexdigest(),
                payloadIncludesAllocationPadding=True, elfEnvelopeRecognized=True)


def audit(capture):
    result = dict(format='swap-program-review-1', state='unavailable', **boundaries())
    try:
        need(type(capture) is dict and capture.get('format') == 'swap-program-capture-1' and
             capture.get('network') == 'devnet' and capture.get('program') == PROGRAM,
             'capture-format-or-program', 'invalid-input')
        need(integer(capture.get('startedAtMs')) and integer(capture.get('finishedAtMs')) and
             0 <= capture['finishedAtMs'] - capture['startedAtMs'] <= 45000,
             'capture-time-window', 'invalid-input')
        need(capture.get('origin') in ('public-rpc-capture', 'synthetic-offline'),
             'capture-origin', 'invalid-input')
        ev = capture.get('evidence')
        need(type(ev) is dict, 'capture-evidence', 'invalid-input')
        for name in ('genesisBefore', 'genesisAfter'):
            need(received(ev, name) == GENESIS['devnet'], 'wrong-cluster')
        bootstrap_slot, bootstrap = snapshot(received(ev, 'bootstrap'), 1)
        address = program_pointer(bootstrap[0])
        need(address not in (PROGRAM, LOADER), 'programdata-role-alias')
        need(capture.get('accountKeys') == [PROGRAM, address], 'account-key-binding')
        slot, rows = snapshot(received(ev, 'accounts'), 2)
        need(slot >= bootstrap_slot, 'snapshot-slot-regression')
        need(program_pointer(rows[0]) == address, 'program-pointer-changed')
        info = deployment(rows[1], slot)
        block_time = received(ev, 'blockTime')
        need(integer(block_time, 1), 'block-time-unavailable', 'unavailable')
        need(capture.get('blockTimeSlot') == slot, 'block-time-slot-binding')
        result.update(state='deployment-observed', program=PROGRAM, programDataAddress=address,
                      snapshotSlot=slot, blockTime=block_time, stateAsOfMs=capture['finishedAtMs'],
                      captureSha256=digest(capture), origin=capture['origin'], **info)
        result['fingerprintSha256'] = digest({k: result[k] for k in IDENTITY_FIELDS})
        result['observations'] = ['upgrade-authority-present' if info['upgradeAuthority'] else
                                  'no-upgrade-authority-at-observed-slot',
                                  'source-build-equivalence-unverified', 'single-rpc-observation']
    except StateError as exc:
        result.update(state=exc.state, reason=exc.reason)
    except (ValueError, TypeError, KeyError, IndexError):
        result.update(state='invalid-input', reason='malformed-capture')
    return result


def compare(current, baseline):
    """Derive both identities from raw captures; never trust a supplied review/hash."""
    result = dict(state='not-compared', **boundaries())
    if baseline is None:
        return result
    left, right = audit(baseline), audit(current)
    if left['state'] != 'deployment-observed' or right['state'] != 'deployment-observed':
        return dict(result, state='comparison-unavailable', reason='capture-not-observed')
    if left['origin'] != right['origin']:
        return dict(result, state='comparison-unavailable', reason='mixed-evidence-origins')
    if right['snapshotSlot'] < left['snapshotSlot'] or right['stateAsOfMs'] < left['stateAsOfMs']:
        return dict(result, state='comparison-unavailable', reason='comparison-time-regression')
    changed = [k for k in IDENTITY_FIELDS if left[k] != right[k]]
    return dict(result, state='deployment-changed' if changed else 'deployment-unchanged',
                changedFields=changed, baselineCaptureSha256=left['captureSha256'],
                currentCaptureSha256=right['captureSha256'], baselineSlot=left['snapshotSlot'],
                currentSlot=right['snapshotSlot'], sameCapture=left['captureSha256'] == right['captureSha256'],
                baselineTrusted=False)
