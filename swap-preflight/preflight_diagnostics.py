"""Bounded explanations for an incomplete capture. Never changes acceptance."""
from preflight import BASELINE
from program import deployment, program_pointer, IDENTITY_FIELDS
from state import snapshot, PROGRAM, digest

NAMES = ('genesisBefore','programBootstrap','poolBootstrap','accounts','blockTime',
         'blockhash','fee','genesisAfter')
METHODS = {'getGenesisHash','getMultipleAccounts','getBlockTime','isBlockhashValid','getFeeForMessage'}
STATES = {'received','not-requested','http-error','network-error','rpc-error',
          'response-too-large','invalid-rpc-envelope','invalid-response','invalid-preflight-response'}
REASONS = {'wrong-cluster','capture-time-budget','packet-expired-during-capture',
    'program-bootstrap-predates-baseline','program-pointer-differs-from-baseline',
    'bootstrap-slot-regression','programdata-role-alias','snapshot-slot-regression',
    'program-pointer-changed','deployment-differs-from-pinned-observation',
    'invalid-capture-input-or-response','snapshot-shape','account-unavailable',
    'account-shape','account-owner-or-executable','account-lamports','account-data-encoding',
    'account-data-canonical','account-layout-size','program-account-layout',
    'programdata-unavailable','programdata-shape','programdata-owner-or-executable',
    'programdata-lamports','programdata-encoding-or-cap','programdata-base64',
    'programdata-noncanonical','programdata-size','programdata-tag',
    'deployment-slot-after-snapshot','programdata-authority-option','program-payload-envelope',
    'account-discriminator','token-program-unsupported','pool-role-alias',
    'pool-authority-bump','pool-status-or-fee-layout','snapshot-role-alias'} | {'rpc-stopped-'+n for n in NAMES}


def describe(capture, *, baseline=None):
    """Only enum codes, bounded numbers and decoded public identities are exported.

    The CLI has no baseline override. The injectable argument supports synthetic
    tests; callers supply the same internally pinned baseline as the collector.
    A missing final genesis/time check still blocks preflight, even if a partial
    account batch can explain a deployment difference.
    """
    baseline = BASELINE if baseline is None else baseline
    result = dict(format='preflight-capture-diagnostics-1', stoppedReason='unclassified',
        requests=[], evidenceStates={}, deploymentComparison=dict(state='unavailable'),
        diagnosticOnly=True, executionApproved=False, baselineChanged=False)
    if type(capture) is not dict: return result
    reason = capture.get('stoppedReason')
    result['stoppedReason'] = reason if type(reason) is str and reason in REASONS else None if reason is None else 'unclassified'
    requests = capture.get('requests')
    if type(requests) is list:
        for r in requests[:8]:
            if type(r) is not dict: result['requests'].append({'state':'unclassified'}); continue
            method, state = r.get('method'), r.get('state')
            row = dict(method=method if type(method) is str and method in METHODS else 'unclassified',
                       state=state if type(state) is str and state in STATES else 'unclassified')
            if type(r.get('httpStatus')) is int and 100 <= r['httpStatus'] <= 599:
                row['httpStatus'] = r['httpStatus']
            if type(r.get('elapsedMs')) is int and 0 <= r['elapsedMs'] <= 60000:
                row['elapsedMs'] = r['elapsedMs']
            result['requests'].append(row)
        result['requestListTruncated'] = len(requests) > 8
    ev = capture.get('evidence')
    if type(ev) is not dict: return result
    for name in NAMES:
        item = ev.get(name)
        state = item.get('state') if type(item) is dict else None
        result['evidenceStates'][name] = state if type(state) is str and state in STATES else 'unclassified'
        # HTTP codes live on evidence items in Client, not its request log.
        code = item.get('httpStatus') if type(item) is dict else None
        if type(code) is int and 100 <= code <= 599:
            result.setdefault('httpStatuses',{})[name] = code
    try:
        keys = capture['accountKeys']
        if (capture.get('network') != 'devnet' or type(keys) is not list or len(keys) not in (9,12)
                or keys[7] != PROGRAM or ev['accounts']['state'] != 'received'):
            return result
        slot, rows = snapshot(ev['accounts']['result'],len(keys))
        pointer = program_pointer(rows[7])
        if keys[-1] != pointer or slot < baseline['observedSlot']: return result
        observed = dict(deployment(rows[-1],slot),program=PROGRAM,programDataAddress=pointer)
        identity = {k:observed[k] for k in IDENTITY_FIELDS}
        changed = [k for k in IDENTITY_FIELDS if identity[k] != baseline['identity'][k]]
        result['deploymentComparison'] = dict(state='different-from-pin' if changed else 'matches-pin',
            snapshotSlot=slot, observedIdentity=identity, observedIdentitySha256=digest(identity),
            baselineIdentitySha256=digest({k:baseline['identity'][k] for k in IDENTITY_FIELDS}),
            changedFields=changed, partialCaptureOnly=reason is not None)
    except (ValueError,KeyError,TypeError,IndexError):
        pass
    return result
