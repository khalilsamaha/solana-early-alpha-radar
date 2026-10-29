# Scoped local reservation integration — 27 October 2026

## Host evidence reviewed

The supplied Kali terminal output at 03:39 UTC reports approximately ten hours
of Radar uptime, zero restarts, no container OOM kill, readiness HTTP 200, an active
quote observer, and 679 successful statistics refreshes with zero failures. The
statistics cache was about eleven seconds old. The declared-quote binding CLI
also reported all eight synthetic cases passed. This accepts the operational and
compatibility checkpoint shown in that output; the compressed report was not
independently replayed here, and none of it proves live execution profitability.

## What this increment adds

`position-book/reservation_view.py` reads the actual local controlled spending
ledger instead of accepting a public report or caller-supplied reservation totals.
It shares the existing wallet execution lock and opens journal connections under
`read_only_journals()` (`mode=ro` and query-only). Missing files, SQLite recovery
sidecars, unsafe file permissions/links, hash-chain errors, quarantine, inconsistent
receipt evidence, STOP and lock contention produce unavailable evidence. There is
no repair, database migration, journal creation or reservation release.

The scope is exactly the existing **two controlled devnet cycles**. Cycle-two
preparation replays the first closed cycle; historical fees are counted in the
cumulative total but not counted again as a live fee reservation. The current
ledger's terminal receipts are compared with replayed retained execution evidence.
The ledger head is checked again before the view is returned.

An unresolved entry retains its original-token principal and native fee reserves.
Its acquired-token reservation is **unknown**, not zero. Open and unresolved-exit
positions retain acquired exposure. A failed exit can have no remaining allocated
fee while still retaining token exposure. Missing receipt evidence cannot establish
that a reservation is clear. The reader reports observation time separately from
the last ledger event; an unchanged old ledger is not relabelled as a new event.

The public report includes the ledger head, event count, cycle binding hash and
scoped amounts, but no raw signed transactions or signatures. Private key files are
not read. Local owner-controlled files remain the trust boundary.

## Quote binding integration

`bind(home, wallet, pool, bundle)` requires `bundle.reservations` to be **null**.
It reads the ledger itself under the wallet lock, selects the exact source account
and mint, and supplies the derived token/native commitments to the quote checker.
The lock remains held through that check. Unknown account coverage blocks it.

The original public quote checker still requires declared reservations to predate
capture. A separate internal path permits this just-observed local ledger view to
follow account capture, with explicit ordering and age checks. Quote, policy and
account clocks are not refreshed or altered by reading the ledger.

The result `local-reservation-binding-consistent` means the scoped local evidence
and quote/account arithmetic agree at inspection. **It is not an atomic reservation
or execution permission.** No new intent, allocation or third cycle is authorized.
External wallet activity and other applications are outside this ledger's coverage.
No wallet-wide reservation claim is made. The existing completed cycles stay closed.

The current bridge still uses the declared direct devnet quote schema. A fresh
quote producer, pinned-program/simulation composition and separately scoped mainnet
route support remain work to do. Mainnet execution-cost evidence cannot yet be
treated as a semantically validated swap.

## Kali inspection

After fetching the pinned development revision supplied in chat, run as the
ordinary `redeye` user (no sudo):

```bash
cd ~/apps/solana-early-alpha-radar
umask 077
python3 -E -s \
  ~/apps/solana-radar-dev/position-book/reservation_cli.py \
  --directory "$HOME/solana-radar-devnet-rehearsal" \
  --wallet FNoAk1H1SEk5ZXbwVZDFUEyiDUnYF5vBQhZQbZKjeGPr \
  --pool EuRveSHpbfCJ3May56v7jmRtW97rbWyAikWFV5dCLPLT \
  --output "$PWD/radar-reservation-view-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

For intact closed journals, expect `local-reservations-observed`, phase `closed`,
zero held native lamports and zero held tokens. These zeros apply only to the
two-cycle controlled scope. `unavailable` returns exit code 2 and a report; preserve
the source journals and investigate instead of clearing STOP or retrying execution.

The ten-second read interval is an acceptance limit checked after bounded local
replay, not a hard process kill deadline. Slow replay may take longer and be refused.
No scanner rebuild, service restart, RPC, cloud transfer or frozen-study evaluation
is performed. The optional `--bundle` argument uses fresh public quote evidence;
do not redate old journal evidence to construct it.

## Validation and release status

New tests exercise the real synthetic two-cycle journals and actual decoders,
read-only storage, receipt replay, quote binding, CLI publication, corrupt/missing
evidence, unknown outcomes, STOP, clock limits and lock contention. The source
bytes are compared before and after inspection. Tests use disposable unfunded
fixtures; no live wallet request or host inspection has been performed here.

This remains a local-tested development checkpoint in the agreed batched workflow.
Full release regression and CI are required before merging a release candidate.
The frozen study checkpoint stays October 28 at 17:30 Europe/Amsterdam with the
original qualification guards.
