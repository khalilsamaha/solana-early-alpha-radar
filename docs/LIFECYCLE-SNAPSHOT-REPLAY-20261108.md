# Unsent lifecycle snapshot replay — November 8

Current acceptance: the full Kali CLI passed all 42 checks at 08:07:13 UTC on
November 8, with 1,343 ms remaining. Recovery, preservation and cleanup passed.
The [consolidation record](SUCCESSOR-CONSOLIDATION-20261108.md) preserves the
failed run, diagnostic result and current phase status. Earlier pending states
below are historical. Real-provider execution and settlement remain separate.

## Measured problem

The Kali profile captured at 05:38:36 UTC is valid diagnostic evidence from clean
commit `1f2c910699a0159474a17ac61d861ca4674481b7`, Python 3.14.6, Node 24.19.0.
The instrumented first attempt took 14,884.318 ms and finished 827 ms after its
original deadline, before the send. No recovery/preservation acceptance followed.
Cleanup succeeded. No real network, transaction, wallet or scanner effects occurred.

Forty preparation replays consumed 6,026.277 ms exclusive wall time and
5,919.947 ms thread CPU. Other lifecycle work consumed 4,188.953 ms exclusive wall
time, including 3,483.974 ms thread CPU. Parent signer-backend time includes its
independent process. Journal transaction commit contexts totalled 9.913 ms.
Nested inclusive times cannot be added. Runtime differences and hardware/load
are confounded; this does not establish Python 3.14 as the cause or justify
downgrading the live host.

## Bounded correction

Previously, an unsent lifecycle projection called preparation.saved directly,
replayed it again through signing.read, and again through the transport status
used by exit-accounting review. The correction obtains the preparation from the
signing reader's existing output sink, then reviews transport against that exact
generation inside one query-only SQLite snapshot. One projection now replays
preparation once instead of three times. No caller supplies a trusted verdict.

The transport projection still checks signing identity, account slots, boundary,
ACK, capture consistency, clocks and orphan records. Only validated
`not-attempted` status uses the existing pending-accounting projection. Saved
accounting and forbidden closure checks still run. Submitted generations retain
the full original raw receipt/accounting review. Unsigned, unknown and
quarantined lifecycle behavior is preserved.

No cache survives the helper call. Later calls freshly read and validate the
database. The existing source locks, before/after signer checks, post-RPC replay,
pre-send writer boundary, STOP checks, old backend markers, original deadlines,
spending limits and unresolved inventory/fee reservations are unchanged.
There is no new execution command or real-provider action.

## Regression contract

Eight added cases check identical evidence/projection and hashes with a three-to-one
replay-count assertion; unsigned/unknown/quarantined compatibility; orphan ACK and
capture rejection; fresh detection of changed preparation/signing; snapshot and
clock requirements and exception ownership; full accounting review after a send;
competing-commit exclusion; and orphan accounting/closure rejection.

The public offline command now runs **42 checks**: 4 setup, 12 composition
boundary, 5 computation ownership, 6 retirement snapshot, 8 lifecycle snapshot
and 7 connected cases. Reports identify `lifecycle-snapshot-replay-1`.
Kali must report `offline-integration-passed`, all 42 cases, positive deadline
headroom, preservation completed and temporary cleanup completed.

## Local validation

The complete uninstrumented CLI passed all 42 checks on the development host.
The measured integration took 4,277.359 ms and returned with 6,947 ms remaining
on its original deadline. All seven connected cases completed, including
keyless recovery, unchanged historical source, conservative held accounting,
preservation and cleanup. One synthetic send occurred; real network requests
and real transactions remained zero. This result does not clear the Kali gate.

All 52 targeted regression tests passed: 10 exit-read snapshot, 6 lifecycle,
7 exit-accounting, 12 original-submission and 17 successor-submission tests.
These include their existing portable CLI contracts. All 14 profiling tests and
both test-partition coverage checks also passed. Source hygiene and package
manifests passed for 943 tracked files, and the staged diff passed whitespace
checks. The full repository suite and hosted CI remain part of later phase
consolidation after Kali acceptance; neither was claimed for this increment.

## Host check and following gate

Use the immutable development commit provided in chat, then run:

```bash
cd /home/redeye/apps/solana-early-alpha-radar
python3 -B -E -s -W error::ResourceWarning \
  /home/redeye/apps/solana-radar-dev/position-book/successor_execution_cli.py \
  --output "$PWD/radar-successor-execution-rehearsal-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

This is the full uninstrumented offline acceptance gate, not another cost profile.
No Docker restart or live key/transaction is involved. A development push is
authorized to distribute this check. Consolidation and CI wait for complete Kali
acceptance, as recorded in [the working agreement](DEVELOPMENT-RHYTHM.md).
Real-provider timing, exact successor receipt reconciliation and scoped closure
remain later work; see [the conditional timeline](PROJECT-TIMELINE-20261108.md).
