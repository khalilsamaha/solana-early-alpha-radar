# Controlled observation consolidation — October 27, 2026

This release combines the exact-message fee contract, raw-pool quote, locked
reservation reader, unsigned simulation, deployment-drift diagnostics, scoped
deployment observation and single-leg cost assessment into one reviewable batch.
PR #58 is the consolidation target. This is standalone development tooling;
there is no scanner deployment or new transaction lifecycle in this release.

## Host evidence accepted

| Checkpoint (UTC) | Evidence | Result |
|---|---|---|
| 04:28 | Fresh pool quote, exact message fee and closed reservations | 1,000 input, 998 output, minimum 989, fee 5,000 lamports; 4.904 seconds |
| 18:30 / 18:38 | Deployment diagnostic and complete raw program capture | Same changed deployment observed twice; complete capture independently replayed |
| 18:46 | Unsigned simulation on explicitly selected October 27 observation | Exact 998 output and 5,000 fee; 7.557 seconds; source journals unchanged |
| 18:58 | Fresh simulation plus single-leg cost assessment | 13 offline cases matched; fee 5,000 within cap 10,000; 7.337 seconds; source journals unchanged |

The quote/simulation/cost uploads contain summaries, not all underlying raw RPC
responses. Their arithmetic, internal hash bindings and clock relationships were
checked; independent raw-response replay was possible for the complete program
capture only. All observations are historical and cannot authorize a future send.
Single-provider deployment observations do not establish source/build equivalence.

## Invariants retained

- The original deployment pin remains the default. The new fixed observation
  requires the explicit simulation-only flag; sender paths are not repinned.
- One exact unsigned simulation follows the bounded read sequence: at most 20
  public devnet requests, no retry, original ten-second quote validity through
  final journal replay and cost computation.
- The actual controlled journals are opened read-only under the cooperating
  wallet lock. Both completed cycles stay closed. STOP, ledger changes, unknown
  reservations, funding shortfalls, deployment drift and stale evidence block
  acceptance. External wallet activity is not covered by that lock.
- Simulated fee and token changes must match the exact message and raw account
  evidence. Missing simulation metadata remains unavailable.
- The full network-fee cap is funded; priority fees already included in that fee
  are not counted twice. Exit and failed-attempt budgets remain unknown.
- Different test-token units are not treated as USDC profit. No round-trip
  economic result, signature, send, new spending reservation or pilot approval
  is produced.
- Scanner polling, alerts, observer admission rules, frozen model/protocol and
  backup configuration are unchanged.

## Release checks

Run the repository's two existing release groups locally before publishing the
consolidated head:

```bash
bash scripts/check.sh core
bash scripts/check.sh devnet-pool
```

These include the new negative cases, disposable two-cycle journal integration
with its signing key removed, original signing/recovery tests, scanner and
research regression suites. Tests use synthetic transport and disposable state;
they do not call public RPC, use the host wallet or evaluate the frozen dataset.
The PR records the final local results and the CI run for the published head.

## Deployment and next boundary

No Kali rebuild, restart, reinstallation or repeated live observation is needed
for this consolidation. Existing host checkpoints apply to the unchanged code;
this consolidation updates review records and documentation.

After consolidated review, the next engineering scope is fresh exit-leg evidence
and explicit round-trip funding/cost accounting. That work needs its own bounded
design and tests; an entry-side simulation cannot stand in for an executable exit.
The frozen strategy study remains unchanged until October 28 at 17:30
Europe/Amsterdam. Its decision is independent of these engineering checks.
Mainnet validation and explicit funded-pilot authorization remain later gates.
