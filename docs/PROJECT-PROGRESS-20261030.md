# Solana Early-Alpha Radar — progress and roadmap

Updated 3 November 2026. This is a current engineering assessment, not a trading
approval or profitability forecast. Earlier dated roadmap sections remain history.

## Where we are

Latest: PR #72 consolidated the accepted connected lifecycle after all twelve CI
groups passed. The November 3 unsigned live timing observation passed with 2.454
seconds of original-deadline headroom. That does not cover durable admission,
signing and send. The [entry phase profile](ENTRY-PHASE-PROFILE.md) now measures
nineteen local stages in a disposable offline exercise; host acceptance is pending.
Full live execution timing and economic qualification remain separate open gates.

The project has a working collection and research platform, plus a controlled
devnet execution and accounting foundation. The projected exit-fee observation
passed its October 30 host gate within the original freshness window. The atomic
rehearsal passed its October 30 host gate as well. The immediate engineering work
is now bounded funding and failure handling for separate transactions.
The larger product blocker is economic: the completed forward study did not
establish a profitable selection rule. These are separate problems and both matter.

PR #60 consolidated the three host-accepted post-entry/reverse-message increments
after CI passed at the exact reviewed head. PR #61 merged and consolidated the fee increment
and timing correction after the corrected host pass: 9.419 seconds, 582 ms remaining.
The atomic rehearsal contract passed its 18-case host check at 06:46 UTC. The
live collector passed at 08:27 UTC: 23 requests, 7.626 seconds and 2.375 seconds
remaining. A third increment adds an opt-in bounded exit-attempt policy to the
offline ledger; its 09:17 UTC host report passed all 14 cases and matched the local
portable result exactly. PR #62 consolidated the three accepted increments after
both CI groups passed;
main commit `6ca918927786be8c93ab28765dc47bd5e44a3cde` matches the reviewed tree.
The pre-sign admission, locked reader and durable signer-adapter handoff have
passed their 15-, 17- and 15-case host checks. PR #63 merged the three-increment batch after both CI
groups passed; main `c632bd7388faea410a5bc401e66e27fdff445807` matches the reviewed tree. PR #64 subsequently consolidated the restricted signer and receipt collection.
PR #65 consolidated same-ledger entry accounting, combined recovery and fresh
delayed exit preparation after their host checks and all five CI groups passed.
The bounded exit collector passed its 19-case host check. Atomic collected
preparation passed all 21 host cases at 17:39:33 UTC. The durable exit signing
handoff passed all 21 host cases at 17:55:29 UTC. PR #66 merged the three-increment batch after all five CI groups passed.
The independent exit key backend passed its 27-case disposable-key Kali check at
18:14:04 UTC. One-send exit transport and bounded recovery are now built; the
24-case synthetic host gate passed at 18:37:40 UTC. Collected exit receipt
accounting passed its 15-case synthetic host gate at 18:59:57 UTC.
PR #67 consolidated those three increments after all nine CI groups passed;
main matches the tested source tree.
The fresh exit balance collector passed all 18 host cases on November 1 at
07:43:01 UTC. Durable scoped closure passed all 21 host cases at 08:04:24 UTC.
The unified read-only lifecycle view passed all 24 host cases at 10:10:12 UTC.
PR #68 consolidated this batch. The PR #69 durable-STOP correction passed 19
local regressions and all nine CI groups, and merged to main; its strengthened 24-case lifecycle host exercise passed on November 2.
The November 1 study capture is already taken, as reported by the user.
PR #70 consolidated the host-accepted timing, signature replay and isolated
durable admission batch. All ten CI groups passed after isolating the heavy closure
suite, preserving every test and the 10-minute job limit. Main is
`777a355897270addccf3bd6218e2352594d0c860`.
The fresh collection-to-signing, one-send entry and settled-entry/unsigned-exit
increments passed their 17-, 21- and 18-case synthetic host checks on November 2.
PR #71 consolidated them after all eleven CI groups passed; main is
`1c3b2dbde43c9a6453bacd6f45632b85067f893e`. The next fresh exit transport integration is built
and locally tested; its 21-case synthetic host acceptance passed on November 2
at 07:42 UTC. It
preserves the original exit expiry through the actual independent signer and
one-send transport. These are internal integration components, not a deployed
production sender.

