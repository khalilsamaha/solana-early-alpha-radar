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
| Latest host acceptance | November 7 22:06:51 UTC: complete successor signing rehearsal, all 24 checks; 1,106 ms headroom; recovery and preservation passed | Offline signing composition accepted; complete real-network submission timing and settlement remain pending |

The performance numbers above are from the committed study decisions, not a new rerun, enlarged sample, or new analysis of raw data. [Frozen review](FROZEN-REVIEW-DECISION-20261028.md) and [closed availability study](EXIT-RPC-SESSION-20261106.md#closed-availability-study) preserve their definitions and limitations. Quotes are not fills. Conditional returned-quote means exclude missing or failed quotes and are not a portfolio or failure-adjusted net return.

## November 7 collection acceptance update

The 18:21:10 UTC host observation passed all 28 fixed reads, with unchanged holds and 3.245 seconds of original freshness remaining at return. The matching offline check passed 13/13. The separate durable successor signing handoff passed all 15 Kali checks at 18:55:10 UTC. The independent key backend and keyless acknowledgment recovery passed all 50 Kali cases at 19:21:34 UTC. The [connected successor signing rehearsal](SUCCESSOR-SIGNING-REHEARSAL-20261107.md) now measures the complete collection, persistence, independent signing and acknowledgment path with a 1 MiB fixture and real clocks. Full live preparation/sign/send timing remains pending. See [the backend release](SUCCESSOR-KEY-BACKEND-20261107.md). See [the handoff release](SUCCESSOR-SIGNING-HANDOFF-20261107.md). These engineering results do not change the research decisions above.

## Corrected connected rehearsal accepted; transport integration next

The host report captured at 2026-11-07T22:06:51.601633+00:00 is
`offline-integration-passed`: four setup, four replay, eleven boundary and five
connected checks. The 1 MiB synthetic path took 12,643.145 ms including local
work before collection; it returned with **1,106 ms remaining on the original
collection deadline**. This is not a 12.6-second relaxation of that deadline.
The independent adapter took 1,267.984 ms; signing handoff took 7,776.616 ms.
Keyless recovery after STOP, repeated recovery, original evidence and cumulative
holds, and temporary cleanup all passed. There were no real network requests,
user-wallet access, transactions or scanner changes.

This accepts the signing component, not live submission latency. The headroom is
small and synthetic replies omit real network delays. The next finite sequence:

1. Bind one durable application send boundary to the exact successor signature,
   with bounded devnet preflight and read-only signature recovery. Exercise lost
   responses, crashes, STOP, expiry, substitution and held accounting offline.
2. Compose collection, signing and this sender under the original deadline with
   a real-clock 1 MiB rehearsal. Include lost-response recovery; do not enlarge
   freshness limits or treat a late response as a new send opportunity.
3. After timing acceptance, provide a separately authorized controlled devnet
   command, reconcile the exact successor receipt, collect fresh residual
   balances and record scoped closure. Until then no mainnet or pilot approval.

See [successor transport](SUCCESSOR-SUBMISSION-20261107.md). The failed setup and
193 ms late result remain in the [rehearsal record](SUCCESSOR-SIGNING-REHEARSAL-20261107.md).

## Submission component accepted; complete timing next

The host report captured at 2026-11-07T22:31:31.352668+00:00 passed all 17
successor submission cases, with no failures or skips. It validates the durable
one-send boundary, exact-generation recovery and conservative held accounting
using disposable data. It made zero network requests and sent no real transaction.

The [combined execution rehearsal](SUCCESSOR-EXECUTION-20261107.md) now joins the
actual collectors, independent key process and internal transport under one
original freshness deadline and one bounded operation. It deliberately loses
the synthetic send reply, then checks keyless signature observation after STOP
and idempotent terminal recovery. Repeated composition does not refresh, sign or
send again. The packaged local CLI passed all 22 checks; its combined path took
6,157.620 ms, with 5,109 ms remaining;
this is not a substitute for Kali timing acceptance or real network latency.

The next decision is finite: if the complete Kali timing/recovery gate passes,
prepare controlled devnet operation and exact successor receipt reconciliation.
If it fails, investigate the measured phase while preserving original deadlines
and attempts. Do not open a funded pilot or change the frozen study decisions.

## Earlier connected rehearsal failure — superseded by accepted run

The November 7 21:49:54 UTC Kali run passed four setup and 11 boundary checks.
It reached the full 1 MiB successor path and durably recorded its disposable
signature and acknowledgment, but finished 193 ms after the original deadline.
No transaction was sent; keyless recovery and final preservation assertions were
not reached. The earlier fixture setup failure was resolved. At that point complete signing
acceptance remained blocked on timing, independently of the accepted component
checks.

A profile found a duplicate full historical replay in the child adapter,
immediately before the parent's required post-child replay. The targeted
correction preserves full validation before boundary commitment, before key
invocation and after key invocation, plus exact saved-ACK binding. It changes no
clock, deadline, fee or inventory rule and does not affect scanner or research
services. The subsequent complete corrected Kali pass above satisfies that
offline signing gate.

## Remaining engineering sequence

1. **Bounded successor observation — accepted.** Collect eight expiry/account responses and at most twenty fresh quote/simulation responses while the source is pinned. Validate against the accepted successor contract. Report timings and headroom. Do not persist an expiring candidate during this observation.
2. **Successor signing integration — complete offline host rehearsal accepted.** Bind an independently checked signing generation to the same retirement, attempt two and original cumulative reservation. Preserve old backend files and retired-sender denial. Test interruption, duplicate invocation and post-sign expiry before a live attempt.
3. **Successor transport, then one controlled devnet exit and closure.** The offline one-send/recovery component is accepted; accept the combined real-clock rehearsal next. Then check actual submission timing, signature recovery, exact token/fee deltas and idempotent scoped release. A timing failure is a failed gate, not permission to widen freshness or reset attempts.
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
