"""Durable reservations for the fixed controlled devnet sender, one round trip only.

Inputs are internally audited plans and replayed exact receipts. This is a local
trusted-owner control, not a wallet-wide or mainnet spending authority.
"""
import copy
import cycle_binding
import hashlib
import os
from pathlib import Path

from controlled_swap import swap, pool
from core import check, directory, private_file, loads
from journal import Journal, encoded

VERSION = 'controlled-spending-guard-1'
NAME = 'controlled.spending.sqlite'
MARKER = 'spending-reservation.json'
MAX_EVENTS = 32
MAX_STATE_BYTES = 32768
POLICY = dict(network='devnet', maximumPrincipalAtomic='1000', maximumLegFeeLamports='10000',
              maximumRoundTripFeeLamports='20000', maximumEntries=1, maximumExits=1)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


class Guard:
    def __init__(self, home, *, create=False, clock=None):
        self.cycle = cycle_binding.load(home) if cycle_binding.is_cycle(home) else None
        path = directory(home) / NAME
        existed = os.path.lexists(path)
        if existed:
            private_file(path, 2 * 1024 * 1024)
        self.j = Journal(path, create=create, clock=clock)
        try:
            if not existed:
                with self.j.transaction():
                    self.j.db.execute('CREATE TABLE spending_events (seq INTEGER PRIMARY KEY, at_ms INTEGER NOT NULL, '
                                      'snapshot TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL)')
            check(self.j.db.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='spending_events'").fetchone()[0] == 1,
                  'spending-ledger-schema')
            check(self.j.db.execute('SELECT count(*) FROM intents').fetchone()[0] == 0
                  and self.j.db.execute('SELECT count(*) FROM events').fetchone()[0] == 0, 'mixed-spending-ledger')
            self.read()
        except BaseException:
            self.j.close()
            raise

    def __enter__(self): return self
    def __exit__(self, *_): self.j.close()

    def read(self):
        rows = self.j.db.execute('SELECT * FROM spending_events ORDER BY seq LIMIT ?', (MAX_EVENTS + 1,)).fetchall()
        check(len(rows) <= MAX_EVENTS, 'spending-event-cap')
        state = None; previous = ''; at = 0
        for seq, row in enumerate(rows, 1):
            check(row['seq'] == seq and type(row['at_ms']) is int and row['at_ms'] >= at
                  and len(row['snapshot'].encode()) <= MAX_STATE_BYTES, 'spending-event-order')
            state = loads(row['snapshot'])
            check(state.get('format') == VERSION and state.get('policy') == POLICY and encoded(state) == row['snapshot'],
                  'spending-state-format')
            check(state.get('cycleBinding') == self.cycle, 'spending-cycle-binding')
            h = digest(dict(seq=seq, atMs=row['at_ms'], state=state, previousHash=previous))
            check(row['previous_hash'] == previous and row['event_hash'] == h, 'spending-event-integrity')
            at = row['at_ms']; previous = h
        return state, len(rows), previous, at

    def change(self, fn):
        with self.j.transaction():
            old, count, previous, stamp = self.read()
            now = self.j.now()
            check(now >= stamp, 'spending-clock-regressed')
            state = fn(copy.deepcopy(old), now)
            if state != old:
                check(count < MAX_EVENTS and len(encoded(state).encode()) <= MAX_STATE_BYTES, 'spending-event-cap')
                h = digest(dict(seq=count+1, atMs=now, state=state, previousHash=previous))
                self.j.db.execute('INSERT INTO spending_events VALUES (?,?,?,?,?)',
                                  (count+1, now, encoded(state), previous, h))
            return state

    def authorize_unsigned_replacement(self, manifest):
        import unsigned_replacement as replacement
        check(self.cycle is not None, 'replacement-cycle-required')
        old,count,head,_ = self.read()
        def apply(state, now):
            check(state and not state['quarantined'] and set(state['legs']) == {'entry'}
                  and state['legs']['entry'] == manifest['oldEntry'], 'replacement-initial-reservation-required')
            leg=state['legs']['entry']
            check(leg['signed'] is None and leg['boundaryAtMs'] is None and leg['receipt'] is None,'replacement-old-entry-not-unsigned')
            authorization=state.get('unsignedReplacement')
            if authorization:
                check(authorization['manifestSha256'] == replacement.digest(manifest)
                      and authorization['oldEntry'] == leg and authorization['newPlanSha256'] is None,'replacement-already-used')
                return state
            check(count == manifest['oldLedgerCount'] == 1 and head == manifest['oldLedgerHash'],'replacement-ledger-head-changed')
            state['unsignedReplacement']=dict(format=replacement.VERSION,manifestSha256=replacement.digest(manifest),
                oldEntry=copy.deepcopy(leg),authorizedAtMs=now,newPlanSha256=None)
            return state
        return self.change(apply)

    def reserve(self, side, plan, capture, *, replace_unsigned=False):
        check(side in ('entry', 'exit'), 'spending-side')
        replacement_manifest = None
        if replace_unsigned:
            import unsigned_replacement as replacement
            check(side == 'entry' and self.cycle is not None, 'replacement-cycle-entry-required')
            replacement_manifest, archived = replacement.ready(self.j.path.parent)
            check(plan.get('unsignedReplacementSha256') == replacement.digest(replacement_manifest)
                  and plan['packet']['policy']['blockhash'] != archived['plan.json']['packet']['policy']['blockhash'],
                  'replacement-fresh-plan-required')
        check(plan.get('cycleBinding') == self.cycle, 'spending-cycle-plan')
        if self.cycle:
            check(int(self.cycle['historicalEntryAtomic']) + 1000 <= 2000
                  and int(self.cycle['historicalSwapFeeLamports']) + 20000 <= 40000, 'spending-cumulative-cap')
            if side == 'entry': cycle_binding.continuity(capture, self.cycle)
        scope = plan['scope']; a = scope['accounts']; packet = plan['packet']
        # Repeat current freshness and full policy validation at the reservation boundary.
        def apply(state, now):
            check(scope['network'] == 'devnet' and scope['maxTotalFeeLamports'] == '10000', 'spending-fixed-policy')
            swap.policy_check(scope, packet, a['wallet'], now)
            checked = swap.audit(capture, now_ms=now)
            check(capture['packet'] == packet and checked['state'] == 'preflight-evidence-consistent', 'spending-preflight')
            rows = dict(zip(capture['accountKeys'], capture['evidence']['accounts']['result']['value']))
            source = swap.token(rows[a['source']], a['inputMint'], a['wallet'])
            destination = swap.token(rows[a['destination']], a['outputMint'], a['wallet'])
            contract = dict(planSha256=digest(plan), scopeSha256=digest(scope), preflightSha256=digest(capture),
                            accounts=a, inputAtomic=scope['amountIn'], minimumOutputAtomic=scope['minimumAmountOut'],
                            feeLamports=packet['feeAssertion']['lamports'],
                            nativeBeforeLamports=str(rows[a['wallet']]['lamports']),
                            sourceBeforeAtomic=source['amount'], destinationBeforeAtomic=destination['amount'],
                            snapshotSlot=checked['snapshotSlot'], expiresAtMs=packet['policy']['expiresAtMs'])
            check(0 < int(contract['feeLamports']) <= 10000, 'spending-leg-fee-cap')
            if state is None:
                check(side == 'entry' and scope['amountIn'] == '1000' and scope['minimumAmountOut'] == '990', 'spending-entry-required')
                state = dict(format=VERSION, policy=copy.deepcopy(POLICY), wallet=a['wallet'], pool=a['pool'],
                             quarantined=False, quarantineReason=None, legs={})
                if self.cycle: state['cycleBinding'] = copy.deepcopy(self.cycle)
            check(not state['quarantined'] and state['wallet'] == a['wallet'] and state['pool'] == a['pool'], 'spending-identity-or-quarantine')
            if replacement_manifest:
                authorization=state.get('unsignedReplacement')
                check(set(state['legs']) == {'entry'} and state['legs']['entry'] == replacement_manifest['oldEntry']
                      and authorization and authorization['newPlanSha256'] is None
                      and authorization['manifestSha256'] == digest(replacement_manifest)
                      and authorization['oldEntry'] == replacement_manifest['oldEntry'], 'replacement-reservation-not-ready')
                authorization['newPlanSha256']=digest(plan)
                authorization['replacedAtMs']=now
            else:
                check(side not in state['legs'], 'spending-attempt-already-reserved')
            confirmed = sum(int(x['receipt']['feeLamports']) for x in state['legs'].values() if x['receipt'])
            if side == 'entry':
                check((not state['legs'] or replacement_manifest is not None) and int(source['amount']) >= 1000, 'spending-principal-cap')
                reserve_fee = 20000  # Reserve one maximum-fee exit before entry signing.
            else:
                entry = state['legs'].get('entry')
                check(entry and entry['receipt'] and entry['receipt']['state'] == 'finalized-success', 'spending-finalized-entry-required')
                e = entry['receipt']; ea = entry['contract']['accounts']
                check(scope['amountIn'] == e['outputAtomic'] and 990 <= int(scope['amountIn']) <= 1000, 'spending-full-exit-required')
                for left, right in (('source','destination'),('destination','source'),('inputMint','outputMint'),
                                    ('outputMint','inputMint'),('inputVault','outputVault'),('outputVault','inputVault')):
                    check(a[left] == ea[right], 'spending-reverse-identity')
                check(contract['nativeBeforeLamports'] == e['walletAfterLamports']
                      and source['amount'] == e['tokenEffects']['destination']['afterAtomic']
                      and destination['amount'] == e['tokenEffects']['source']['afterAtomic']
                      and contract['snapshotSlot'] >= e['slot'], 'spending-exit-continuity')
                reserve_fee = 10000
            check(int(contract['nativeBeforeLamports']) >= reserve_fee and confirmed + reserve_fee <= 20000, 'spending-round-trip-fee-cap')
            state['legs'][side] = dict(contract=contract, reservedAtMs=now, signed=None, boundaryAtMs=None, receipt=None)
            return state
        return self.change(apply)

    def bind(self, side, plan, signed):
        check(plan.get('cycleBinding') == self.cycle, 'spending-cycle-plan')
        def apply(state, now):
            check(state and not state['quarantined'] and side in state['legs'], 'spending-reservation-required')
            leg = state['legs'][side]
            check(leg['contract']['planSha256'] == digest(plan), 'spending-plan-binding')
            identity = dict(signature=signed['signatures'][0], wireSha256=signed['wireSha256'], messageSha256=signed['wireMessageSha256'])
            if leg['signed']:
                check(leg['signed'] == identity, 'spending-signed-conflict')
            else:
                check(leg['boundaryAtMs'] is None and leg['receipt'] is None, 'spending-bind-state')
                leg['signed'] = identity
            return state
        return self.change(apply)

    def boundary(self, side, plan, signed):
        # Binding is a separate durable write; a crash between writes retains the reservation.
        self.bind(side, plan, signed)
        def apply(state, now):
            leg = state['legs'][side]
            check(not state['quarantined'] and leg['boundaryAtMs'] is None and leg['receipt'] is None, 'spending-boundary-consumed')
            check(now < leg['contract']['expiresAtMs'], 'spending-intent-expired')
            leg['boundaryAtMs'] = now
            return state
        return self.change(apply)

    def reconcile(self, side, result):
        """Called only after sender replays its privately stored exact signed receipt."""
        def apply(state, now):
            check(state and side in state['legs'], 'spending-reservation-required')
            leg = state['legs'][side]
            if result['state'] == 'quarantined':
                state.update(quarantined=True, quarantineReason='execution-quarantined')
                return state
            r = result.get('observation', {}).get('receipt')
            if result['state'] not in ('finalized-success','finalized-failure'):
                return state  # Expiry and missing receipts never release money.
            check(r and leg['signed'] and leg['boundaryAtMs'] is not None and result['submissionBoundaryRecorded'], 'spending-final-boundary')
            c = leg['contract']
            consistent = (all(r[k] == v for k,v in leg['signed'].items())
                          and r['feeLamports'] == c['feeLamports'] and int(r['feeLamports']) <= 10000
                          and r['walletBeforeLamports'] == c['nativeBeforeLamports']
                          and int(r['walletBeforeLamports']) - int(r['walletAfterLamports']) == int(r['feeLamports'])
                          and r['slot'] >= c['snapshotSlot']
                          and r['tokenEffects']['source']['beforeAtomic'] == c['sourceBeforeAtomic']
                          and r['tokenEffects']['destination']['beforeAtomic'] == c['destinationBeforeAtomic'])
            if not consistent or (leg['receipt'] is not None and leg['receipt'] != r):
                state.update(quarantined=True, quarantineReason='receipt-conflicts-with-reservation')
                return state
            leg['receipt'] = copy.deepcopy(r)
            check(sum(int(x['receipt']['feeLamports']) for x in state['legs'].values() if x['receipt']) <= 20000, 'spending-confirmed-fee-cap')
            return state
        return self.change(apply)

    def summary(self):
        with self.j.transaction():
            state, count, _, _ = self.read()
        if state is None:
            return dict(format=VERSION, state='empty-incomplete', eventCount=count, pretradeBudgetEnforced=False)
        legs = state['legs']; e = legs.get('entry'); x = legs.get('exit')
        er = e['receipt'] if e else None; xr = x['receipt'] if x else None
        fees = sum(int(v['receipt']['feeLamports']) for v in legs.values() if v['receipt'])
        held_principal = 1000 if e and er is None else 0
        residual = int(er['outputAtomic']) if er and er['state'] == 'finalized-success' else 0
        if xr and xr['state'] == 'finalized-success': residual = 0
        if er is None:
            stage = 'entry-unresolved'; reserve_fee = 20000
        elif er['state'] == 'finalized-failure':
            stage = 'entry-failed'; reserve_fee = 0
        elif xr:
            stage = 'closed' if xr['state'] == 'finalized-success' else 'exit-failed-position-open'; reserve_fee = 0
        else:
            stage = 'exit-unresolved' if x else 'open'; reserve_fee = 10000
        result = dict(format=VERSION, state='quarantined' if state['quarantined'] else stage,
                    policy=state['policy'], eventCount=count, pretradeBudgetEnforced=True,
                    wallet=state['wallet'], pool=state['pool'], confirmedFeeLamports=str(fees),
                    heldEntryPrincipalAtomic=str(held_principal), reservedFeeLamports=str(reserve_fee),
                    lastReconciledAcquiredAtomic=str(residual), remainingFeeBudgetLamports=str(20000-fees),
                    accountingUsable=not state['quarantined'], quarantineReason=state['quarantineReason'],
                    legs={k:dict(reservedAtMs=v['reservedAtMs'], signedIdentityBound=v['signed'] is not None,
                                 boundaryAtMs=v['boundaryAtMs'], finalized=v['receipt'] is not None,
                                 planSha256=v['contract']['planSha256']) for k,v in legs.items()},
                    mainnetEnabled=False, automaticRetryAllowed=False, currentWalletBalancesKnown=False,
                    enforcementScope='This controlled devnet sender and dedicated local journal only',
                    limitations=['Unknown outcomes keep reservations. Expiry is not proof of non-execution.',
                                 'One entry and one exit only; a failed exit retains exposure and has no automatic replacement.',
                                 'Atomic token amounts and native fees are different units; no USD budget or profit claim.',
                                 'Local files and process ownership are trusted; external wallet activity can bypass this guard.'])
        if self.cycle:
            result['cycleBinding'] = self.cycle
            result['cumulativeConfirmedFeeLamports'] = str(int(self.cycle['historicalSwapFeeLamports']) + fees)
            result['cumulativeConfirmedAndReservedFeeLamports'] = str(int(self.cycle['historicalSwapFeeLamports']) + fees + reserve_fee)
            result['cumulativeGrossEntryAllocatedAtomic'] = str(int(self.cycle['historicalEntryAtomic']) + 1000)
        if state.get('unsignedReplacement'):
            r=state['unsignedReplacement']
            result['unsignedReplacement']=dict(format=r['format'],manifestSha256=r['manifestSha256'],
                originalPlanSha256=r['oldEntry']['contract']['planSha256'],newPlanSha256=r['newPlanSha256'],
                authorizedAtMs=r['authorizedAtMs'],replacedAtMs=r.get('replacedAtMs'),originalReservationPreserved=True)
        return result


