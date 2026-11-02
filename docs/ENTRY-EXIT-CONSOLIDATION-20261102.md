# Entry-to-exit preparation consolidation — November 2, 2026

This batch joins three locally tested, host-accepted increments on the PR #70
base. It follows the agreed cadence: focused local tests for each increment,
then one grouped CI run for consolidation.

| Increment | Pinned development commit | Host acceptance UTC |
| --- | --- | --- |
| Fresh collection to independent signer | `269fdea7d8b2ee42aa136490314df0a5978fda62` | November 2 06:40:05; 17 cases |
| Fresh entry sender and keyless receipt recovery | `a6b5c165212e6c1df1bea698ff90cb3c4f3fcbef` | November 2 06:58:18; 21 cases |
| Collected settlement and delayed unsigned exit | `e4ca4d0cc8c64954eb0e91bb34e1acb667cbb7f1` | November 2 07:13:54; 18 cases |

Each public host report exactly matched its portable contract. The gates used
synthetic transport and temporary journals, without wallet access or broadcasts.
Local disposable-key tests separately exercised the real independent signer.

The batch preserves one original entry deadline through signing and send,
records uncertainty before transport, and supports receipt recovery without
resigning or resending. Receipt effects establish owned quantity and paid fees.
A separately collected unsigned exit protects other inventory and held fees;
missing, conflicting or failed entry outcomes cannot enable it. Existing expired
preparations cannot be silently replaced.

Local validation for the increments passed 36, 43 and 59 targeted tests
respectively; these totals overlap and are not a count of distinct tests.
CI partition coverage and source/package hygiene checks also passed. The full
matrix remains required before this batch is merged. No test or timeout waiver
is part of the consolidation.

This is source consolidation, not runtime deployment or execution approval.
Scanner, observer, backups, frozen study, wallet and dedicated rehearsal state
remain unchanged. Next: connect fresh exit preparation to restricted signing and
bounded transport, followed by full lifecycle accounting/closure acceptance and
host latency measurement. Mainnet/economic readiness is not established.
