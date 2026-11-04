# Exact admission-history validation reuse — 4 November 2026

## Purpose and boundary

The accepted Kali preserved-exit observation completed collection in 7,386 ms
and additional validation in 1,403 ms: 8,789 ms total, with 1,211 ms remaining
inside its original ten-second collection window. It made twenty fixed devnet
read/simulation requests and did not sign, submit, append a preparation or release
holds. That headroom does not include persistence, signing or submission.

This change avoids repeatedly decoding and hashing an identical admission-event
chain within one fresh-exit attempt or one preserved-exit observation. It does not
skip the SQL query: every call fetches the bounded current rows again. The key
contains the exact canonical current policy and every sequence, timestamp, value,
previous hash and hash. Any difference forces the original complete validator.
A hit reconstructs a fresh mutable state from the already validated immutable
JSON; callers cannot modify the saved result through a returned dictionary.

The scope is independent for each operation, clears on return or exception, and
is not inherited by a new thread. Nested operations have independent scopes.
Retention is capped at 32 entries, 256 KiB of input payload per entry and 2 MiB
of retained input payload overall. These are payload budgets, not Python heap
measurements. Oversized inputs and empty histories use the original validator;
failures are never retained. Without a scope, validation behaves as before.

Current ownership, accounting, source identity, balances, STOP state, backend
markers, signature validity and clocks still run through their existing checks.
No authorization decision or live RPC response is memoized. The separate signer
continues to independently validate its contract. No deadline, replacement count,
fee ceiling, protected inventory or sampling rule changes.

## Local evidence

- Seven targeted tests cover exact equality, independent returned dictionaries,
  fresh SQL reads, every key column, policy mutation, a committed STOP append,
  rehashed accounting tampering, scope isolation, failures and memory budgets.
- The connected offline profile retains twelve integration cases, ten independent
  signer cases, twenty collection requests, and explicit persisted-expiry refusal.
  The synthetic lost-response path still recovers read-only without resending.
- One sequential before/after full profile measured 2,261.818 / 2,193.760 ms.
  This modest difference is not a stable speedup claim. Both retained 49 evidence
  reviews, 45 provenance reviews and six source replays.
- The connected operation reported 1,130 history reads, one complete validation
  and 1,129 exact-input reuses; no SQL read was skipped. Retained payload: 22,536
  bytes. These counts depend on the fixture and may differ on Kali.
- A separate same-fixture check alternated disabled/enabled scopes over three
  samples of 500 reads each. Median time was 171.859 / 41.868 ms. This measures
  only admission-history reads; it excludes real network latency and does not
  establish full-path host timing or safe execution headroom.

The regression set also covers the original admission tests, the preserved
observation fault matrix and the connected profile. Kali acceptance passed at 18:24:18 UTC on November 4: 4,260.472 ms, twelve
integration and ten independent signer cases, with expiry still refusing signing.
See [the next continuation gate](UNSIGNED-EXIT-CONTINUATION.md) for the evidence
identity and remaining live-timing limitations.

## Kali acceptance

Fetch the pinned development commit supplied in chat. No Docker rebuild, service
restart, private wallet access or real transaction is needed for this check:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/exit_profile_cli.py" \
  --output "$PWD/radar-history-reuse-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-exit-profile-passed`, complete connected/signer checks,
`sqlReadsSkipped: 0`, no cached authorization decisions, and a valid phase report.
Synthetic signing uses disposable test keys only. Share the generated public
report to evaluate timing; a single quick run does not authorize execution.

## Remaining work

1. Accept the Kali connected profile and assess the remaining time budget.
2. Design and test a separately guarded continuation for the already preserved,
   expired replacement. Keep both original records and cumulative holds intact;
   do not reset or implicitly reuse the one replacement allowance.
3. Only after that gate, perform an explicitly scoped devnet continuation and
   reconcile its actual finalized receipt, inventory and fees before closure.

The current real devnet exit remains unresolved. This release supplies no new
continuation command. Scanner, quote observer, frozen studies and mainnet
activation remain unchanged. Availability preservation on November 5 and 6 and
the scheduled study review remain separate work.
