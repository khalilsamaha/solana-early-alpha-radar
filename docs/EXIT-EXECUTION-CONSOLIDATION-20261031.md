# Exit execution integration consolidation — October 31, 2026

[PR #67](https://github.com/khalilsamaha/solana-early-alpha-radar/pull/67)
merged three accepted increments after PR #66.
All nine CI groups passed at head `86a6233ad536638b0b48ce2d233127d132a79082`.
Main commit `46cb51cd457a39def47248fe01883edf67d184eb` was verified to have the exact tested tree
`8501fb19d99809f8871a91f9df594671c198e41f`.

Accepted increments:

| Increment | Accepted Kali check | Scope |
| --- | --- | --- |
| Restricted exit signer | 27 cases, 18:14:04 UTC | Exact independently checked exit packet; durable attempt and acknowledgment |
| One-send exit transport | 24 cases, 18:37:40 UTC | Committed attempt before one exact send; bounded keyless recovery |
| Exit receipt accounting | 15 cases, 18:59:57 UTC | Exact owned inventory, protected balances, fees and retained commitments |

Each accepted public report matched its source replay. Local exit-accounting
validation also passed 27 targeted tests, including full-source restore and
19 existing recovery regressions. No scanner or observer deployment is included.

The first consolidation CI attempt passed three groups and hit the ten-minute
limit in two position-book groups. The runner now divides all 38 position-book
test modules into six regular partitions plus one dedicated exit-submission job,
and runs each module in an isolated process,
with visible progress and failure propagation. Partition-union checks confirmed
that no module was skipped or duplicated. The submission module takes about
8.5 minutes by itself, so it must not share a job with other modules. The ten-minute
CI limit and all runtime
freshness/deadline rules remain unchanged.

The next branch adds fresh post-exit balance observation. Its host acceptance,
durable scoped closure, allocation reuse and live execution timing remain open.
No mainnet enablement or strategy/model promotion occurs. Continue availability
captures on November 1, 3, 5 and 6; final review opens November 6 at 00:05 UTC
(01:05 Amsterdam), after the final capture.