def status(home, child):
    marker = child / MARKER
    execution_path = child / 'execution.json'
    execution = loads(private_file(execution_path, 32768)) if os.path.lexists(execution_path) else {}
    version = execution.get('spendingGuardVersion')
    check(version in (None, VERSION), 'spending-version')
    side = 'exit' if child.name == 'swap-reverse-v1' else 'entry'
    marked = os.path.lexists(marker)
    if not marked:
        # A fresh replacement can fail before transferring the existing reservation.
        # Keep that held budget visible even if no fresh packet was completed.
        if cycle_binding.is_cycle(home) and os.path.lexists(Path(home) / NAME):
            with Guard(home) as g:
                state=g.read()[0]
                replacement=state.get('unsignedReplacement') if state else None
                if side == 'entry' and replacement and replacement['newPlanSha256'] is None:
                    check(not any(os.path.lexists(child/n) for n in ('signing-attempt.json','signed.json','submission-boundary.json')),
                          'replacement-unreserved-signing-marker')
                    if execution:
                        plan=loads(private_file(child/'plan.json',32768))
                        check(digest(plan)==execution['planSha256'] and plan.get('unsignedReplacementSha256')==replacement['manifestSha256'],
                              'replacement-unreserved-plan-binding')
                    return dict(g.summary(),reservationMarkerPresent=False,replacementReservationTransferred=False)
        check(not version or not any(os.path.lexists(child / n) for n in ('signing-attempt.json', 'signed.json', 'submission-boundary.json')),
              'spending-required-marker-missing')
        if not version or not os.path.lexists(Path(home) / NAME):
            return dict(format=VERSION, state='not-recorded-for-this-attempt', pretradeBudgetEnforced=False)
        # A crash after reservation commit but before marker creation still holds money.
        with Guard(home) as g:
            state = g.read()[0]
            if state is None or side not in state['legs']:
                return dict(format=VERSION, state='not-reserved', pretradeBudgetEnforced=False, retainedBudget=g.summary())
            check(state['legs'][side]['contract']['planSha256'] == execution['planSha256'], 'spending-incomplete-reservation')
            return dict(g.summary(), reservationMarkerPresent=False)
    m = loads(private_file(marker, 4096))
    check(version == VERSION and m.get('format') == VERSION and m.get('side') == side
          and m.get('planSha256') == execution.get('planSha256'), 'spending-marker')
    with Guard(home) as g:
        state = g.read()[0]
        check(state and side in state['legs'] and m['planSha256'] == state['legs'][side]['contract']['planSha256'], 'spending-marker-binding')
        return dict(g.summary(), reservationMarkerPresent=True)
