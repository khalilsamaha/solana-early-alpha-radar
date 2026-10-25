"""One controlled devnet swap. Immutable attempt boundary; recovery never broadcasts."""
import base64
import copy
import json
import os
from pathlib import Path
import time

import controlled_swap as bridge
import spend_guard
import cycle_binding
from controlled_swap import pool, swap
from fresh_packet import build
from core import Session, check, directory, private_file, loads, write_new, sync_directory, received, context_value, integer
from contract import atomic, decode_wire
from recorded_capture import Client, GENESIS

CHILD = 'swap-execution-v1'
VERSION = 'controlled-pool-swap-execution-1'
REVERSE_CHILD = 'swap-reverse-v1'
REVERSE_VERSION = 'controlled-pool-reverse-swap-1'
TERMINAL = ('finalized-success', 'finalized-failure', 'quarantined')
TOKEN_ROLES = ('source', 'destination', 'inputVault', 'outputVault')


def journal_name(reverse=False):
    check(type(reverse) is bool, 'explicit-direction-required')
    return REVERSE_CHILD if reverse else CHILD


def forward_evidence(home, wallet):
    r = report(home, wallet)
    check(r['state'] == 'finalized-success' and r['submissionBoundaryRecorded']
          and not r['signatureOutcomeUnknown'], 'finalized-entry-required')
    return r


