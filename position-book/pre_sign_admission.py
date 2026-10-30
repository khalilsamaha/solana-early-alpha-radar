"""Durable pre-sign admission prototype. No signer, transport or live installation.

Raw evidence and reservation provenance belong to a trusted in-process caller.
The standalone CLI exposes only synthetic checks, never an evidence-import permit.
"""
from copy import deepcopy
import json
from pathlib import Path

import fresh_quote  # Establish the repository's existing validator import paths.
import cost_readiness
from simulation_baseline import BASELINE
from contract import atomic, digest, fields, uint
from core import check
from cpmm_quote import derive
from fresh_packet import scope_check
from swap_rehearsal import scope_for
from journal import Journal, encoded

VERSION = 'pre-sign-admission-1'
MAX_EVENTS = 8
MAX_EVIDENCE_BYTES = 12 * 1024 * 1024
FLAGS = dict(networkRequests=0, signaturesCreated=0, transactionsSent=0,
             executionApproved=False, signingApproved=False, liveSenderIntegrated=False,
             productionLedgerUpdated=False, walletWideReservationsKnown=False,
             roundTripFundingEstablished=False, automaticRetryAllowed=False,
             sourceReservationProvenanceVerified=False, signerInvocationAllowed=False)


def validate_policy(p):
    fields(p, {'format','scope','maximumExitAttempts','maximumExitFeeLamports',
               'maximumTotalFeeLamports'}, 'admission-policy-schema')
    check(p['format'] == VERSION+'-policy', 'admission-policy-format')
    scope_check(p['scope'])
    uint(p['maximumExitAttempts'], 3, 'admission-exit-attempts', minimum=1)
    exit_fee = atomic(p['maximumExitFeeLamports'], 'admission-exit-fee', positive=True)
    total = atomic(p['maximumTotalFeeLamports'], 'admission-total-fee', positive=True)
    check(exit_fee <= 10000 and total <= 40000, 'admission-fee-hard-cap')


def review(evidence, policy, now):
    """Recompute raw prices, message/deployment, balances, fees and simulation."""
    validate_policy(policy)
    uint(now, 2**53-1, 'admission-clock', minimum=1)
    check(len(encoded(evidence).encode()) <= MAX_EVIDENCE_BYTES, 'admission-evidence-cap')
    fields(evidence, {'costInputs','initialPool','scope','entryScope','completedAtMs'}, 'admission-evidence-schema')
    args = deepcopy(evidence['costInputs'])
    fields(args, {'packet','capture','price','simulation_item','reservations','baseline',
                  'simulation_started','simulation_received','simulation_finished','now_ms'}, 'admission-cost-schema')
    check(args['baseline'] == BASELINE, 'admission-pinned-baseline')
    check(type(evidence['completedAtMs']) is int and args['now_ms'] == evidence['completedAtMs']
          <= now, 'admission-completion-clock')
    scope = scope_for(args['packet']['policy'])
    check(scope == evidence['scope'] == policy['scope'], 'admission-scope')
    # The observer's reference scope can carry a placeholder minimum, but all
    # other roles, amounts and fee settings must be the exact admitted entry.
    scope_check(evidence['entryScope'])
    check({k:v for k,v in evidence['entryScope'].items() if k!='minimumAmountOut'} ==
          {k:v for k,v in scope.items() if k!='minimumAmountOut'}, 'admission-reference-scope')
    computed = derive(evidence['initialPool'], scope, slippage_bps=100, now_ms=now)
    check(computed == args['price'], 'admission-price')
    current, _ = fresh_quote.preflight.split_capture(args['capture'])
    repriced = derive(current, scope, slippage_bps=100, now_ms=now)
    check(computed['economicInputs'] == repriced['economicInputs'] and
          computed['arithmetic'] == repriced['arithmetic'], 'admission-pool-changed')
    args.update(now_ms=now, baseline=deepcopy(BASELINE))
    result = cost_readiness.assess(**args)
    check(result['state'] == 'single-leg-cost-evidence-consistent', 'admission-raw-evidence')
    c = result['calculation']
    fee = int(c['networkFeeCapLamports']) + policy['maximumExitAttempts']*int(policy['maximumExitFeeLamports'])
    check(fee <= int(policy['maximumTotalFeeLamports']), 'admission-total-budget')
    check(fee <= int(c['nativeSpendableLamports']), 'admission-native-budget')
    return dict(evidenceSha256=digest(evidence), policySha256=digest(policy),
                messageSha256=result['evidence']['messageSha256'],
                ledgerHeadSha256=result['evidence']['ledgerHeadSha256'],
                cycleBindingSha256=result['evidence']['cycleBindingSha256'],
                validUntilExclusiveMs=result['validUntilExclusiveMs'],
                reservedPrincipalAtomic=c['inputAtomic'], reservedFeeLamports=str(fee),
                maximumExitAttempts=policy['maximumExitAttempts'],
                entryFeeCapLamports=c['networkFeeCapLamports'],
                exitFeeCapLamports=policy['maximumExitFeeLamports'])


