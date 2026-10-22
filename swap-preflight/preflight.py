"""Unified raw-evidence preflight; never an exported signing authorization."""
import copy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'swap-program'))
from program import (audit as program_audit, IDENTITY_FIELDS, program_pointer, boundaries)
from state import (audit as state_audit, PROGRAM, GENESIS, StateError, need, received,
                   snapshot, decode_pool, account_keys, integer, digest, key, validate, Rejected)
from baseline import BASELINE


def flags():
    return dict(boundaries(), simulationApproved=False, signerConnected=False, positionBookConnected=False)


def split_capture(c):
    """Both readers receive slices of the same raw batch, not independently supplied reports."""
    need(type(c) is dict and c.get('format') == 'swap-preflight-capture-1' and
         c.get('network') == 'devnet', 'capture-format', 'invalid-input')
    need(c.get('origin') in ('synthetic-offline', 'public-rpc-capture'), 'capture-origin', 'invalid-input')
    ev = c.get('evidence'); need(type(ev) is dict, 'capture-evidence', 'invalid-input')
    pool_key = key(c.get('pool')); packet = c.get('packet')
    need(c.get('selection') == ('prior-packet' if packet is not None else 'explicit-pool'),
         'capture-selection', 'invalid-input')
    pslot, prows = snapshot(received(ev, 'programBootstrap'), 1)
    pointer = program_pointer(prows[0])
    sslot, srows = snapshot(received(ev, 'poolBootstrap'), 1)
    need(sslot >= pslot, 'bootstrap-slot-regression')
    pool = decode_pool(srows[0])
    keys = account_keys(pool_key, pool, packet)
    need(pointer not in keys, 'programdata-role-alias')
    need(c.get('accountKeys') == keys + [pointer], 'combined-key-binding')
    slot, rows = snapshot(received(ev, 'accounts'), len(keys)+1)
    need(slot >= sslot, 'snapshot-slot-regression')
    common = {k: c[k] for k in ('network', 'origin', 'startedAtMs', 'finishedAtMs', 'blockTimeSlot')}
    shared = {k: ev[k] for k in ('genesisBefore', 'genesisAfter', 'blockTime')}
    state = dict(common, format='cpmm-state-capture-1', pool=pool_key, packet=packet,
                 selection=c['selection'], accountKeys=keys, messageSha256=c.get('messageSha256'),
                 evidence=dict(shared, bootstrap=ev['poolBootstrap'],
                               accounts={'state':'received','result':{'context':{'slot':slot},'value':rows[:-1]}},
                               blockhash=ev.get('blockhash'), fee=ev.get('fee')))
    program = dict(common, format='swap-program-capture-1', program=PROGRAM,
                   accountKeys=[PROGRAM, pointer], evidence=dict(shared, bootstrap=ev['programBootstrap'],
                    accounts={'state':'received','result':{'context':{'slot':slot},'value':[rows[7], rows[-1]]}}))
    return state, program


def _review(capture, baseline, now_ms):
    """Pure evaluator; injectable baseline is for synthetic regression, not a CLI override."""
    result = dict(format='swap-preflight-review-1', state='unavailable', **flags())
    try:
        need(integer(now_ms), 'review-clock', 'invalid-input')
        need(type(capture) is dict and not capture.get('stoppedReason'), 'capture-incomplete', 'unavailable')
        state_capture, program_capture = split_capture(capture)
        result['poolReview'] = s = state_audit(state_capture)
        result['programReview'] = p = program_audit(program_capture)
        need(s['state'] in ('pool-state-consistent', 'policy-state-consistent'),
             'pool-check-' + s.get('reason', s['state']), s['state'] if s['state'] in ('unavailable','unsupported') else 'mismatch')
        need(p['state'] == 'deployment-observed', 'program-check-' + p.get('reason', p['state']),
             p['state'] if p['state'] in ('unavailable','unsupported') else 'mismatch')
        need(s['snapshotSlot'] == p['snapshotSlot'] and s['programDataAddress'] == p['programDataAddress'],
             'pool-program-binding')
        need(baseline['network'] == 'devnet', 'baseline-network', 'invalid-input')
        expected_origin = 'synthetic-offline' if baseline['kind'] == 'synthetic-test-baseline' else 'public-rpc-capture'
        need(capture['origin'] == expected_origin, 'baseline-origin-mismatch')
        need(p['snapshotSlot'] >= baseline['observedSlot'] and capture['startedAtMs'] >= baseline['observedAtMs'],
             'capture-predates-baseline')
        changed = [k for k in IDENTITY_FIELDS if p[k] != baseline['identity'][k]]
        result.update(baselineId=baseline['id'], baselineKind=baseline['kind'],
                      baselineSha256=digest(baseline), changedDeploymentFields=changed)
        need(not changed, 'deployment-differs-from-pinned-observation')
        result['observedBaselineMatched'] = True
        need(0 <= now_ms-capture['finishedAtMs'] <= 10000, 'evidence-stale-or-future', 'unavailable')
        observed_at = capture['evidence']['accounts'].get('receivedAtMs')
        need(integer(observed_at) and capture['startedAtMs'] <= observed_at <= capture['finishedAtMs'],
             'account-observation-clock', 'invalid-input')
        need(0 <= now_ms-observed_at <= 10000, 'account-evidence-stale', 'unavailable')
        need(not s['eligibilityBlockers'], 'pool-eligibility-blocked')
        result['riskObservations'] = ['mint-authority-present'] if any(m['mintAuthority'] for m in s['mints']) else []
        packet = capture.get('packet')
        if packet is not None:
            for name in ('blockhash', 'fee'):
                at = capture['evidence'][name].get('receivedAtMs')
                need(integer(at) and observed_at <= at <= capture['finishedAtMs'],
                     'message-evidence-clock', 'invalid-input')
            checked = validate(packet, now_ms=now_ms)
            need(checked['state'] == 'instruction-policy-match', 'packet-expired-or-invalid-at-review', 'unavailable')
            need(s['state'] == 'policy-state-consistent', 'wallet-policy-evidence-missing')
            result.update(state='preflight-evidence-consistent', wireMessageSha256=checked['wireMessageSha256'],
                          policySha256=checked['policySha256'],
                          walletAndFeeChecked=True,
                          validUntilExclusiveMs=min(checked['validUntilExclusiveMs'],observed_at+10001))
        else:
            result.update(state='pinned-pool-snapshot', walletAndFeeChecked=False,
                          validUntilExclusiveMs=observed_at+10001)
        result.update(snapshotSlot=s['snapshotSlot'], stateAsOfMs=capture['finishedAtMs'],
                      reviewedAtMs=now_ms, captureSha256=digest(capture))
    except StateError as exc:
        result.update(state=exc.state, reason=exc.reason)
    except (ValueError, TypeError, KeyError, IndexError, Rejected):
        result.update(state='invalid-input', reason='malformed-preflight')
    return result


def audit(capture, *, now_ms):
    # No capture-supplied baseline, hash, review or permission field is trusted.
    return _review(capture, copy.deepcopy(BASELINE), now_ms)