The next [exit settlement integration](EXIT-SETTLEMENT-INTEGRATION.md) connects
recovered receipts, fresh residual balances and scoped closure. The remaining
immediate gates are: consolidate the [accepted connected lifecycle batch](LIFECYCLE-CONSOLIDATION-20261103.md),
then scope explicit controlled devnet acceptance with real provider latency. The
Kali lifecycle profile passed nine connected checks on November 3 at 04:17 UTC. The settlement host check passed all 21 cases on November 3 at 04:07 UTC. The availability study remains independent, with captures on November
3, 5 and 6 and review on November 6 at 00:05 UTC. Neither synthetic execution
success nor model fit minimums establish a profitable real-money rule.

Status definitions: **accepted** means the stated scope has test/host evidence;
**built** means code exists but the stated acceptance gate is outstanding;
**collecting** means a fixed study is in progress; **pending** means work remains.
An earlier successful operational check does not prove present host health.

## Tasks and subtasks

| ID | Task / subtask | Status and evidence | Remaining acceptance gate |
|---|---|---|---|
| 1 | Hosting and operations | Established on the Kali host | Maintain current operational evidence |
| 1.1 | Docker service, localhost dashboard, authentication and restart policy | Previously host-verified | Check after deployments/reboots; no new deployment in this release |
| 1.2 | External heartbeat and DOWN/recovery notification | Previously tested | Continue end-to-end outage checks without suppressing failures |
| 1.3 | Daily local scanner and quote-ledger snapshots | Implemented; integrity checks demonstrated | Verify recent job timestamps and success, not only historic status |
| 1.4 | Backblaze copies and download verification | Implemented; pay-as-you-go selected following cap failures | Confirm current cloud job success and periodic restore evidence |
| 1.5 | Retention, disk growth and write load | Bounded tooling exists; earlier growth/I/O issues investigated | Trend resource usage and retention behavior as history grows |
| 1.6 | Private execution evidence recovery and key custody | Local key-excluded snapshots and isolated restore accepted | Encrypted off-machine recovery and key recovery procedure remain separate |
| 2 | Discovery, monitoring and alerts | Operating research platform | Preserve data quality and coverage as sources change |
| 2.1 | PumpPortal, DEX, Jupiter and Helius collection | Integrated | Provider failures, stale responses and missing fields stay visible |
| 2.2 | Candidate scheduling and bounded active queue | Improved from substantial unattempted coverage | Track first attempts, eviction, refresh age and rate limits |
| 2.3 | Security/liquidity labels and token identity links | Implemented | Unknown data must not become a security pass |
| 2.4 | Telegram, paper entries and historical outcomes | Implemented and previously host-verified | Keep observed, pending, missing and gapped outcomes distinct |
| 2.5 | Statistics memory and refresh isolation | Corrections deployed; latest supplied October 27 health check had zero restarts and zero worker failures | Current health is not inferred from that older snapshot |
| 3 | Research evidence and execution realism | Built and collecting | Avoid selection bias and optimistic outcomes |
| 3.1 | Baseline, early-activity and Fast30 cohorts | Versioned and compared | Analyze policy/version periods separately |
| 3.2 | Observation quality and same-pool histories | Implemented | Repeated responses do not prove fresh market movement; pool changes remain explicit |
| 3.3 | Walletless quote observer | Separate bounded service; three-cohort budgets | Retain rejected/skipped signals and failed quotes in denominators |
| 3.4 | Historical capture and dataset preparation | Bounded chunk capture, deduplication, source identities and local backup support | Preserve all required windows before retention expires |
| 3.5 | Delay/cost/outcome analysis | Implemented research models | Sampled prices and returned quotes are not actual fills or net profit |
| 4 | Strategy and ML qualification | No model approved for live trading | Demonstrate future economic value, not only classification performance |
| 4.1 | Frozen October study | Reviewed 781 forward watches; original result replayed | Completed development evidence, not a reusable untouched holdout |
| 4.2 | Profit prediction and richer entry context | No convincing improvement; cohort quote means were negative | Revise or retire weak hypotheses using explicit new research versions |
| 4.3 | Early-activity exit-availability hypothesis | Retrospective lead identified; not activated | Separate prospective confirmation with unchanged weights/threshold |
| 4.4 | Confirmation collection | October 30–November 5 UTC; manual preservation November 1, 3, 5 and 6 | Do not refit, change sampling, or inspect outcomes early |
| 4.5 | Confirmation review | Scheduled protocol gate: November 6 00:05 UTC / 01:05 Amsterdam | Review coverage, 200 known labels, seven labelled UTC dates, 20 failures and 20 excluded known labels; unmet guards mean insufficient evidence |
| 4.6 | Economic acceptance | Pending | Evaluate costs, missing exits, loss severity, concentration in best token/day and untouched forward performance; availability improvement alone is insufficient |
| 5 | Controlled devnet transaction lifecycle | Two fixed test cycles completed and reconciled | Preserve closed journals; this is not general trading support |
| 5.1 | Dedicated wallet, test assets and fixed pool | Prepared and exercised | Never infer mainnet asset or program support from these fixtures |
| 5.2 | Scope/message checks and restricted signing | Controlled paths implemented | Maintain exact program, roles, quantities and fee limits |
| 5.3 | Durable one-send boundary and recovery | Implemented with terminal evidence | Uncertain submissions remain unresolved; no blind retry |
| 5.4 | Entry/exit receipts and position accounting | Two-cycle receipts, cumulative fees and idempotent reconciliation accepted | New cycles need their own validated scope and reservation state |
| 5.5 | Stop controls, reservations and external-credit reconciliation | Implemented for controlled scope | General wallet/portfolio-wide concurrency and exposure controls remain pending |
| 6 | Integrated quote, simulation and costs | In progress — current engineering focus | Complete freshness-bounded evidence before another integration step |
| 6.1 | Quote ↔ exact instruction/account binding | Accepted | Remains a controlled direct devnet route |
| 6.2 | Current raw pool/program state and local reservation checks | Accepted | Deployment observation is not proof of source/binary equivalence |
| 6.3 | Exact unsigned entry simulation and single-leg fee caps | Accepted | No signing or submission in these observers |
| 6.4 | Independent reverse/paired cost observations | Accepted for their stated independent-state scope | Must not be presented as a sequential round trip |
| 6.5 | Same-simulation post-entry pool transition and reverse quantity | Accepted | Returned simulated accounts are not committed chain state |
| 6.6 | Reverse-message draft with exact acquired quantity/minimum | Accepted October 30: 998 input, projected 997 output, minimum 988 | No exit execution or future blockhash guarantee |
| 6.7 | Exact reverse-message fee and conditional two-leg caps | Accepted October 30: 11 offline cases, 22 requests, 9.419-second complete observation; 5,000 lamports per leg and 20,000 combined caps | 582 ms headroom is one passing sample, not sustained latency reliability |
| 6.8 | Supported sequential rehearsal | Accepted for one atomic host observation: 21 cases, 23 requests, matching effects and original deadline | Atomic success does not prove two delayed transactions or sustained latency reliability |
| 6.8.1 | Ordered message and acquired-quantity binding | Accepted: 18-case host self-check; one zero-signature transaction, shared compute budget, two exact swaps | No signer/sender connection |
| 6.8.2 | Intermediate token-flow and residual review | Accepted: four parsed transfers and final balances matched; acquired residual zero | Only the stated controlled standard-SPL route |
| 6.8.3 | Bounded live atomic collector | Accepted: 7.626 seconds, 2.375 seconds remaining, 5,000 combined fee, Clock/oracle/token/pool checks | One passing sample; future observations must retain all gates |
| 6.8.4 | Separate delayed-entry/exit workflow | Pending | Independent fee/blockhash lifecycle, failed exit exposure, stop/recovery; not satisfied by atomic rehearsal |
| 6.9 | Complete funding and economic reconciliation | In progress | Include raw admission, durable integration, fee/rent/tip treatment, residual positions and explicit valuation |
| 6.9.1 | Bounded exit-attempt fee commitments | Accepted offline: 257 local regressions and exact 14-case host replay; v2 reserves all 1–3 exit caps and retains unknown exposure | Live admission/sender integration remains pending; no production migration |
| 6.9.2 | Quote/funding-to-durable-admission adapter | 15-case host check accepted October 30; raw pricing/effects and durable reservation | Preserve the original expiry and unknown commitments |
| 6.9.2a | Locked reader and signed acknowledgment binding | Accepted: 17-case host report matched October 30 | Keep source checks under the cooperating wallet lock |
| 6.9.2b | Signer-adapter and durable accounting handoff | Accepted synthetic gate: all 15 host cases matched at 13:30 UTC on October 30 | Production key backend and authoritative receipt application remain unconnected |
| 6.9.2c | Same-ledger receipt integration | Accepted synthetic gate: all 14 host cases matched October 30 at 15:51 UTC | Submission/RPC provenance and allocation release remain unconnected |
| 6.9.2d | Restricted key backend | Accepted: 19-case disposable-key host report matched October 30 at 18:38 UTC | No production command or deployment |
| 6.9.2e | Durable submission and genesis-bound receipt collection | Accepted: exact 18-case host report at 19:10 UTC; consolidated in PR #64 with passing CI | No runtime wiring or new cycle approval |
| 6.9.2f | Collected entry accounting | Accepted: all 15 host cases/flags matched October 31 at 04:57 UTC | Same-ledger acquired delta and paid/held fees; no allocation release or exit integration |
| 6.9.2g | Combined admission evidence recovery | Accepted: 19 actual Kali cases at 05:26:57 UTC October 31; case-list formatter corrected | No active restore or off-machine transfer |
| 6.9.2h | Fresh delayed exit preparation in the admission ledger | Accepted: all 27 host cases at 05:40:57 UTC October 31 | Live evidence collection, restricted exit signing/submission and final reconciliation remain pending |
| 6.9.2i | Bounded admission-owned exit collector | Accepted: all 19 host cases/flags matched October 31 at 06:05:55 UTC | Preserve exact acquired quantity and held commitments |
| 6.9.2j | Atomic collected exit preparation and replay | Accepted: all 21 host cases/flags at 17:39:33 UTC October 31 | Preserve immutable evidence and collection deadline |
| 6.9.2k | Durable exit signer-adapter handoff | Accepted: 21-case host report at 17:55:29 UTC October 31 | Consolidated in PR #66; independent backend host gate and sender remain open |
| 6.9.2l | Independent restricted exit key backend | Accepted: 27-case disposable-key host report matched October 31 at 18:14:04 UTC | No live execution CLI or new controlled cycle approval |
| 6.9.2m | One-send exit transport and bounded recovery | Accepted: 24-case synthetic host report at 18:37:40 UTC October 31 | Full receipt effects and release remain separate gates |
| 6.9.2n | Collected exit receipt accounting | Accepted: all 15 host cases and flags at 18:59:57 UTC October 31 | Original allocation commitments remain held |
| 6.9.2o | Fresh post-exit balance collector | Accepted: 18 host cases and flags exactly replayed November 1 at 07:43:01 UTC | Historical/as-of evidence only |
| 6.9.2p | Durable scoped exit closure | Accepted: 21 host cases and flags exactly replayed November 1 at 08:04:24 UTC | Allocation reuse and live timing remain open |
| 6.9.2q | Unified read-only admission lifecycle | Accepted: all 24 host cases and flags matched November 1 at 10:10:12 UTC | No allocation credit or runtime integration |
| 6.9.2r | Entry admission collection/validation timing | Accepted observation: 19 host cases and one 20-request unsigned run on November 2 | Only 74 ms remaining; no durable admission or signing |
| 6.9.2s | Exact signature replay within timing observation | Accepted: 30 host cases; 1,131 ms remaining on November 2 | Single observation does not establish execution latency |
| 6.9.2t | Isolated durable unsigned admission | Accepted November 2: 22 host cases, 1,754 ms commit headroom and identical read-only recovery | One timing sample; isolated journal is not an operational permit |
| 6.9.2u | Fresh collection to independent signer | Built: 36 targeted local tests, including real disposable-key signing and lost-ack recovery | 17-case synthetic host check; live sender/deadline integration still pending |
| 6.9.3 | Separate-transaction failure recovery integration | Pending | Actual receipt reconciliation, open exposure, independent expiry/fees and stop behavior |
| 7 | Narrow mainnet support | Pending | Engineering work required before any funded mechanics pilot |
| 7.1 | Choose one route and supported token/account types | Pending | Explicit scope; reject unsupported extensions/routes |
| 7.2 | Validate route message, ownership, spending, slippage, rent and fees | Pending | Adversarial offline tests plus current read-only/simulation evidence |
| 7.3 | Safe signer/sender integration and wallet-wide limits | Pending | Durable reservations, loss/exposure limits, stop/recovery and duplicate-send protection |
| 7.4 | Operational rehearsal and deployment/rollback | Pending | Monitor failures and reconcile uncertain outcomes before reuse |
| 8 | Real-money pilot | Not authorized or enabled | Explicitly separate mechanics testing from strategy validation |
| 8.1 | Minimal mechanics pilot design | Pending | Dedicated wallet, explicit small total risk budget, one position, stop rules, supervision and separately agreed scope |
| 8.2 | First funded mechanics test | Pending | Mainnet/operational gates and user authorization; validates execution only |
| 8.3 | Strategy pilot | Pending | Credible prospective economics plus measured execution costs and failure handling |
| 8.4 | Scaling or broader automation | Not scheduled | Requires repeated robust results and operational reliability; never implied by passing devnet tests |

