# Durable exit signing handoff — 31 October 2026

The collected-preparation Kali report captured at 17:39:33 UTC matched all 21
cases and public flags exactly. This increment adds a durable, one-call adapter
boundary to the first exit of that same admission. It does not connect a real
wallet backend, expose a live CLI, submit a transaction or release an allocation.

## Exact request and recovery

Only a collected preparation is eligible. The dispatcher independently replays its
raw evidence and request provenance, checks current evidence freshness, the exact
reverse instruction contract, acquired quantity, retained fee commitments, current
admission identity and the historical source. It holds the cooperating wallet lock
and a SQLite write reservation during validation. A separate read-only connection
avoids nested transactions during accounting replay.

Before calling the explicitly supplied internal adapter, the dispatcher commits
one immutable request containing the exact packet and preparation/accounting hashes.
It checks STOP and the original collection deadline before commit and again before
the call. An exception, crash, lost response or failed acknowledgment write leaves
`exit-signing-unknown`. Calling dispatch again never calls the adapter again.

A recovered response must have one valid Ed25519 signature from the expected wallet
and the exact admitted message bytes. The full wire remains private. Recovery may
record an existing response after expiry or STOP, but that is not submission approval.
Invalid or contradictory responses quarantine the signing state and preserve any
previous valid wire. No path refreshes evidence, retries signing, consumes a send
attempt, releases fees or increases the allocated token quantity.

The signing journal allows at most three events of at most 8 KiB each: boundary,
optional accepted response and optional quarantine. Reads replay schemas, transitions,
clocks, request identity and signatures, rather than accepting recomputed hashes.
The existing 64 MiB database cap also applies before writes commit.

## Isolation and snapshots

The signing state lives in the same admission database as entry accounting and exit
preparation. Existing private snapshots preserve it automatically. Their semantic
projection now includes the optional signing head and state. Isolated restore
validates unknown and signed states, keeps the restored source stopped, and detects
changed requests even when record hashes and the manifest inventory are recomputed.
Older snapshots without signing records keep their previous projection.

Tests use fake HTTP and public pre-signed fixtures whose disposable key was discarded.
The separate full-source integration test creates only disposable synthetic keys;
no user wallet is read. This does not establish timing or execution success on devnet.
No scanner, observer, notification, backup-service or fixed-study settings change.

## Local validation

Passed: 10 handoff/CLI tests (including the 21 portable cases), two full-source
unknown/signed restore tests, 47 related admission/preparation tests and 19 existing
snapshot regression tests. Source hygiene and whitespace checks passed. These
checks do not substitute for the pinned Kali offline exercise or future live timing.

## Kali acceptance

Fetch the pinned source supplied in chat and run:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/exit_signing_handoff_cli.py" \
  --output "$PWD/radar-exit-signing-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, 21 cases. The command supports only `--output`;
it makes no real RPC calls, accesses no keys and creates no new signatures. Upload
only its public `.json.gz` report. No service restart or rebuild is required.

## Remaining sequence

1. Connect the independent restricted exit key backend to the committed request,
   with a durable backend attempt and saved acknowledgment. Do not reuse the entry
   signer's markers or infer permission from an offline report.
2. Bind one devnet submission to that signed exit, including current genesis,
   blockhash and fee checks; recover the original signature without resending.
3. Reconcile exact exit receipts, fees, residual inventory and allocation release.
4. Consolidate accepted increments under the agreed local-test/host-check/PR rhythm.

The confirmation study remains frozen, with captures November 1, 3, 5 and 6 and
review November 6 at 00:05 UTC / 01:05 Amsterdam. These engineering checks do not
establish strategy profitability or authorize a funded pilot.
