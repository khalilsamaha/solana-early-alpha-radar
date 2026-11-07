# Project review — 7 November 2026

## Decision

Continue a bounded devnet exit/recovery integration, but do not promote a trading strategy or describe the project as profitable. We have made measurable reliability progress. The current evidence does not establish an economic edge. More infrastructure or a more complex model does not resolve that gap.

The project has spent substantial effort on exit freshness, repeated validation and recovery. These were real defects exposed by host tests. The next milestone must be a complete, measured devnet exit and reconciliation, rather than an open-ended sequence of additional capabilities. In parallel, research must answer whether any fixed entry/exit hypothesis survives prospective testing and realistic costs.

## What the evidence establishes

| Track | Evidence | Current conclusion |
|---|---|---|
| Collection and operations | Scanner, walletless quotes, backups and health monitoring were deployed and previously checked on Kali | Implemented; this new offline report does not establish today's live scanner or backup health |
| Version control | PR #78 merged after all 12 CI jobs passed; main `d1153636db104295b9a8812565a1db17b1e47738` matches the tested tree | Consolidated base; subsequent increments stay in a batched feature branch until acceptance |
| Research validity | Frozen artifact and fixed forward windows; unknown/failure denominators retained | Useful evaluation discipline, not a successful strategy |
| Gain prediction | October 28 forward review: mean returned-quote 30s changes baseline -2.62%, early activity -8.79%, Fast30 -4.55%; models did not demonstrate improvement | No model promotion or strategy pilot |
| Availability hypothesis | Fixed October 30–November 6 window: 304 predictions, 302 known labels, seven UTC dates; only 15 excluded known labels against the registered minimum 20 | `insufficient-fixed-window-evidence`; do not extend this completed window or relax its threshold |
| Availability economics | Selected returned quotes averaged -7.18% at 30s and -13.89% at 120s; failures are separate | Avoiding some quote failures did not establish positive returns |
| Exit mechanics | Immutable signed evidence, conservative holds, one-send boundaries, recovery and retirement accepted in separate host tests | Useful reliability foundation; the currently retired held exit still needs a separately bound successor and exact settlement |
| Latest acceptance | November 7 17:57:42 UTC: 12/12 unsigned-successor checks, zero failures/skips, no user journals/network/signing | Offline contract accepted; live collection and signing are not established by this report |

The performance numbers above are from the committed study decisions, not a new rerun, enlarged sample, or new analysis of raw data. [Frozen review](FROZEN-REVIEW-DECISION-20261028.md) and [closed availability study](EXIT-RPC-SESSION-20261106.md#closed-availability-study) preserve their definitions and limitations. Quotes are not fills. Conditional returned-quote means exclude missing or failed quotes and are not a portfolio or failure-adjusted net return.

## Remaining engineering sequence

1. **Bounded successor observation — this increment.** Collect eight expiry/account responses and at most twenty fresh quote/simulation responses while the source is pinned. Validate against the accepted successor contract. Report timings and headroom. Do not persist an expiring candidate during this observation.
2. **Successor signing integration.** Bind an independently checked signing generation to the same retirement, attempt two and original cumulative reservation. Preserve old backend files and retired-sender denial. Test interruption, duplicate invocation and post-sign expiry before a live attempt.
3. **One controlled devnet exit and closure.** Check actual submission timing, signature recovery, exact token/fee deltas and idempotent scoped release. A timing failure is a failed gate, not permission to widen freshness or reset attempts.
4. **Target-route validation before any funded mechanics test.** Controlled test-pool success is not evidence that a mainnet aggregator route, liquidity, fees, account setup or failure behavior is equivalent. Specify the intended route and reconcile its complete costs first.

Do not create further generic execution layers unless a concrete failure or integration requirement justifies them. Keep operations fixes separate from frozen research and continue the approved local-test/batched-PR rhythm.

## Research priority after the current bounded integration

Prepare one decision-oriented, offline review of the existing compatible quote evidence: entry-to-quote delay, actual 10/30/60/120-second returned-quote paths, failures, lower-tail losses and token/day concentration. Keep sampling policies, versions and cohorts separate; deduplicate by source identity and sequence; do not merge hypothetical market-price outcomes with route quotes. Retain skipped signals without inventing labels. Quota-limited admitted watches are not a random sample of all market tokens, and provider quote failure alone is not proof of unsellability.

Use that review to decide whether there is a defensible new hypothesis about entry timing or tradable liquidity. Freeze its features, threshold, exit policy, cost assumptions and acceptance criteria before collecting a new untouched forward interval. Existing failed or insufficient studies remain closed. If economics remain negative, reject or redesign the hypothesis; do not tune repeatedly against the same holdout.

Additional ML complexity is not the next priority. Availability classification and return prediction are different targets; improving one does not prove the other. Any new model must beat simple fixed comparators on later, untouched data after the same costs and failure treatment.

## Real-money gates

A small funded mechanics test and a strategy pilot answer different questions. Neither is currently approved by these engineering reports.

- Mechanics: target-route validation, bounded allocation, exact signing/one-send/recovery, measured latency, receipt reconciliation and stop controls must pass; funding requires separate explicit authorization.
- Strategy: a frozen prospective rule must show credible net economic evidence, with failures, execution costs, concentration and uncertainty accounted for.

There is no evidence-backed profitable-launch date. The useful schedule is milestone-based: finish the finite devnet closure, review the economic hypothesis, then decide whether a funded mechanics test would answer an unresolved question. Waiting more days alone does not satisfy these gates.