## Immediate sequence

1. The corrected fee observation passed. Preserve the failed and successful reports
   as evidence; the original freshness limit remains unchanged.
2. The live atomic gate and [bounded exit-budget host self-check](BOUNDED-EXIT-BUDGET.md) passed.
   PR #62 consolidated the batch. The [pre-sign admission check](PRE-SIGN-ADMISSION.md) passed on the host.
   The [locked admission check](LOCKED-ADMISSION-BINDING.md) passed. The
   [durable handoff check](DURABLE-SIGNER-HANDOFF.md) passed at 13:30 UTC; PR #63 consolidated this batch.
   The [receipt integration check](ADMISSION-RECEIPT-GATE.md) and
   [restricted signer self-check](RESTRICTED-ADMISSION-SIGNER.md) passed. The
   [submission/receipt self-check](ADMISSION-SUBMISSION-GATE.md) also passed; PR #64
   consolidated the three-increment batch after CI and code review. The new path is
   not deployed. The [entry accounting gate](ADMISSION-ENTRY-ACCOUNTING.md) passed
   its October 31 host check. The [combined private recovery](ADMISSION-RECOVERY.md)
   gate passed 19 actual host cases. The [fresh delayed exit preparation](ADMISSION-EXIT-PREPARATION.md) passed its 27-case host check.
   Live exit collection/signing, receipt accounting and allocation release remain open.
