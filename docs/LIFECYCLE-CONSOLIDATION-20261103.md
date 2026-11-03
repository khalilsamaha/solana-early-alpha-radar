# Connected lifecycle acceptance — November 3, 2026

This batch consolidates three accepted increments above main
`1c3b2dbde43c9a6453bacd6f45632b85067f893e` (PR #71). Each increment received local
checks and a pinned Kali host report before this grouped CI run.

| Increment | Development commit | Host evidence UTC |
| --- | --- | --- |
| Fresh exit collector, signer and one-send transport | `b89adcef90070b5d154ad69b4470b690a5e7ac21` | November 2 07:42:19; 21 cases |
| Recovered receipt accounting, fresh balances and scoped closure | `4d06aac33c0436e7dad3f29549ace1a25c37594c` | November 3 04:07:01; 21 cases |
| Connected lifecycle timing and lost-response recovery | `6447b9af73affad6d3186e2eb11dd8c4abd36e58` | November 3 04:17:47; 9 connected checks |

The first two reports matched their portable contracts exactly. For the timing
report, the non-timing contract matches; Python version and measured nonnegative
finite durations are host-specific. Seven stages completed, both transaction legs
retained their original deadlines, and final read-only recovery preserved closure
identity and journal bytes without further provider requests.

## Kali timing evidence

| Inclusive stage | Seconds |
| --- | ---: |
| Disposable fixture setup | 42.584 |
| Entry collection, signing and synthetic send | 2.822 |
| Entry receipt and accounting | 0.210 |
| Exit collection, signing and synthetic send | 4.308 |
| Exit receipt, accounting and closure | 8.083 |
| Read-only closure recovery | 4.225 |
| Repeated closure recovery | 3.852 |

This is one offline sample. Fixture setup is not part of a trading leg. Provider
and confirmation latency are excluded, so these timings are not mainnet or live
latency acceptance. The 8.083-second inclusive settlement stage includes receipt
and accounting replay before the balance collector, and final projection after
closure. It is not a measurement of time consumed inside the balance freshness
window. Existing expiry and STOP guards remained enabled and passed.

Lost responses were deliberately exercised on both synthetic sends and after the
closure commit. Existing signatures and durable records were reconciled; neither
transaction was resent and scoped funds were not released twice. No user wallet,
real RPC, scanner, quote observer, study or backup was modified by the rehearsal.

## Consolidation checks

Increment-local validation passed 35, 36 and 9 targeted tests respectively;
these totals overlap and must not be added as distinct coverage. Source hygiene
and partition coverage/stability checks also passed.

The new settlement regression module took 413 seconds in its recorded local run.
The existing position-book-3 CI group took 214 seconds in the accepted PR #71 run.
Those are different environments, not an exact duration prediction, but together
show insufficient margin for the existing ten-minute job limit. The new module
therefore gets its own position-book-9 group. Every test module is checked
exactly once. The matrix now has twelve
groups. No tests, assertions or time limits are removed. All groups must pass on
the exact consolidation head before merge.

The first consolidation run (41577640207) passed eleven groups; group 2 reached
the ten-minute job limit while its final signer-handoff module was still running.
No assertion failure was reported, but that incomplete group is not accepted.
Its exit-balance module passed in 264.405 seconds. Group 3 completed in 171 seconds,
so the explicit manifest now moves exit-balance from group 2 to group 3. This is
a measured redistribution within the same twelve jobs, without skipped tests or
a longer timeout. All other assignments remain unchanged; adding future files
still cannot reshuffle existing assignments. The complete matrix must pass again
on the revised head.

## Next acceptance scope

After consolidation, prepare a controlled devnet acceptance interface with
explicit directory/wallet/pool and fee limits, durable admission identity, one-send
entry and exit actions, and read-only recovery. Keep entry and exit as separate
operator actions. A collector failure, STOP, expiry, incomplete signer response
or uncertain send must never trigger a replacement or resend automatically.

Measure actual provider latency, original-deadline headroom and receipt effects
there. Preserve evidence before any next-cycle action; historical scoped closure
still does not establish wallet-wide available funds. Mainnet route validation,
wallet-wide budgeting, pilot limits and economic strategy qualification remain
separate prerequisites. This merge deploys no trading service.

Availability-study captures on November 3, 5 and 6 and review on November 6 at
00:05 UTC / 01:05 Amsterdam remain unchanged.
