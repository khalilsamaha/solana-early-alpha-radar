# Exit lifecycle consolidation — November 1, 2026

This batch adds fresh balance reconciliation, atomic scoped closure and one
read-only lifecycle view after PR #67. It does not deploy the scanner or observer,
connect execution to signals, authorize another allocation or enable mainnet.

| Increment | Published source | Kali acceptance (UTC) |
| --- | --- | --- |
| Fresh post-exit balances | `fbce80b5ed00135801afd192c580c9dc29489750` | 18 cases, November 1 07:43:01 |
| Durable scoped closure | `fc49b19be802c34cc9a51e1902dc409c4f5c7571` | 21 cases, November 1 08:04:24 |
| Unified lifecycle | `1820965156e5cf31850b63c9b78850bd39d49ddc` | 24 cases, November 1 10:10:12 |

Each public host report matched its expected source cases and no-action flags.
These were synthetic/disposable host exercises, not live network acceptance.
Closure retained the independent source replay and private stopped restore;
the lifecycle view kept unknown amounts unavailable and original caps separate
from current holds/releases. Source hygiene and targeted local tests passed.
PR #68 merged as `55852a1227c1e4f2284720e829374e9688da56ea` after all nine
CI groups passed at reviewed head `568bb23bb3003d4763f019c606c0511096da917c`.
The merged tree exactly matched that reviewed source.

Automated review identified a durable-STOP historical replay edge case after
the initial consolidation. The correction binds a saved closure to a verified
admission-history prefix and allows only later STOP-only state changes. Current
receipt/accounting conflicts are still rejected. The lifecycle host exercise
now covers both the STOP file and a durable ledger STOP. All 19 local regression
tests and all nine CI groups passed. PR #69 merged as
`c9e38aba5927cd346b4694cf7e904c278646cd5c`; its tree exactly matched reviewed head
`e0f7cc1b49a49ea8ecc4f08e0983ba81841d4abd`.
The strengthened host case is pending and is included in the timing release.

## Accounting boundary

Raw finalized exit effects are insufficient to claim current balances. The
balance collector binds a fresh snapshot to those effects; scoped closure
replays it under the writer lock and records actual proceeds plus unused fee
commitments exactly once. The read-only view explains that history consistently.
An original principal cap is not credited again. Protected inventory is not
released. Missing or conflicting evidence never becomes a zero commitment.

A recorded release is not a wallet-wide spendability result. No allocator reuses
it, no failed exit is retried, and no closed rehearsal is reset. Historical STOP
inspection does not bypass STOP for actions. Checksums are not protection against
malicious replacement of all locally trusted source evidence.

## Next engineering work

Prepare the separate-transaction rehearsal by measuring the real entry collection
and source-validation path before introducing a live admission writer. Preserve
all freshness limits, source identity and failure states. A timing check must
retain failures rather than obtain a pass by repeatedly refreshing its evidence.
Live signing, submission, delayed exit and final closure need their own tightly
scoped host acceptance. The previously completed controlled cycles stay closed.

## Research and operations

The November 1 capture is already taken, as reported by the user. Continue on
November 3, 5 and 6. The final capture/review opens November 6 at 00:05 UTC /
01:05 Amsterdam. No strategy/model promotion, research registration change,
production sampling change, rebuild or restart follows from this consolidation.