3. Preserve the fixed availability-study captures on the agreed dates. Production
   research collection continues while execution engineering progresses.
4. Review the confirmation on November 6 at 01:05 Amsterdam. A failure-filter result
   may support further research; it does not by itself authorize buying tokens.
5. Continue the narrow mainnet validation and pilot controls when the engineering
   evidence is ready. Do not set a funded-test date just from the number of commits.

## Timeline and confidence

The infrastructure and controlled devnet mechanics have concrete demonstrated
value: they improve observability, reproducibility and failure handling. Their
remaining limitations are explicit. They do not establish a profitable strategy.

The next dated milestone is the November 6 research review. The next engineering
milestone is the fresh collection-to-signing integration, followed by the bounded
entry sender and separate delayed exit lifecycle under the original deadlines.
There is no evidence-based date or success probability for a profitable real-money
pilot yet. Advancing those two tracks in parallel avoids waiting unnecessarily
without confusing engineering progress with economic validation.

## Development rhythm

Local relevant tests first, small development commits, pinned Kali commands where
host behavior matters, and consolidated PR/CI batches around three completed
increments. A source merge does not deploy the scanner. Preserve original studies
and private journals; no test resets them to make an outcome look successful.

References: [roadmap and history](ROADMAP.md), [frozen review decision](FROZEN-REVIEW-DECISION-20261028.md),
[confirmation protocol](../availability-study/README.md), [fee observation](PROJECTED-EXIT-FEE.md).

## October 31 update: first-exit signing handoff

Collected exit preparation passed all 21 host cases at 17:39:33 UTC. The next
internal handoff commits its exact request before calling an injected adapter,
checks returned signatures, and preserves unknown or quarantined states without
automatic re-signing. Both unknown and signed states are covered by private
snapshot replay. The [21-case host exercise](EXIT-SIGNING-HANDOFF.md) passed at 17:55:29 UTC.
The [independent exit key backend](RESTRICTED-EXIT-SIGNER.md) is now built and
host-accepted. The new internal exit sender/collector has a synthetic host gate
pending. Final receipt/allocation reconciliation remains open; no runtime deployment or real-money
approval is implied.
