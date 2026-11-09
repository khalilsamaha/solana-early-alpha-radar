# Solana Radar: independent review and working agenda

Date: 8 November 2026. Calendar dates use Europe/Amsterdam (CET).
Reviewed source: `e62e2f26f8ea03bac123c774a2d8f224383e9c0e` (PR #79).
This agenda replaces the ordering and forecasts in the earlier November 8
timeline. Historical protocols, evidence, safety limits and failed observations
remain unchanged. This is a planning record, not an execution or spending permit.

## 1. Decision

Research is the primary path to a trading-product decision. Preserve the working
scanner and observer, establish their actual current evidence quality, and test
one defensible hypothesis. Finish or explicitly block the current bounded devnet
exit/closure task; do not expand generic execution infrastructure indefinitely.
Reuse the existing reporting and protocol machinery after verifying compatibility.
New feeds and reconstruction are conditional investments, not automatic projects.

The system is an implemented monitoring/research platform with substantial
controlled-devnet safeguards. It is not a validated profitable strategy or a
mainnet trading service. No percentage-complete estimate would be meaningful
across those different objectives.

## 2. Review scope and evidence strength

This is a project-level architecture, implementation-boundary, evidence and
delivery review. It is not an exhaustive line-by-line security audit or a fresh
inspection of the running Kali host. Current host health, installed versions,
retained data and operational private journals require new host evidence.

Reviewed the scanner and observer contracts and relevant implementations;
launch registry/reporting and dataset joins; research/forward/availability
protocols and tests; signer/submission and accounting/closure boundaries;
operational reporting, backups, retention, wrappers, manifests and both CI
workflows. Historical study conclusions were checked against committed decisions,
not newly recomputed from private raw quote captures unavailable in this workspace.

Independently checked during this review:

- GitHub main remains at the reviewed merge; post-merge run 42466480821 is
  completed/success on that exact SHA. All 12 jobs were verified in the completed
  consolidation. The full regression suite was not rerun for this documentation.
- Re-read the supplied execution/profile reports and their compressed hashes.
  The full accepted report is `offline-integration-passed`, 42 checks,
  11,889.065 ms and 1,343 ms headroom; earlier failures remain evidence.
- Source hygiene and immutable package manifests passed; both partition tests
  passed. Research packages match the pinned numpy/scipy/scikit-learn versions.
- Ran 55 offline research regressions: research-ml 12, forward model 10,
  experiment 7, failure audit 10, availability confirmation 16; all passed.
  These used synthetic/temp evidence and did not register a real experiment.

The supplied full execution report has version markers but no self-contained Git
SHA attestation. Its source attribution rests on the pinned command and adjacent
clean profile, as already documented. Future report provenance should include
revision, tracked-change state, runtime versions and relevant protocol hashes.
None is an independent attestation of provider truth or a clean machine.

## 3. Capability assessment

| Component | Established functionality | Remaining limit or gate |
|---|---|---|
| Scanner | Bounded discovery/enrichment, freshness checks, heuristic score, dashboard, notification outbox, price observations | Live configuration/health must be refreshed; heuristic scores are not calibrated profit probabilities |
| Launch registry | Creation receipts before queue eviction; trader/creator roles separate; URI hashes; bounded prior-launch reporting | 30-day retention, 100,000-row cap; capture drops at capacity; no complete chain history or guaranteed creator identity |
| Quote observer | Walletless entry/exit observations at fixed quantities, source identity, failure/unknown denominators | Nonrandom first-eligible admission, one active watch, 48/day/cohort and 144/day overall, 7-day retention |
| Research | Entry-time dataset, immutable registrations/artifacts, chronological exclusions, replay, descriptive uncertainty | No demonstrated economic edge; old holdouts are closed; prospective capacity and dependence must be designed anew |
| Devnet mechanics | Historical controlled cycles plus separate signing, one-send, recovery, receipt and closure building blocks | Current successor operational timing, exact receipt/accounting integration and actual closure remain outstanding |
| Offline successor | Accepted 42-check composition, stopped/keyless recovery, preserved holds and history | Synthetic network; narrow and variable timing; not a general entry or round-trip latency benchmark |
| Mainnet execution | Read-only scanner/quote access exists | No supported operational mainnet swap path; real route/account/token semantics require separate validation |
| Risk screen | Authorities, extensions, concentration and deterioration heuristics provide reusable inputs | Discrimination, false exclusions, completeness, freshness and practical usefulness need evaluation |

The completed frozen review did not justify model promotion. Its 30s returned
quote means were -2.62%, -8.79% and -4.55% for baseline/early/Fast30 respectively.
The completed availability study is insufficient (15 excluded labels against 20),
with selected returned quotes averaging -7.18% at 30s and -13.89% at 120s.
These are conditional quote observations, not fills or failure-adjusted net P&L.

## 4. Findings that change the next work

1. **Current-state documentation is fragmented.** README/roadmap/review paragraphs
   retain old pending states and superseded consolidation references. This agenda
   is the current entry point; keep historical evidence but clearly label it.
2. **One wrapper uses an old installed path.** `launch-study/run-joined.sh` calls
   observer `0.6.0`; source and `research-dataset/run.sh` use `0.9.0`. Verify actual
   installation and source/schema compatibility before correcting the wrapper.
   This is a source mismatch, not a demonstrated host failure. No silent fallback.
3. **Research pushes currently trigger CI.** `.github/workflows/research-ml.yml`
   has path-filtered pushes without a main-branch restriction. General regression
   pushes are main-only. Align research triggers before pushing research changes,
   so implementation publication does not precede Kali acceptance with CI.
4. **Operational status includes old experiment-age warnings.** The operational
   reporter treats the closed frozen study's last capture as continuously aging.
   Interpret closed-study preservation separately from active collection health;
   do not extend a closed study merely to clear a warning. Verify integrity first.
5. **Retention and capture caps can invalidate a longer new study.** Verify backup
   coverage and retrieval; design versioned bounded incremental preservation for
   the new interval. Do not expand or rewrite the old study's immutable protocol.
6. **Mainnet parity is substantial work.** Existing accounting has deliberately
   narrow standard-SPL, fixed-account, fee/rent and inventory assumptions. WSOL,
   account creation/closure, ALTs, extensions and actual router semantics must be
   supported explicitly or excluded for the selected route.
7. **Current sample capacity is partly internal policy.** A paid provider tier
   alone does not lift admission spacing, concurrency, per-cohort budgets or
   selected/control sampling constraints.

## 5. Comparison with the developer's v2.0 plan

Input: uploaded `Pasted text.txt`, SHA-256
`118d84f5e4d9d3dd1aad55bdd0742ba3dd97a245b95c03657b7d6fa8275628fb`.

| Proposal | Decision in this agenda |
|---|---|
| Research first; bounded devnet completion | Adopt; initial baseline audit first, then bounded closure work alongside research |
| Closed studies remain closed | Adopt without exception; insufficient and negative are distinct |
| Freeze generic execution layers | Adopt; permit fixes necessary for current exposure/recovery and required workflow compliance |
| Infer strategy horizon from the 11.9s benchmark | Reject that inference; measure actual stages for the selected strategy/route |
| Immediately build a trade-level reconstruction system | Make conditional on a narrow feasibility and value-of-information decision |
| Free/exact/unlimited reconstructed execution | Reject; use versioned, coverage-limited counterfactual simulation with explicit assumptions |
| Creator/security/funder at creation time | Correct to actual local availability time and verified role; retain unknowns |
| Holder ownership and realized wallet P&L from trade ticks | Require transfer/history coverage; label partial observed activity honestly |
| Wallet and slower-horizon lanes in parallel | Defer; choose at most one alternative if the primary hypothesis is not defensible |
| Risk screen as guaranteed-value fallback | Retain as an independently evaluated product hypothesis; no guarantee |
| 14-day window plus three weekly blocks | Correct: at least 21 complete days if three nonoverlapping weekly blocks remain a gate |
| Approximately 2,000 entries | Illustrative only; specify effect, variance, power, dependence, control and multiplicity before freezing |
| G1 bound above -2% | Discovery screen only, never a trading or positive-edge acceptance criterion |
| Dec 31 and late-Jan/Feb checkpoints | Retain Dec 31 as a scope/budget decision; derive final evaluation dates from coverage, not the calendar |
| Funded mechanics distinct from strategy pilot | Adopt; both need their own operational scope and explicit owner authorization |

Current provider documentation reviewed on November 8 describes metered
PumpPortal trade subscriptions, unlike free creation/migration subscriptions.
No paid service, wallet funding or trial is approved by this agenda. Solana allows
unsigned simulation with signature verification disabled, but simulation is not
landing evidence and provider usage may incur costs. Recheck schedules and
supported protocol versions before choosing a provider.

## 6. Calendar and workload assumptions

Targets assume one engineering stream with about four focused working days per
week (roughly 24-32 hours), including tests, reports and consolidation, plus Kali
feedback normally within 24-48 hours. This is a planning assumption, not confirmed
owner availability or a promise of unattended background work. Lower capacity,
holidays, host delays, new data requirements and failed gates move dependent dates.
Tasks listed in the same fortnight share that capacity; they are not two full-time
developers. No additional research lanes are silently added to fill waiting time.

Dates govern reviews and allocation of effort. Acceptance is always evidence-based.
Record any move with its cause, changed dependency and next dated checkpoint.

| Window (2026 unless noted) | Priority and concrete output | Acceptance / decision |
|---|---|---|
| Nov 9-13 | B0: current host inventory, reporting compatibility, daily counts/coverage, retention/restore status, workflow correction specification | Source/runtime identity known; blockers classified; replayable baseline and measured collection-rate table, or explicit missing evidence |
| Nov 9-20, after initial inventory | E0: bounded current devnet successor/closure task, maximum five focused engineering days in this fortnight | Complete operational evidence and idempotent closure, or a written blocker with held state preserved; Nov 20 is a checkpoint, not forced completion |
| Nov 16-27 | B1: audit existing launch/quote evidence; choose one hypothesis/universe/horizon; cost/sampling/preservation design | A feasible research protocol and sample forecast, or a reasoned no-go; no new model/filter deployment |
| Nov 30-Dec 4 | Conditional R1 feasibility only if essential missing evidence justifies it; otherwise build/test the minimal study using existing data | Written feed/coverage/cost decision; no paid activation without approval; avoid a broad new platform |
| Dec 7-18 | Existing-data branch: bounded discovery analysis and held-out check; new-feed branch: capture/reconstruction engineering | Candidate evidence report with limitations, or implementation/coverage status; this date does not promise G1 |
| Dec 21-31 | C1: assess G1, preservation readiness and study feasibility; freeze/register R7 only if all prerequisite checks pass | Proceed with one frozen prospective trial, choose one separately justified alternative, or pause alpha work; insufficient stays insufficient |
| 2027, after valid R7 registration | Fresh prospective collection; coverage-only interim reporting | Fixed end and minimum sample/dependence guards; normally multiple weeks, potentially months |
| After R7 ends and labels mature | C2/G2: reproducible final evaluation and decision | Positive modeled evidence under the preregistered tests, negative evidence, or insufficient evidence |
| Conditional after credible G1 | E2: selected-route mainnet read-only parity and mechanics specification | Explicit supported instruction/account scope and simulated effects; no signing or broadcasting |
| After G2 and operational readiness under this chosen ordering | E3: separately authorized bounded funded mechanics test | Actual fills, costs, failures and settlement satisfy registered tolerances; no profit claim |
| Only after G2 and E3 pass | E4: separately authorized strategy pilot | Budget, wallet, limits, exposure monitoring and stop/recovery scope accepted; no fixed launch date |

If R1 requires a new reliable feed, allow approximately 3-6 additional focused
engineering weeks after feasibility for bounded capture, reconstruction and
validation, with fresh observation time potentially extending that. That branch
can move G1 into January or later. Do not promise December G1 on both branches.
January mechanics/February pilot are optimistic scenarios only. Under this agenda
funded mechanics waits for G2, avoiding expenditure without a sufficiently
supported hypothesis; it remains a distinct experiment if eventually authorized.

## 7. B0 — baseline inventory and capacity gate

First establish the host, not just repository assumptions:

- Actual scanner/observer versions and source identities, configuration and sample
  policy; readiness, recent provider/loop clocks, resource/disk usage and drops.
- Scanner and quote-ledger local/cloud status, age and recoverability; distinguish
  reading a status file from a new isolated restore or off-machine verification.
- Launch registry span/count, cap drops and missing creator/trader/reserve/unit
  fields. Current chain lookups cannot populate historical as-of predictors.
- Bounded original exports/backups: eligible signals, admission/skip reasons,
  buy responses, on-time exits, provider failures, missing/pending outcomes and
  unique mint/actor counts per day, cohort and source version.
- Available history and its gaps; do not combine incompatible versions or infer
  unquoted returns. Old studies can guide discovery, never become fresh validation.
- New-study preservation: retention, request/row/byte/disk limits, capture schedule,
  hashing, overlap de-duplication, manifest integrity and restoration checks.

Begin with the existing read-only operational report from the reviewed checkout.
Its closed-study age findings need interpretation as described above. Verify the
installed observer before selecting launch/quote export commands. Adapt only the
reporting code required for this gate, test it locally, then provide a pinned
fetch/checkout/run command for Kali. A report failure is a blocker to diagnose,
not grounds to lift caps, change source identity or silently shrink the window.

B0 is complete when the evidence can be replayed, relevant current source versions
are known, hard collection/backup failures are resolved or explicitly bound the
permitted scope, and the rate table supports a realistic next-study design.

## 8. E0 — finish the current bounded devnet responsibility

Inventory the actual held state read-only. Separate safe observation, synthetic
acceptance and an operational attempt. Reuse the existing successor, receipt,
balance and closure contracts; extend only the exact missing successor binding.

Completion requires all of:

1. Required local and Kali offline tests for any change, with runtime/source identity.
2. Real-provider observations within original freshness and request budgets;
   measure stage timings without treating a single pass as a latency distribution.
3. A separately authorized, exactly scoped devnet action when the operator chooses
   to run it. This planning request is not that authorization.
4. Exact original signature/message, finalized token/native fee effects, fresh
   residual and protected balances, durable scoped closure and idempotent recovery.
5. Interrupted/unknown paths preserve holds and permit only the designed recovery;
   no retry, re-sign, reset or new generation is inferred from elapsed time.
6. Whole completed engineering-phase consolidation and post-merge verification.

By Nov 20, publish accepted evidence or a precise blocker and preservation/recovery
plan. Additional execution engineering needs a specific necessity and revised
estimate. Do not abandon monitoring of unresolved exposure, erase history, widen
freshness or call an unknown balance zero to satisfy the time box.

## 9. B1 / R1 / G1 — choose the smallest informative study

Begin with the existing as-of creation-trader and URI-hash features and compatible
quotes. Test whether coverage permits any defensible candidate before requesting
new feeds. Declare at most three primary discovery hypotheses; record all
exploration and comparisons. Select a simple rule only if held-out evidence
justifies prospective evaluation. A new complex model is not the default.

If critical features are unavailable, write down the exact question a feed would
resolve, expected eligible events/day and maximum effort/cost. A 3-5-day feasibility
spike should establish accessible fields, version/fee semantics, within-slot event
identity/order, reconnect/gap/fork handling, receipt clocks, subscriptions and
storage/backup impact. Evaluate paid offerings without activating them. Proceed
only after a capped acquisition scope is approved where spending is involved.

Reconstruction must separate observed state from hypothetical execution. Validate
amounts and fee effects at intended size against compatible state/simulation and
quotes, with predeclared tolerances and coverage exclusions. Quote disagreement
can reflect route/state timing differences; quotes are not independent ground
truth. Multiple delays on the same token do not create independent samples.
Unobserved transfers prevent complete wallet/holder accounting from trade ticks.

Use actual feature availability clocks, not just event timestamps. Identify
creator/trader/fee-recipient/funder roles separately and keep uncertain relations
as flags. Migration ends an unsupported reconstructed path with an explicit
denominator; it must not silently remove successful or failed tokens.

G1 is permission to invest in a fresh trial, not proof of positive economics.
Before held-out analysis, fix target notional, primary horizon, route/universe,
cost model, downside/coverage criteria, splitting/purging and hypotheses explored.
The developer's 300-entry/90%/-2% limits are unapproved proposals, not existing
project acceptance thresholds. Finalize numerical gates before inspecting their
validation outcomes. Assess tail loss, missingness and best-token/day sensitivity.

## 10. R7 / G2 — prospective evaluation contract

Freeze code/config/protocol hashes, selected rule, comparator, source versions,
eligible population, notional, decision clock, cost version, sampling probability,
calendar span, sample guards, maturity, coverage, primary statistic and multiplicity
treatment before new validation observations. Validate the capture and evaluator
offline and on Kali before the trial starts. No mid-window improvement to selection.

Model costs at the intended size: embedded fees/impact once, additional network/
priority/tip costs as applicable, account funding/rent separately from irrecoverable
expense, failed-attempt fees, and conservative unresolved-exit stress. Preserve
pending paths and failed buys as their own states. Quote/reconstruction returns
are modeled, not realized cash returns.

Primary gate: positive absolute modeled net economics AND superiority over the
registered control under prespecified confidence, downside and coverage criteria.
A better result than a losing control is insufficient. Specify whether confidence
is one/two-sided, clustering scheme, effective sample and minimum independent time
blocks. At least 21 complete days if retaining three weekly blocks; this is a floor,
not a guarantee of reliable tail or clustered inference.

Size with observed eligible/selected/control arrival rates, outcome availability
and dependence. If using the developer's illustrative target of 2,000:

| Effective usable selected observations/day (illustration) | Days for 2,000 |
|---:|---:|
| 48 | 42 |
| 24 | 84 |
| 12 | 167 |

The 48/day row is already an ideal per-cohort admission ceiling, not a measured
independent selected rate. Controls, outages, exclusions and clustering can reduce
it. Approximately 2,181 iid observations correspond to a 3-percentage-point mean
effect, 50% standard deviation, 80% power and a two-sided 5% one-sample test; this
does not power a clustered, multiple-hypothesis or two-arm experiment automatically.

Set a fixed end plus maturity and minimum guards from B0. Weekly interim reports
show capture health/counts only, unless a valid sequential outcome-review design
was registered. Do not keep extending until the result becomes positive. An
insufficient study remains closed/insufficient; any new protocol gets fresh data.

## 11. Mainnet, pilot and alternative tracks

After credible G1, route-specific unsigned parity may be prepared without signing.
It is a bounded evidence task, not a general executor redesign. Account-state and
balance prerequisites for simulation must be explicit; unsigned simulation neither
funds an account nor proves admission/landing. Select supported token extensions,
message/ALT formats and router semantics explicitly; deny unknown functionality.

E3 requires a separately approved dedicated wallet, finite disposable budget,
maximum total loss, exact actions, supervised session, hard caps and measured
recovery. Include both legs, failed landing/selling and exact reconciliation.
E3 tolerances and sample adequacy must be agreed in advance; a handful of successes
does not establish a rare failure rate. Re-evaluate economics against measured costs.

E4 additionally requires G2 and operational controls for the selected scope:
new-entry stop, controlled existing-position recovery/exit, exposure and loss caps,
one-attempt semantics, on-chain reconciliation, audit records and explicit pilot
approval. Existing offline/cumulative limits must not be misdescribed as deployed
wallet-wide daily-loss enforcement. Never automatically top up or scale a pilot.

Wallet intelligence and slower-horizon strategies stay deferred. If the primary
lane is infeasible or fails, choose at most one justified alternative with its own
data and protocol. Do not infer slower-horizon suitability solely from 11.9s.
A risk-screen product remains a separate hypothesis: validate false exclusions,
missed risks, freshness/unknowns and usefulness. A successful dust quote, high AUC
or lack of risk flags is not a safety certification or proof of product demand.

## 12. Delivery discipline and review cadence

- Local implementation and relevant offline tests; pinned development publication
  only when necessary for Kali. No PR/CI/consolidation before the full agreed gate
  or engineering phase is accepted on Kali. Do not use a fixed count of increments
  as a substitute for completion of that phase.
- Then complete applicable full regression (including separate research suites),
  review, PR, all required CI on the final head, merge and post-merge verification.
- A source push or merge is not deployment. Preserve the existing host project,
  Compose identity, configuration and database volumes. Install only through an
  explicit tested release/rollback procedure where needed.
- Every host instruction includes fetch/commit verification, the correct separate
  development path, exact run command, output filename and acceptance criteria.
- Each checkpoint records gate ID, source/protocol identities, evidence hashes,
  passed/failed/not-run cases, runtime, external effects, decision and next action.
- Use complete / blocked / insufficient / failed / deferred distinctly. No status
  changes based solely on elapsed days, code volume, a synthetic pass or one AUC.
- Review progress each Friday when work resumes in chat, and after each host report.
  Record completed evidence, blockers and next-week scope. No automatic reminder or
  background job has been created by this agenda.
- C1 on Dec 31 is an owner scope/budget decision, not a forced statistical verdict.
  Two properly specified negative prospective iterations trigger a stop/strategy
  review; they do not authorize endless retuning. Insufficient iterations consume
  time/budget and also require review, but are not relabeled negative evidence.

## 13. Owner inputs and default boundaries

Immediate baseline work requires no new spending or funding. Before a paid feed,
new validation registration or operational action, collect only the decisions
relevant to that step: available engineering/host time, acceptable horizon,
data budget, target notional and numerical statistical/downside limits. Capital
budget, maximum total loss, wallet and actions are required separately before E3/E4.
No arbitrary amount or tolerance in this document is an approved capital limit.

## 14. Source map

- [Developer's prior direction](EDGE-RESEARCH-PLAN.md), [project review](PROJECT-REVIEW-20261107.md), [historical timeline](PROJECT-TIMELINE-20261108.md).
- [Frozen decision](FROZEN-REVIEW-DECISION-20261028.md), [availability closure](EXIT-RPC-SESSION-20261106.md), [availability protocol](../availability-study/protocol.json).
- [Launch study](LAUNCH-STUDY.md), [joined report](LAUNCH-QUOTE-UPDATE.md), [registry source](../scanner/src/core/launch-registry.js), [entry clocks](../scanner/src/core/entry-context.js).
- [Observer policy/source](../quote-observer/observer.mjs), [dataset](../research-dataset/README.md), [research dependencies](../research-ml/requirements.txt).
- [Successor consolidation](SUCCESSOR-CONSOLIDATION-20261108.md), [composition](../position-book/successor_execution.py), [closure](EXIT-CLOSURE.md), [lifecycle](ADMISSION-LIFECYCLE.md).
- [Operational report](../operational-review/operational.py), [development workflow](DEVELOPMENT.md), [general CI](../.github/workflows/tests.yml), [research CI](../.github/workflows/research-ml.yml).
- [PR #79](https://github.com/khalilsamaha/solana-early-alpha-radar/pull/79), [accepted post-merge CI](https://github.com/khalilsamaha/solana-early-alpha-radar/actions/runs/42466480821).
- Provider references reviewed November 8: [PumpPortal data](https://pumpportal.fun/data-api/real-time/), [Pump instruction versions](https://github.com/pump-fun/pump-public-docs/blob/main/docs/instructions/TRADE_V3.md), [Solana simulation](https://solana.com/docs/rpc/http/simulatetransaction).

## 15. First Kali evidence request — existing source only

This command uses the already merged source, not a new implementation or a study
registration. It updates only the separate development checkout, reads local host
status and writes a public report. It makes no market/cloud request, evaluates no
model, changes no service and sends no transaction. It requires the existing
development checkout and refuses to switch it when the worktree is dirty.

```bash
bash <<'SH'
set -euo pipefail
umask 077
radar_dev="$HOME/apps/solana-radar-dev"
radar_live="$HOME/apps/solana-early-alpha-radar"
radar_revision=e62e2f26f8ea03bac123c774a2d8f224383e9c0e
test -d "$radar_dev"
test -d "$radar_live"
if [ -n "$(git -C "$radar_dev" status --porcelain)" ]; then
  echo 'Development checkout has local changes; preserve them and report this before switching.' >&2
  exit 1
fi
git -C "$radar_dev" fetch origin main
git -C "$radar_dev" checkout --detach "$radar_revision"
test "$(git -C "$radar_dev" rev-parse HEAD)" = "$radar_revision"
test -f "$radar_dev/operational-review/run.sh"
cd "$radar_live"
bash "$radar_dev/operational-review/run.sh"
SH
```

Upload the printed `radar-operational-review-*.json.gz`. Do not upload `.env`,
keys or private journals. `attention-required` is a diagnostic outcome, not a
reason to reset anything. The closed-study 48-hour warning is expected to need
interpretation; the next review separates that historical condition from actual
scanner/provider/backup faults. This initial report does not supply the full B0
rate table, verify cloud restoration or clear E0. Follow-up exports are selected
only after installed observer compatibility is known.
