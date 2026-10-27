"""One read-only, locally priced controlled-devnet observation. No sender path."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import urllib.request

import reservation_view as view
from core import check
from journal import read_only_journals

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'swap-preflight'))
import preflight
import preflight_capture
from preflight_diagnostics import describe as capture_diagnostics
from fresh_packet import build, scope_check
from cpmm_quote import derive
from recorded_capture import NoRedirect, ENDPOINTS

VERSION = 'fresh-controlled-quote-observation-1'
METHODS = {'getGenesisHash','getMultipleAccounts','getBlockTime','getLatestBlockhash',
           'isBlockhashValid','getFeeForMessage'}
DIAGNOSTICS = {'closed-controlled-cycles-required','initial-preflight-rejected',
    'fresh-packet-scope','fresh-packet-capture-mismatch','final-preflight-rejected',
    'pool-price-inputs-changed','ledger-changed-during-quote','local-token-reservation-unknown',
    'local-binding-rejected','stop-marker-present','quote-read-stale-or-future',
    'quote-pool-rejected','quote-pool-ineligible','quote-mint-authority','quote-pool-scope',
    'quote-input-mint','quote-pool-roles','native-route-unsupported','input-vault-overflow',
    'input-consumed-by-fee','empty-or-invalid-output','combined-fee-rate',
    'zero-input-fee-denominator','observation-expired-before-completion','observation-time-budget',
    'simulation-evidence-unavailable','simulation-clock-regression'}


class ReadTransport:
    """Shared request budget across three collectors. Never retry or redirect."""
    METHODS = METHODS
    REQUEST_CAP = 18
    def __init__(self, opener=None, monotonic=time.monotonic):
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.calls = []
        self.monotonic = monotonic
        self.started = monotonic()

    def open(self, request, timeout):
        remaining = 30 - (self.monotonic()-self.started)
        check(0 < remaining <= 30 and len(self.calls) < self.REQUEST_CAP, 'read-budget')
        body = json.loads(request.data)
        check(request.full_url == ENDPOINTS['devnet'] and request.get_method() == 'POST'
              and body['method'] in self.METHODS, 'readonly-devnet-request')
        self.calls.append(body['method'])
        return self.opener.open(request, timeout=min(timeout, remaining))


def combine(first, built, second, scope, *, stamp, review=preflight.audit):
    """Pure integration; synthetic tests may inject their fixed fixture baseline."""
    check(review(first, now_ms=stamp)['state'] == 'pinned-pool-snapshot', 'initial-preflight-rejected')
    first_state, _ = preflight.split_capture(first)
    priced = derive(first_state, scope, slippage_bps=100, now_ms=stamp)
    packet = built['packet']
    expected = deepcopy(scope); expected['minimumAmountOut'] = priced['quote']['minimumOutAmount']
    check({k:packet['policy'][k] for k in expected if k != 'format'} ==
          {k:v for k,v in expected.items() if k != 'format'}, 'fresh-packet-scope')
    check(second['packet'] == packet, 'fresh-packet-capture-mismatch')
    checked = review(second, now_ms=stamp)
    check(checked['state'] == 'preflight-evidence-consistent', 'final-preflight-rejected')
    second_state, _ = preflight.split_capture(second)
    repriced = derive(second_state, expected, slippage_bps=100, now_ms=stamp)
    check(priced['economicInputsSha256'] == repriced['economicInputsSha256'] and
          priced['arithmetic'] == repriced['arithmetic'], 'pool-price-inputs-changed')
    bundle = dict(format=view.quote_binding.VERSION, quote=priced['quote'], capture=second_state,
                  reservations=None, maxSlippageBps=100)
    return priced, checked, bundle


@view.cycles.binding.operation
def observe(home, wallet, pool, *, opener=None, clock=view.now, monotonic=time.monotonic,
            simulate=False):
    check(type(simulate) is bool, 'simulation-mode')
    result = dict(format=VERSION, state='unavailable', stage='local-scope', reasons=[],
        network='devnet', networkRequests=0, requestMethods=[], quote=None, preflight=None,
        reservations=None, binding=None, signaturesCreated=0, transactionsSent=0,
        privateKeyAccessed=False, sourceStateChanged=False, databaseConnectionsReadOnly=True,
        executionApproved=False, nextCycleAuthorized=False, mainnetSupported=False,
        simulationVerified=False, sourceEquivalenceVerified=False, walletWideReservationsKnown=False,
        limitations=[
            'Locally calculated standard-SPL direct-pool quote, not an aggregator quote or fill.',
            'The pinned deployed bytes are checked; equivalence to the formula source is not proved.',
            'Only existing controlled-cycle reservations are known; external wallet activity is not locked.',
            'One observation, at most 18 public devnet reads, no retries, 30-second request-start budget.',
            'Original quote freshness remains 10 seconds, including the final local ledger read.',
            'No simulation, private key read, signed transaction, new cycle or frozen-study change.'])
    transport = None
    if simulate:
        import unsigned_simulation as sim
        result.update(format=sim.VERSION, simulation=None)
        result['limitations'][-3:] = [
            'At most 20 public devnet requests including one unsigned simulation; no retries.',
            'Original quote freshness remains 10 seconds through simulation and local ledger replay.',
            'Simulation is not a fill, signature verification, new cycle or execution approval.',
            'Matching sampled effects do not prove deployed-source equivalence for all inputs.']
    try:
        with view.cycles.c.source_lock(home, wallet) as root, read_only_journals():
            before = view.read_locked(root, wallet, pool, clock)
            check(before['phase'] == 'closed', 'closed-controlled-cycles-required')
            scope, _ = view.cycles.c.submit.bridge.source_scope(SimpleNamespace(home=root, wallet=wallet), pool)
            scope_check(scope)
            transport = sim.Transport(opener, monotonic) if simulate else ReadTransport(opener, monotonic)
            result['stage'] = 'pool-quote'
            first = preflight_capture.collect(pool=pool, opener=transport, now=clock, monotonic=monotonic)
            result['captureDiagnostics'] = dict(poolQuote=capture_diagnostics(first,baseline=preflight.BASELINE))
            initial = preflight.audit(first, now_ms=clock())
            result['preflight'] = initial
            check(initial['state'] == 'pinned-pool-snapshot', 'initial-preflight-rejected')
            raw, _ = preflight.split_capture(first)
            price = derive(raw, scope, slippage_bps=100, now_ms=clock())
            result['quote'] = price
            fresh_scope = deepcopy(scope); fresh_scope['minimumAmountOut'] = price['quote']['minimumOutAmount']
            result['stage'] = 'unsigned-packet'
            built = build(fresh_scope, opener=transport, now=clock)
            check(not view.cycles.c.submit.swap.stop(root), 'stop-marker-present')
            result['stage'] = 'account-preflight'
            second = preflight_capture.collect(packet=built['packet'], opener=transport, now=clock, monotonic=monotonic)
            result['captureDiagnostics']['accountPreflight'] = capture_diagnostics(second,baseline=preflight.BASELINE)
            result['stage'] = 'local-binding'
            current = view.read_locked(root, wallet, pool, clock)
            check((before['ledgerHeadSha256'], before['cycleBindingSha256']) ==
                  (current['ledgerHeadSha256'], current['cycleBindingSha256']), 'ledger-changed-during-quote')
            stamp = clock()
            price, checked, bundle = combine(first, built, second, scope, stamp=stamp)
            q = price['quote']
            selected = [a for a in current['tokenAccounts'] if a['account'] == q['source'] and a['mint'] == q['inputMint']]
            check(len(selected) == 1 and selected[0]['heldAtomic'] is not None, 'local-token-reservation-unknown')
            bundle['reservations'] = dict(wallet=wallet, source=q['source'], inputMint=q['inputMint'],
                otherTokenAtomic=selected[0]['heldAtomic'], otherNativeLamports=current['nativeHeldLamports'],
                asOfMs=current['observedAtMs'])
            binding = view.quote_binding._review(bundle, now_ms=stamp, current_local_reservations=True)
            result.update(quote=price, preflight=checked, reservations=current, binding=binding)
            check(binding['state'] == 'declared-quote-state-consistent', 'local-binding-rejected')
            check(not view.cycles.c.submit.swap.stop(root), 'stop-marker-present')
            if simulate:
                result['stage'] = 'unsigned-simulation'
                deadline = min(checked['validUntilExclusiveMs'], binding['binding']['validUntilExclusiveMs'])
                simulation = sim.collect(built['packet'], second, price, transport=transport,
                                         clock=clock, deadline=deadline)
                result['simulation'] = simulation
                check(simulation['state'] == 'unsigned-effects-match-quote', 'simulation-evidence-unavailable')
                result['stage'] = 'post-simulation-reservations'
                final = view.read_locked(root, wallet, pool, clock)
                check((current['ledgerHeadSha256'], current['cycleBindingSha256']) ==
                      (final['ledgerHeadSha256'], final['cycleBindingSha256']) and final['phase'] == 'closed',
                      'ledger-changed-during-quote')
                result['reservationsAfterSimulation'] = final
                check(not view.cycles.c.submit.swap.stop(root), 'stop-marker-present')
            finished = clock()
            if simulate:
                check(simulation['finishedAtMs'] <= final['readStartedAtMs'] <= final['observedAtMs'] <= finished,
                      'simulation-clock-regression')
            check(stamp <= finished < min(checked['validUntilExclusiveMs'],
                  binding['binding']['validUntilExclusiveMs']), 'observation-expired-before-completion')
            check(0 <= monotonic()-transport.started < 30, 'observation-time-budget')
            result.update(state='unsigned-quote-simulation-consistent' if simulate else
                          'fresh-quote-observation-consistent', stage='complete', reviewedAtMs=finished,
                          simulationVerified=simulate)
    except (ValueError, KeyError, TypeError, IndexError, OSError, view.sqlite3.Error) as exc:
        result['reasons'] = ['fresh-observation-unavailable-at-'+result['stage']]
        result['diagnosticCode'] = str(exc) if str(exc) in DIAGNOSTICS else 'unclassified-local-or-rpc-evidence'
    finally:
        if transport is not None:
            result.update(networkRequests=len(transport.calls), requestMethods=transport.calls)
    return result