def reverse_scope(home, wallet):
    entry = forward_evidence(home, wallet)
    rec = entry['observation']['receipt']
    quantity = atomic(rec['outputAtomic'], 'entry-output', positive=True)
    check(990 <= quantity <= 1000, 'reverse-input-cap')
    scope = copy.deepcopy(entry['scope'])
    a = scope['accounts']
    for left, right in (('source', 'destination'), ('inputVault', 'outputVault'), ('inputMint', 'outputMint')):
        a[left], a[right] = a[right], a[left]
    scope['amountIn'] = str(quantity)
    # Fixed test policy for the equal-seed-reserve pair, not a route-derived price.
    scope['minimumAmountOut'] = str(quantity * 99 // 100)
    proof = dict(signature=entry['signature'], wireSha256=entry['wireSha256'],
                 messageSha256=entry['messageSha256'], blockhash=entry['intent']['blockhash'],
                 receiptSlot=rec['slot'], receiptSha256=pool.digest(rec),
                 scopeSha256=pool.digest(entry['scope']), receivedAtomic=str(quantity))
    return scope, proof, rec


def verify_forward_on_chain(rpc, home, wallet, expected):
    child = home / CHILD
    plan, wire, signed, evidence = bound(child, wallet)
    genesis(rpc)
    st = signature_status(rpc, signed['signatures'][0], evidence['contextSlot'])
    check(st is not None and st['confirmationStatus'] == 'finalized', 'entry-finality-unavailable')
    tx = transaction(rpc, signed['signatures'][0]); genesis(rpc)
    check(tx is not None, 'entry-receipt-unavailable')
    checked = receipt(tx, st, plan, wire, signed, read(child, 'presend-preflight.json', 4 * 1024 * 1024))
    check(checked == expected, 'entry-current-receipt-mismatch')


def continuity(capture, entry):
    slot = capture['evidence']['accounts']['result']['context']['slot']
    check(integer(slot) and slot >= entry['slot'], 'entry-continuity-slot')
    rows = dict(zip(capture['accountKeys'], capture['evidence']['accounts']['result']['value']))
    wallet = capture['packet']['policy']['accounts']['wallet']
    check(rows[wallet]['lamports'] == int(entry['walletAfterLamports']), 'entry-wallet-continuity')
    for role in ('source', 'destination'):
        e = entry['tokenEffects'][role]
        current = swap.token(rows[e['account']], e['mint'], wallet)
        check(int(current['amount']) == int(e['afterAtomic']), 'entry-holder-continuity')


def round_trip(entry, exit_receipt):
    check(entry['state'] == 'finalized-success' and exit_receipt['state'] in ('finalized-success', 'finalized-failure'), 'round-trip-states')
    check(entry['signature'] != exit_receipt['signature'] and exit_receipt['slot'] >= entry['slot'], 'round-trip-order')
    first, last = entry['tokenEffects'], exit_receipt['tokenEffects']
    for a, b in (('source', 'destination'), ('destination', 'source')):
        check(first[a]['account'] == last[b]['account'] and first[a]['mint'] == last[b]['mint']
              and first[a]['afterAtomic'] == last[b]['beforeAtomic'], 'round-trip-holder-continuity')
    check(entry['walletAfterLamports'] == exit_receipt['walletBeforeLamports'], 'round-trip-wallet-continuity')
    received_amount = int(entry['outputAtomic'])
    spent = int(exit_receipt['inputAtomic'])
    closed = exit_receipt['state'] == 'finalized-success'
    check(spent == (received_amount if closed else 0), 'round-trip-exact-exit-quantity')
    total_fee = int(entry['feeLamports']) + int(exit_receipt['feeLamports'])
    check(total_fee <= 20000 and int(entry['walletBeforeLamports']) - int(exit_receipt['walletAfterLamports']) == total_fee, 'round-trip-fee-conservation')
    net_original = int(last['destination']['afterAtomic']) - int(first['source']['beforeAtomic'])
    residual = int(last['source']['afterAtomic']) - int(first['destination']['beforeAtomic'])
    check(residual == received_amount - spent and net_original == int(exit_receipt['outputAtomic']) - int(entry['inputAtomic']), 'round-trip-token-conservation')
    return dict(state='round-trip-reconciled' if closed else 'exit-failed-position-open',
                entrySignature=entry['signature'], exitSignature=exit_receipt['signature'],
                originalMint=first['source']['mint'], acquiredMint=first['destination']['mint'],
                entryInputAtomic=entry['inputAtomic'], acquiredAtomic=entry['outputAtomic'],
                exitInputAtomic=exit_receipt['inputAtomic'], returnedOriginalAtomic=exit_receipt['outputAtomic'],
                netOriginalTokenAtomic=str(net_original), residualAcquiredTokenAtomic=str(residual),
                entryFeeLamports=entry['feeLamports'], exitFeeLamports=exit_receipt['feeLamports'], totalFeeLamports=str(total_fee),
                walletBeforeLamports=entry['walletBeforeLamports'], walletAfterLamports=exit_receipt['walletAfterLamports'],
                evidenceBasis='Two exact finalized receipts with wallet/holder continuity; fees kept in native units',
                profitabilityClaim=False, productionPositionUpdated=False)


def now():
    return time.time_ns() // 1000000


def read(child, name, maximum=32768):
    return loads(private_file(child / name, maximum))


class Trace:
    """Count actual HTTP attempts across bounded collectors, without exporting payloads."""
    def __init__(self, opener=None, recovery=False):
        self.opener = opener or Client('devnet').opener
        self.calls = []
        self.recovery = recovery
    def open(self, request, timeout=None):
        q = loads(request.data)
        check(request.full_url == 'https://api.devnet.solana.com', 'devnet-endpoint-only')
        check(len(self.calls) < (12 if self.recovery else 64), 'total-request-cap')
        if self.recovery:
            check(q['method'] in RecoveryRpc.METHODS, 'recovery-read-only')
        if q['method'] == 'sendTransaction':
            check(not any(c['method'] == 'sendTransaction' for c in self.calls), 'one-send-only')
        self.calls.append(dict(method=q['method'], atMs=now()))
        return self.opener.open(request, timeout=timeout)


class ExecutionRpc(Client):
    METHODS = ('getGenesisHash', 'isBlockhashValid', 'getSignatureStatuses', 'getTransaction', 'getBlockHeight', 'sendTransaction')
    REQUEST_CAP = 32
    def __init__(self, opener=None):
        super().__init__('devnet', opener)


class RecoveryRpc(ExecutionRpc):
    METHODS = ('getGenesisHash', 'getSignatureStatuses', 'getTransaction', 'getBlockHeight')
    REQUEST_CAP = 12


def genesis(rpc):
    check(received(rpc.request('getGenesisHash', [])) == GENESIS['devnet'], 'wrong-cluster')


def signature_status(rpc, signature, minimum_slot):
    slot, rows = context_value(rpc.request('getSignatureStatuses', [[signature], {'searchTransactionHistory': True}]), minimum_slot)
    check(type(rows) is list and len(rows) == 1, 'invalid-status')
    v = rows[0]
    if v is not None:
        check(type(v) is dict and integer(v.get('slot')) and minimum_slot <= v['slot'] <= slot
              and 'err' in v and v.get('confirmationStatus') in ('processed', 'confirmed', 'finalized'), 'invalid-status')
        if v['confirmationStatus'] == 'finalized':
            check(v.get('confirmations') is None, 'invalid-finality')
    return v


def transaction(rpc, signature):
    return received(rpc.request('getTransaction', [signature, dict(encoding='base64', commitment='finalized', maxSupportedTransactionVersion=0)]))


def old_simulation(home, scope):
    """Replay successful local simulation; never modify that journal or use its wire for sending."""
    child = home / swap.CHILD
    directory(child)
    plan = read(child, 'plan.json')
    check(plan.get('format') == 'swap-signing-plan-1' and plan.get('scope') == scope, 'prior-simulation-scope')
    check(not os.path.lexists(child / 'failure.json'), 'prior-simulation-failed')
    capture = read(child, 'preflight.json', 4 * 1024 * 1024)
    check(capture.get('packet') == plan['packet'], 'prior-preflight-binding')
    check(swap.audit(capture, now_ms=capture['finishedAtMs'])['state'] == 'preflight-evidence-consistent', 'prior-preflight-invalid')
    wire = read(child, 'signed.json', 8192)['wire']
    checked = swap.simulation_review(plan['packet'], capture, wire, read(child, 'simulation-response.json'))
    check(checked == read(child, 'simulation-review.json'), 'prior-simulation-review-mismatch')
    return dict(signature=checked['signature'], wireSha256=checked['wireSha256'],
                blockhash=plan['packet']['policy']['blockhash'], simulationSlot=checked['simulationSlot'],
                reviewSha256=pool.digest(checked))


def prior_absent_and_expired(rpc, prior):
    genesis(rpc)
    _, valid = context_value(rpc.request('isBlockhashValid', [prior['blockhash'], dict(commitment='finalized', minContextSlot=prior['simulationSlot'])]), prior['simulationSlot'])
    check(valid is False, 'prior-simulation-blockhash-still-valid')
    check(signature_status(rpc, prior['signature'], prior['simulationSlot']) is None, 'prior-simulation-signature-observed')
    check(transaction(rpc, prior['signature']) is None, 'prior-simulation-receipt-observed')
    genesis(rpc)


def observations(child):
    paths = sorted(child.glob('observation-*.json'))
    check(len(paths) <= 32 and [p.name for p in paths] == [f'observation-{i:03d}.json' for i in range(len(paths))], 'observation-sequence')
    return [read(child, p.name) for p in paths]


def save_observation(child, item):
    old = observations(child)
    if old and old[-1]['state'] in TERMINAL:
        return
    check(len(old) < 32, 'observation-cap')
    write_new(child / f'observation-{len(old):03d}.json', dict(item, recordedAtMs=now()))


def bound(child, wallet):
    """Revalidate the canonical fixed scope and exact wire before observation or transport."""
    check(child.name in (CHILD, REVERSE_CHILD), 'unsupported-swap-journal')
    reverse = child.name == REVERSE_CHILD
    plan = read(child, 'plan.json')
    check(plan.get('format') == 'swap-signing-plan-1', 'plan-format')
    cycle_binding.plan_matches(child.parent, plan)
    scope = plan['scope']
    p = plan['packet']
    swap.policy_check(scope, p, wallet, plan['recordedAtMs'])
    if reverse:
        expected_scope, prior, _ = reverse_scope(child.parent, wallet)
        check(scope == expected_scope, 'reverse-scope-binding')
    else:
        check(scope['amountIn'] == '1000' and scope['minimumAmountOut'] == '990'
              and scope['maxComputeUnits'] == 300000 and scope['maxMicroLamportsPerCU'] == '0'
              and scope['maxPriorityFeeLamports'] == '0' and scope['maxTotalFeeLamports'] == '10000', 'fixed-scope-required')
        setup = pool.read(cycle_binding.root(child.parent) / pool.CHILD, 'plan.json')
        a = pool.addresses(setup['pairAccounts'])
        mapping = dict(source='holder0', destination='holder1', inputVault='vault0', outputVault='vault1', inputMint='mint0', outputMint='mint1')
        check(all(v == a[mapping.get(k, k)] for k, v in scope['accounts'].items()), 'controlled-accounts-required')
    wire = read(child, 'signed.json', 8192)['wire']
    signed = swap.signed_binding(p, wire)
    evidence = read(child, 'execution.json')
    check(evidence.get('format') == (REVERSE_VERSION if reverse else VERSION) and evidence.get('planSha256') == pool.digest(plan)
          and integer(evidence.get('lastValidBlockHeight')) and evidence['lastValidBlockHeight'] > 0 and integer(evidence.get('contextSlot')), 'execution-binding')
    if reverse:
        check(evidence.get('priorExecution') == prior, 'reverse-entry-proof-binding')
    return plan, wire, signed, evidence


def report(home, wallet, trace=None, reason=None, *, reverse=False):
    child = home / journal_name(reverse)
    calls = trace.calls if trace else []
    r = dict(format=REVERSE_VERSION if reverse else VERSION, state='not-started', wallet=wallet, network='devnet', reason=reason,
             networkRequests=len(calls), requests=calls,
             sendRequestsThisRun=sum(c['method'] == 'sendTransaction' for c in calls),
             submissionBoundaryRecorded=False, signaturesCreatedThisRun=0, signatureOutcomeUnknown=False,
             stopRequested=swap.stop(cycle_binding.root(home)), mainnetEnabled=False, resubmitAllowed=False,
             productionLedgerUpdated=False, positionBookConnected=False, privateKeyExported=False, signedBytesExported=False,
             limitations=[
                 'A durable send boundary can precede a crash before HTTP transport; it is not proof of delivery.',
                 'Finalized results rely on RPC evidence matched to exact locally verified signed bytes.',
                 'The signer is a same-user boundary; another holder of private signed bytes could broadcast them while valid.',
                 'Fixed test tokens and devnet fees do not measure strategy profitability or mainnet execution.',
                 'No journal replacement, automatic retry, reverse swap or production position update is enabled.'])
    if cycle_binding.is_cycle(home):
        r['cycleBinding'] = cycle_binding.load(home, wallet)
        r['cycleId'] = cycle_binding.CYCLE
        import unsigned_replacement as replacement
        if replacement.exists(home):
            m,_=replacement.ready(home)
            r['unsignedReplacement']=dict(format=replacement.VERSION,manifestSha256=replacement.digest(m),
                originalEvidenceSha256=m['evidenceSha256'],originalJournalPreserved=True)
            r['limitations'][-1]='One explicitly prepared unsigned replacement only; no automatic retry or production position update.'
    if reverse:
        r['limitations'][-1] = 'One explicit reverse of the recorded acquisition only; no journal replacement, automatic retry or production position update.'
    if not os.path.lexists(child):
        return r
    directory(child)
    r['state'] = 'preparation-incomplete'
    if os.path.lexists(child / 'signing-attempt.json'):
        r['signatureOutcomeUnknown'] = not os.path.lexists(child / 'signed.json')
    if os.path.lexists(child / 'signed.json'):
        plan, wire, signed, evidence = bound(child, wallet)
        r.update(scope=plan['scope'], signature=signed['signatures'][0], wireSha256=signed['wireSha256'],
                 messageSha256=signed['wireMessageSha256'], lastValidBlockHeight=evidence['lastValidBlockHeight'],
                 setupEvidence=evidence['setupEvidence'],
                 intent=dict(blockhash=plan['packet']['policy']['blockhash'],
                             issuedAtMs=plan['packet']['policy']['issuedAtMs'],
                             expiresAtMs=plan['packet']['policy']['expiresAtMs'],
                             quotedFeeLamports=plan['packet']['feeAssertion']['lamports'],
                             contextSlot=evidence['contextSlot']))
        r['priorExecution' if reverse else 'priorSimulation'] = evidence['priorExecution' if reverse else 'priorSimulation']
        if os.path.lexists(child / 'simulation-review.json'):
            r['simulation'] = read(child, 'simulation-review.json')
            r['state'] = 'signed-simulated-not-submitted'
    if os.path.lexists(child / 'submission-boundary.json'):
        boundary = read(child, 'submission-boundary.json')
        check(boundary['signature'] == r.get('signature') and boundary['wireSha256'] == r.get('wireSha256'), 'boundary-binding')
        r.update(state='submission-unknown', submissionBoundaryRecorded=True)
    history = observations(child)
    if history:
        last = history[-1]
        if last['state'] in ('finalized-success', 'finalized-failure'):
            stored = read(child, 'receipt-evidence.json', 131072)
            replay = receipt(stored['transaction'], stored['status'], plan, wire, signed,
                             read(child, 'presend-preflight.json', 4 * 1024 * 1024))
            check(replay == last['receipt'] and replay['state'] == last['state'], 'terminal-receipt-replay-mismatch')
        r.update(state=last['state'], observation=last)
        if reverse and last['state'] in ('finalized-success', 'finalized-failure'):
            r['roundTrip'] = round_trip(forward_evidence(home, wallet)['observation']['receipt'], last['receipt'])
    if os.path.lexists(child / 'failure.json'):
        r['failure'] = read(child, 'failure.json')
        if not r['submissionBoundaryRecorded']:
            r['state'] = 'preparation-incomplete'
    r['spendingGuard'] = spend_guard.status(home, child)
    return r


def finish_report(home, wallet, trace=None, reason=None, *, reverse=False):
    """Reconcile only replayed local finalized evidence, including after a crash."""
    r = report(home, wallet, trace, reason, reverse=reverse)
    child = home / journal_name(reverse)
    if os.path.lexists(child / spend_guard.MARKER):
        with spend_guard.Guard(home) as guard:
            guard.reconcile('exit' if reverse else 'entry', r)
        r['spendingGuard'] = spend_guard.status(home, child)
    return r


def receipt(tx, st, plan, wire, signed, capture):
    """Finalized exact-message receipt: four SPL amounts, native fee only, no ALT or rent effects."""
    check(st.get('confirmationStatus') == 'finalized' and st.get('confirmations') is None, 'receipt-finality')
    check(type(tx) is dict and tx.get('slot') == st['slot'] and integer(tx.get('slot'))
          and tx.get('version') == 'legacy' and tx['slot'] >= capture['evidence']['accounts']['result']['context']['slot'], 'receipt-slot-or-version')
    check(tx.get('transaction') == [wire, 'base64'], 'receipt-wire')
    m = tx.get('meta')
    check(type(m) is dict and 'err' in m, 'receipt-unavailable')
    check(m['err'] == st['err'], 'receipt-status-disagreement')
    p = plan['packet']; a = plan['scope']['accounts']; fee = int(p['feeAssertion']['lamports'])
    check(type(m.get('fee')) is int and m['fee'] == fee <= 10000, 'receipt-fee')
    keys = decode_wire(wire)[4]['transaction']['message']['accountKeys']
    check(m.get('loadedAddresses', {'writable': [], 'readonly': []}) == {'writable': [], 'readonly': []}, 'receipt-loaded-addresses')
    pre, post = m.get('preBalances'), m.get('postBalances')
    check(type(pre) is list and type(post) is list and len(pre) == len(post) == 14
          and all(integer(v) for v in pre + post), 'receipt-balances-unavailable')
    expected = pre.copy(); expected[0] -= fee
    check(expected[0] >= 0 and post == expected, 'receipt-native-effects')
    bykey = dict(zip(capture['accountKeys'], capture['evidence']['accounts']['result']['value']))
    check(pre[0] == bykey[a['wallet']]['lamports'], 'receipt-wallet-prebalance')
    def token_map(rows):
        check(type(rows) is list and len(rows) == 4, 'receipt-tokens-unavailable')
        out = {}
        for row in rows:
            check(type(row) is dict and integer(row.get('accountIndex')) and row['accountIndex'] < 14, 'receipt-token-index')
            k = keys[row['accountIndex']]
            check(k not in out, 'receipt-duplicate-token')
            out[k] = row
        check(set(out) == {a[n] for n in TOKEN_ROLES}, 'receipt-token-set')
        return out
    groups = [token_map(m.get(name)) for name in ('preTokenBalances', 'postTokenBalances')]
    deltas = []; effects = {}
    for i, name in enumerate(TOKEN_ROLES):
        k = a[name]; mint = a['inputMint' if i in (0, 2) else 'outputMint']; owner = a['wallet' if i < 2 else 'authority']
        values = []
        for group in groups:
            row = group[k]; u = row.get('uiTokenAmount')
            check(row.get('mint') == mint and row.get('owner') == owner and row.get('programId') == swap.TOKEN
                  and type(u) is dict and type(u.get('decimals')) is int and u['decimals'] == 6, 'receipt-token-identity')
            values.append(atomic(u.get('amount'), 'receipt-token-amount'))
        check(pre[keys.index(k)] == bykey[k]['lamports'], 'receipt-token-rent')
        if i < 2:
            check(values[0] == int(swap.token(bykey[k], mint, owner)['amount']), 'receipt-holder-prebalance')
        deltas.append(values[1] - values[0])
        effects[name] = dict(account=k, mint=mint, beforeAtomic=str(values[0]), afterAtomic=str(values[1]), deltaAtomic=str(deltas[-1]))
    failed = m['err'] is not None
    check(deltas == [0, 0, 0, 0] if failed else
          deltas[0] == -int(plan['scope']['amountIn']) and deltas[1] >= int(plan['scope']['minimumAmountOut'])
          and deltas[2] == -deltas[0] and deltas[3] == -deltas[1], 'receipt-token-effects')
    return dict(state='finalized-failure' if failed else 'finalized-success', slot=st['slot'],
                signature=signed['signatures'][0], wireSha256=signed['wireSha256'], messageSha256=signed['wireMessageSha256'],
                feeLamports=str(fee), walletBeforeLamports=str(pre[0]), walletAfterLamports=str(post[0]),
                inputAtomic='0' if failed else plan['scope']['amountIn'], outputAtomic=str(deltas[1]), tokenEffects=effects,
                evidenceBasis='RPC finalized exact signed transaction and native/SPL balance reconciliation')


def observe(child, wallet, rpc, *, sleeper=time.sleep):
    plan, wire, signed, evidence = bound(child, wallet)
    capture = read(child, 'presend-preflight.json', 4 * 1024 * 1024)
    for turn in range(3):
        if turn:
            sleeper(10)
        try:
            genesis(rpc)
            st = signature_status(rpc, signed['signatures'][0], evidence['contextSlot'])
            if st is not None and st['confirmationStatus'] == 'finalized':
                tx = transaction(rpc, signed['signatures'][0]); genesis(rpc)
                if tx is not None:
                    result = receipt(tx, st, plan, wire, signed, capture)
                    if child.name == REVERSE_CHILD:
                        round_trip(forward_evidence(child.parent, wallet)['observation']['receipt'], result)
                    # Retain bounded raw receipt fields privately, so terminal status replays
                    # accounting rather than trusting a stored 'success' label.
                    tx = dict(tx)
                    tx['meta'] = {k: tx['meta'][k] for k in ('err', 'fee', 'preBalances', 'postBalances',
                        'preTokenBalances', 'postTokenBalances', 'loadedAddresses') if k in tx['meta']}
                    record = dict(transaction=tx, status={k: st[k] for k in ('slot', 'err', 'confirmationStatus', 'confirmations')})
                    check(len(json.dumps(record).encode()) <= 131072, 'receipt-evidence-size')
                    target = child / 'receipt-evidence.json'
                    if os.path.lexists(target):
                        saved = read(child, target.name, 131072)
                        check(receipt(saved['transaction'], saved['status'], plan, wire, signed, capture) == result,
                              'receipt-record-conflict')
                    else:
                        write_new(target, record)
                    save_observation(child, dict(state=result['state'], receipt=result))
                    return
                reason = 'finalized-receipt-unavailable'
                state = 'submission-unknown'
            else:
                height = received(rpc.request('getBlockHeight', [dict(commitment='finalized', minContextSlot=evidence['contextSlot'])]))
                check(integer(height), 'invalid-block-height'); genesis(rpc)
                state = 'expired-outcome-unknown' if height > evidence['lastValidBlockHeight'] else 'submission-pending' if st else 'submission-unknown'
                reason = 'receipt-not-finalized'
            save_observation(child, dict(state=state, reason=reason))
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            code = str(exc) if type(exc) is ValueError else 'invalid-evidence'
            # Missing receipt fields remain unknown; contradictory supplied effects are quarantined.
            unavailable = ('receipt-unavailable', 'receipt-balances-unavailable', 'receipt-tokens-unavailable')
            if code.startswith(('receipt-', 'round-trip-')) and code not in unavailable:
                save_observation(child, dict(state='quarantined', reason=code))
            else:
                save_observation(child, dict(state='submission-unknown', reason='rpc-or-receipt-evidence-unavailable'))
            return


def _execute(home, wallet, expected_pool, *, reverse=False, cycle=False, replace_unsigned=False, opener=None, sleeper=time.sleep):
    trace = Trace(opener); rpc = ExecutionRpc(trace)
    with Session(home) as s:
        check(s.wallet == wallet, 'explicit-wallet-mismatch')
        check(type(cycle) is bool, 'explicit-cycle-required')
        jhome = s.home / cycle_binding.CYCLE if cycle else s.home
        binding = cycle_binding.load(jhome, wallet, expected_pool) if cycle else None
        child = jhome / journal_name(reverse)
        if os.path.lexists(child):
            return finish_report(jhome, wallet, trace, 'existing-journal-use-recover-no-retry', reverse=reverse)
        check(type(replace_unsigned) is bool and (not replace_unsigned or cycle and not reverse), 'replacement-cycle-entry-required')
        replacement_hash = None
        if cycle:
            import unsigned_replacement as replacement
            if replacement.exists(jhome):
                check(reverse or replace_unsigned, 'explicit-unsigned-replacement-required')
                replacement_hash = replacement.digest(replacement.ready(jhome)[0])
            else:
                check(not replace_unsigned, 'replacement-not-prepared')
        check(not swap.stop(s.home), 'stop-requested')
        scope, setup = bridge.source_scope(s, expected_pool)
        if reverse:
            # Legacy entries cannot acquire a retroactive pretrade approval.
            finish_report(jhome, wallet)
            with spend_guard.Guard(jhome) as guard:
                entry_guard = guard.read()[0]
                check(entry_guard and not entry_guard['quarantined'] and entry_guard['legs'].get('entry', {}).get('receipt'), 'spending-prospective-entry-required')
            scope, prior, entry_receipt = reverse_scope(jhome, wallet)
            check(scope['accounts']['pool'] == expected_pool, 'explicit-pool-mismatch')
            verify_forward_on_chain(rpc, jhome, wallet, entry_receipt)
        else:
            prior = old_simulation(s.home, scope)
            prior_absent_and_expired(rpc, prior)
        # Once the execution directory exists it is never reused.
        check(not swap.stop(s.home), 'stop-requested')
        child.mkdir(mode=0o700); sync_directory(jhome)
        phase = 'fresh-packet'
        try:
            built = build(scope, opener=trace); packet = built['packet']
            check(packet['policy']['blockhash'] != prior['blockhash'], 'fresh-blockhash-required')
            v = swap.policy_check(scope, packet, wallet, now())
            plan = dict(format='swap-signing-plan-1', scope=scope, packet=packet, recordedAtMs=now())
            if binding is not None: plan['cycleBinding'] = binding
            if replacement_hash is not None: plan['unsignedReplacementSha256'] = replacement_hash
            write_new(child / 'plan.json', plan)
            write_new(child / 'execution.json', dict(format=REVERSE_VERSION if reverse else VERSION, planSha256=pool.digest(plan), setupEvidence=setup, spendingGuardVersion=spend_guard.VERSION,
                      **({'priorExecution': prior} if reverse else {'priorSimulation': prior}), lastValidBlockHeight=built['lastValidBlockHeight'],
                      contextSlot=built['evidence']['blockhash']['result']['context']['slot']))
            phase = 'preflight'
            capture = swap.collect(packet=packet, opener=trace)
            check(capture.get('packet') == packet, 'preflight-packet-changed')
            write_new(child / 'preflight.json', capture)
            reviewed = swap.audit(capture, now_ms=now())
            check(reviewed['state'] == 'preflight-evidence-consistent', 'fresh-preflight-required')
            if binding is not None and not reverse:
                cycle_binding.continuity(capture, binding)
            if reverse:
                phase = 'entry-to-exit-continuity'
                continuity(capture, entry_receipt)
            check(not swap.stop(s.home), 'stop-requested')
            phase = 'spending-reservation'
            side = 'exit' if reverse else 'entry'
            with spend_guard.Guard(jhome, create=not reverse) as guard:
                guard.reserve(side, plan, capture, **({'replace_unsigned': True} if replace_unsigned else {}))
            write_new(child / spend_guard.MARKER, dict(format=spend_guard.VERSION, side=side, planSha256=pool.digest(plan)))
            write_new(child / 'signing-request.json', dict(format='restricted-swap-request-1',
                planSha256=pool.digest(plan), preflightSha256=pool.digest(capture), expiresAtMs=reviewed['validUntilExclusiveMs'],
                computeUnits=v['computeUnits'], microLamportsPerCU=v['microLamportsPerCU'],
                messageBase64=base64.b64encode(decode_wire(packet['unsignedTransactionBase64'])[1]).decode()))
            phase = 'signing'
            if reverse:
                swap.invoke_signer(s.home, reverse=True, **({'cycle': True} if cycle else {}))
            else:
                swap.invoke_signer(s.home, execution=True, **({'cycle': True} if cycle else {}))
            plan, wire, signed, evidence = bound(child, wallet)
            with spend_guard.Guard(jhome) as guard:
                guard.bind(side, plan, signed)
            check(not swap.stop(s.home), 'stop-requested')
            check(swap.audit(capture, now_ms=now())['state'] == 'preflight-evidence-consistent', 'preflight-expired')
            phase = 'simulation'
            a = scope['accounts']; simrpc = swap.SimulationRpc(trace)
            write_new(child / 'simulation-request.json', dict(signature=signed['signatures'][0]))
            item = simrpc.request('simulateTransaction', [wire, dict(encoding='base64', commitment='finalized', sigVerify=True,
                replaceRecentBlockhash=False, minContextSlot=reviewed['snapshotSlot'],
                accounts=dict(encoding='base64', addresses=[a[n] for n in ('wallet', *TOKEN_ROLES)]))])
            write_new(child / 'simulation-response.json', item)
            genesis(simrpc)
            simulated = swap.simulation_review(packet, capture, wire, item)
            write_new(child / 'simulation-review.json', simulated)
            phase = 'presend-preflight'
            fresh = swap.collect(packet=packet, opener=trace)
            write_new(child / 'presend-preflight.json', fresh)
            current = swap.audit(fresh, now_ms=now())
            check(current['state'] == 'preflight-evidence-consistent' and current['snapshotSlot'] >= simulated['simulationSlot'], 'presend-freshness')
            check(fresh['packet'] == packet and fresh['accountKeys'] == capture['accountKeys']
                  and fresh['evidence']['accounts']['result']['value'] == capture['evidence']['accounts']['result']['value'], 'presend-account-drift')
            if binding is not None and not reverse:
                cycle_binding.continuity(fresh, binding)
            if reverse:
                continuity(fresh, entry_receipt)
            genesis(rpc)
            height = received(rpc.request('getBlockHeight', [dict(commitment='finalized', minContextSlot=current['snapshotSlot'])]))
            check(integer(height) and height + 10 < evidence['lastValidBlockHeight'], 'blockhash-near-expiry')
            check(signature_status(rpc, signed['signatures'][0], evidence['contextSlot']) is None, 'signature-already-observed')
            # Validate again at the durable boundary; the boundary is never cleared, even if transport fails.
            swap.policy_check(scope, packet, wallet, now())
            check(swap.audit(fresh, now_ms=now())['state'] == 'preflight-evidence-consistent', 'presend-expired')
            check(not swap.stop(s.home), 'stop-requested')
            phase = 'submission'
            with spend_guard.Guard(jhome) as guard:
                guard.boundary(side, plan, signed)
            write_new(child / 'submission-boundary.json', dict(signature=signed['signatures'][0], wireSha256=signed['wireSha256'], atMs=now()))
            # Recheck after fsync. A stop/expiry here intentionally consumes the only boundary without sending.
            check(not swap.stop(s.home) and now() < packet['policy']['expiresAtMs'] and now() < current['validUntilExclusiveMs'], 'boundary-stopped-or-expired')
            sent = rpc.request('sendTransaction', [wire, dict(encoding='base64', skipPreflight=False, preflightCommitment='finalized', maxRetries=0, minContextSlot=current['snapshotSlot'])])
            ack = sent.get('state') == 'received' and sent.get('result') == signed['signatures'][0]
            write_new(child / 'send-observation.json', dict(expectedSignatureAcknowledged=ack, responseState=sent.get('state')))
            # Even an unexpected acknowledgement is not a second signature to follow or a reason to resend.
            observe(child, wallet, rpc, sleeper=sleeper)
        except (ValueError, KeyError, TypeError, IndexError, OSError, swap.subprocess.SubprocessError):
            write_new(child / 'failure.json', dict(phase=phase, reason='execution-validation-or-transport-incomplete', atMs=now()))
        r = finish_report(jhome, wallet, trace, reverse=reverse)
        r['signaturesCreatedThisRun'] = None if r['signatureOutcomeUnknown'] else int(os.path.lexists(child / 'signed.json'))
        return r


@cycle_binding.operation
def recover(home, wallet, *, opener=None, sleeper=time.sleep, reverse=False, cycle=False, expected_pool=None):
    check(type(cycle) is bool, 'explicit-cycle-required')
    trace = Trace(opener, recovery=True)
    with Session(home) as s:
        check(s.wallet == wallet, 'explicit-wallet-mismatch')
        jhome = s.home / cycle_binding.CYCLE if cycle else s.home
        if cycle: cycle_binding.load(jhome, wallet, expected_pool)
        r = finish_report(jhome, wallet, reverse=reverse)
        if r['state'] in TERMINAL or not r['submissionBoundaryRecorded']:
            return r
        child = jhome / journal_name(reverse)
        check(len(observations(child)) <= 29, 'recovery-observation-cap')
        observe(child, wallet, RecoveryRpc(trace), sleeper=sleeper)
        return finish_report(jhome, wallet, trace, reverse=reverse)


@cycle_binding.operation
def status(home, wallet, *, reverse=False, cycle=False, expected_pool=None):
    check(type(cycle) is bool, 'explicit-cycle-required')
    with Session(home) as s:
        check(s.wallet == wallet, 'explicit-wallet-mismatch')
        jhome = s.home / cycle_binding.CYCLE if cycle else s.home
        if cycle: cycle_binding.load(jhome, wallet, expected_pool)
        return report(jhome, wallet, reverse=reverse)


@cycle_binding.operation
def execute(home, wallet, expected_pool, *, opener=None, sleeper=time.sleep, cycle=False, replace_unsigned=False):
    return _execute(home, wallet, expected_pool, opener=opener, sleeper=sleeper, cycle=cycle,replace_unsigned=replace_unsigned)


@cycle_binding.operation
def execute_reverse(home, wallet, expected_pool, *, opener=None, sleeper=time.sleep, cycle=False):
    return _execute(home, wallet, expected_pool, reverse=True, opener=opener, sleeper=sleeper, cycle=cycle)


def inspect_reverse(home, wallet, expected_pool):
    with Session(home) as s:
        check(s.wallet == wallet, 'explicit-wallet-mismatch')
        bridge.source_scope(s, expected_pool)
        scope, proof, _ = reverse_scope(s.home, wallet)
        check(scope['accounts']['pool'] == expected_pool, 'explicit-pool-mismatch')
        r = report(s.home, wallet, reverse=True)
        r.update(scope=scope, priorExecution=proof)
        if r['state'] == 'not-started':
            r['state'] = 'stopped' if swap.stop(s.home) else 'reverse-scope-ready'
        return r