class Admission:
    """One immutable unsigned entry admission per separate private ledger.

No reset/release, signed binding, receipt application or production handoff yet.
A signing boundary marks uncertainty; it is not a callable signing capability.
"""
    def __init__(self, path, policy=None, clock=None):
        path = Path(path)
        check(path.name.endswith('.admission.sqlite'), 'separate-admission-file-required')
        existed = path.exists() or path.is_symlink()
        check(existed or policy is not None, 'admission-not-found')
        if policy is not None: validate_policy(policy)
        self.j = Journal(path, create=policy is not None, clock=clock)
        self.db = self.j.db
        try:
            if not existed:
                with self.j.transaction():
                    self.db.execute('CREATE TABLE admission_policy (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')
                    self.db.execute('CREATE TABLE admission_events (seq INTEGER PRIMARY KEY, at_ms INTEGER NOT NULL, value TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL)')
                    self.db.execute('INSERT INTO admission_policy VALUES (1,?)', (encoded(policy),))
            check(self.db.execute('SELECT COUNT(*) FROM intents').fetchone()[0] == 0 and
                  self.db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 0, 'mixed-admission-ledger')
            row = self.db.execute('SELECT value FROM admission_policy WHERE id=1').fetchone()
            check(row is not None, 'admission-policy-absent')
            self.policy = json.loads(row[0]); validate_policy(self.policy)
            check(policy is None or encoded(policy)==row[0], 'admission-immutable-policy')
            self.read()
        except BaseException:
            self.close(); raise

    def close(self): self.j.close()

    def read(self):
        rows = self.db.execute('SELECT * FROM admission_events ORDER BY seq LIMIT ?', (MAX_EVENTS+1,)).fetchall()
        check(len(rows) <= MAX_EVENTS, 'admission-event-cap')
        previous = ''; stamp = 0; state = None
        for seq, row in enumerate(rows, 1):
            value = json.loads(row['value'])
            check(row['seq']==seq and type(row['at_ms']) is int and row['at_ms']>=stamp and
                  len(row['value'])<=8192 and encoded(value)==row['value'], 'admission-event-shape')
            check(value['policySha256']==digest(self.policy) and value['state'] in
                  ('reserved','signing-unknown','stopped'), 'admission-state-policy')
            h = digest(dict(seq=seq, atMs=row['at_ms'], value=value, previousHash=previous))
            check(row['previous_hash']==previous and row['hash']==h, 'admission-event-integrity')
            previous=h; stamp=row['at_ms']; state=value
        return state, len(rows), previous, stamp

    def change(self, action, *, enforce_deadline=True):
        with self.j.transaction():
            state, count, previous, last = self.read()
            now = self.j.now(); check(now>=last, 'admission-clock-regressed')
            value = action(deepcopy(state), now)
            # Expensive raw validation cannot consume the deadline unnoticed.
            end = self.j.now(); check(end>=now, 'admission-clock-regressed')
            if enforce_deadline and value != state:
                check(end < value['validUntilExclusiveMs'], 'admission-deadline-elapsed')
            if value != state:
                check(count < MAX_EVENTS, 'admission-event-cap')
                h = digest(dict(seq=count+1, atMs=end, value=value, previousHash=previous))
                self.db.execute('INSERT INTO admission_events VALUES (?,?,?,?,?)',
                                (count+1,end,encoded(value),previous,h))
            return self.public(value, count+(value!=state))

    def reserve(self, evidence):
        # Own the raw object for the duration of both validation and hashing.
        check(len(encoded(evidence).encode()) <= MAX_EVIDENCE_BYTES, 'admission-evidence-cap')
        evidence = deepcopy(evidence)
        def apply(state, now):
            identity = digest(evidence)
            if state is not None:
                check(state.get('evidenceSha256')==identity, 'admission-already-reserved')
                return state  # idempotency does not refresh or authorize signing
            bound = review(evidence, self.policy, now)
            return dict(bound, state='reserved', reservedAtMs=now, signingBoundaryAtMs=None)
        return self.change(apply)

    def mark_signing_boundary(self, evidence):
        check(len(encoded(evidence).encode()) <= MAX_EVIDENCE_BYTES, 'admission-evidence-cap')
        evidence = deepcopy(evidence)
        def apply(state, now):
            check(state is not None and state['state']=='reserved', 'admission-signing-blocked')
            bound = review(evidence, self.policy, now)
            check(all(state[k]==v for k,v in bound.items()), 'admission-evidence-changed')
            state.update(state='signing-unknown', signingBoundaryAtMs=now)
            return state
        return self.change(apply)

    def stop(self):
        def stop(state, now):
            if state is None:
                return dict(state='stopped',policySha256=digest(self.policy),
                            reservedPrincipalAtomic='0',reservedFeeLamports='0')
            state['state']='stopped'; return state
        return self.change(stop, enforce_deadline=False)

    @staticmethod
    def public(state, count):
        return dict(format=VERSION, state='empty' if state is None else state['state'],
                    eventCount=count, reservation=None if state is None else deepcopy(state),
                    **FLAGS)

    def status(self):
        with self.j.transaction():
            state, count, _, last = self.read()
            check(self.j.now()>=last, 'admission-clock-regressed')
            return self.public(state,count)
