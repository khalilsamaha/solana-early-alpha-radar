# Solana Radar: consolidated direction and development sequence

Version 1.1 — 11 October 2026. Supersedes conflicting recommendations in the uploaded edge plan v1.0. This is the project direction; it does not authorize funding, paid subscriptions or live transactions.

## Objective and present position

Find out whether observable launch characteristics and timely market evidence can select repeatable, realistically enterable and exitable opportunities. Faster alerts alone are not the objective. If the available evidence does not support an edge, do not promote the system to trading.

Hosting, local dashboard, Telegram, availability monitoring, scanner backups and restore checks are established by the supplied host reports. The scanner remains 0.2.9. Research tools, three-cohort walletless quotes and observation-quality evidence are operating. The pool/timing/fixed-exit update was prepared in PR #4; production activation has not been confirmed. This release includes that source change in its guarded installer.

The latest 516-entry Fast30 report has observed mean gross changes of −2.04%, −6.93%, −9.79% and −19.65% at 30, 60, 120 and 300 seconds. Missing and gapped cases remain separate. These are sampled prices, not fills, and do not demonstrate a profitable strategy. Keep existing selection rules frozen while building an independent launch-quality study.

## Decisions adopted from the review

1. Preserve launch evidence before queue admission or eviction; do not treat the current 1,000-candidate queue as the launch population.
2. Record separate event/source and local availability clocks. A feature is eligible only after its response or computation was available to the decision process.
3. Keep provider-reported creator, creation trader, migration actor and verified authorities distinct. Same-slot or shared-funder evidence is a flag, not proof of insider activity.
4. Separate price collapse, unavailable exit quote, provider failure, pool change, missing data and verified liquidity withdrawal. Never label every failed quote a rug.
5. Test exit quotes for the fixed hypothetical quantity obtained at the intended buy notional. A dust route does not establish exit availability at another size. A quote is not a fill.
6. Measure quoted changes separately from modeled costs. Avoid counting price impact, embedded fees or priority tips twice. Additional proceeds haircuts are stress assumptions, not measured fees or exact net returns.
7. Curve reconstruction requires ordered state, correct instruction version, fee rules, integer units and rounding; it cannot guarantee counterfactual transaction inclusion. Estimated block timestamps are not precise transaction arrival clocks.
8. Retain all selected, excluded, unknown, failed and pending denominators. A matured unresolved exit after a modeled buy may receive a total-loss stress scenario, separately labeled; do not apply it to pending paths or unsuccessful buys.
9. Use immutable protocol versions, entry-time feature snapshots and distinct exploratory/forward periods. Deduplicate source identity plus sequence. Model mint/creator/time dependence and label unknown identity.
10. A better result than a losing control is not sufficient. Positive medians alone do not establish an edge when tail losses dominate.

## Work sequence and decision gates

| Sequence | Deliverable | Decision unlocked |
| --- | --- | --- |
| A: evidence foundation | Guarded combined source update; quote-ledger snapshot and isolated restore; optional verified B2 round trip; bounded durable launch registry and availability audit | Which features actually exist, and whether their evidence survives eviction and recovery |
| B: small launch-feature study | As-of joins from registered launches to existing entry records; missingness and creator-role audit; limited hypotheses with a frozen comparison plan | Whether launch information adds useful selection evidence beyond momentum |
| C: prospective execution comparison | Register chosen candidate rules, notional, costs, primary exit, sampling design and stopping criteria before new validation observations | Whether a candidate survives forward evaluation with quote failures, delays and realistic costs |
| D: execution engineering | Independent signer boundary, action/amount caps, simulation, idempotency, signature reconciliation, restart recovery and exit handling | Whether bounded execution is operationally testable |
| E: explicitly approved funded pilot | Fixed loss budget, small position size, maximum exposure, entry and exit controls, no unattended expansion | Whether actual fills and costs agree sufficiently with the tested assumptions |

Sequence A is implemented in this release. B and C require host evidence and a subsequent code change; no creator score or new production admission rule is added here. Gaps in those features are an answer, not a reason to manufacture history.

### Sequence B: first study, deliberately small

Start with features that are truly available in received create events: signature presence, distinct creator/trader roles, provider-reported initial buy/amount/reserves and an equality-only metadata URI hash. Audit missingness and units before computing ratios. A URI hash is not content verification. Current raw creation quantity fields are reported values, not inferred token decimals or executable prices.

A separate future as-of feature snapshot may count earlier locally observed creations from a reported actor. It must exclude the current and later launches, declare the bounded lookback and distinguish unknown from zero. Previous-launch outcomes must have matured and been observed before the new decision. Do not compute a retrospective creator reputation and attach it to older entries.

Limit the first study to a few declared hypotheses. Examples to investigate, not rules to activate: whether prior locally observed launch frequency adds information; whether adequately specified initial participation improves outcomes; whether launch information changes the behavior of the current known-liquidity subset. Never assume liquidity or actor identity is known just because a field exists.

Use chronological discovery/validation splits, group-aware analysis, and purge overlapping outcome windows. Keep the effective number of independent creators/mints/time blocks visible. Show outlier sensitivity and missing-data stress. Retain negative findings and record how many hypotheses were explored.

### Sequence C: protocol to freeze before a strategy trial

Specify the exact buy notional, quote route model, primary horizon and decision-to-request clock. The prepared fixed-short-exits-1 evidence protocol uses 30 seconds after buy response as the primary observation, with 60/120 seconds as comparators and a five-second lateness boundary. It is an evidence protocol, not a selected trading strategy. A launch-feature strategy needs its own registration and cost model.

Choose sample targets using observed dispersion, dependence and acceptable uncertainty, not launch volume alone. At present each quote cohort admits at most 48 watches/day, with 144/day across three different cohorts. Fourteen days permits at most 672 watches for one cohort; 2,178 observations would require roughly 45 days even at full capacity. These arithmetic ceilings are not sample-size guarantees. Three complete weekly blocks require at least 21 days.

Current first-eligible arrival after spacing is not random sampling. Use full selected coverage within a defined capacity envelope, or design prospective probability sampling with auditable inclusion/exclusion and busy-period handling. Version it separately and preserve the existing observations. Do not infer skipped-signal returns from admitted signals.

A candidate advances only after a prespecified forward assessment supports positive modeled outcomes under stated costs, acceptable tail loss and exit-failure rates, and robustness across independent periods. Confidence level, multiple-hypothesis treatment, absolute target and control comparison must be set before the trial. Small exploratory samples or an interval merely above −2% are not live promotion gates.

## Optional research lanes

Trade-level feed feasibility: bounded provider capability and cost review, then a separately authorized event/request budget. Creation/migration feeds remain the only PumpPortal subscriptions in this release. Compare same-signature local receipt timing across sources; do not measure subsecond advantage from whole-second estimated block times.

Wallet research: defer until historical coverage, realized PnL accounting and copyability delays can be established. Treat same-slot/shared-funder associations as uncertain. A trader's observed success does not show that following them later is profitable.

Slower graduated markets: consider as a separate preregistered lane if very early launches remain unfavorable. Do not mix holding horizons and select the best retrospectively.

Risk-screen product: possible independent direction, with its own false-positive and missed-risk evaluation. Absence of a known risk flag is not a safety guarantee.

## Engineering and deployment constraints

Use pinned GitHub commits, guarded installers, source backups and explicit rollback. GitHub and the development checkout do not access the live Kali database. Keep keys, .env, databases and reports out of Git.

The launch registry is a separate indexed table in the existing radar.sqlite so the established whole-database backup includes it. It is not loaded into the active candidate map. This avoids introducing another unprotected database. There is one bounded row per retained mint, 30-day age retention, a 100,000-row hard cap and at most 500 expired rows pruned per minute while creations arrive. A row cap stops capture rather than silently replacing recent evidence; health counters disclose drops. Idle expired rows are removed gradually on subsequent traffic. Database file allocation need not shrink after deletion.

Capture adds a short SQLite transaction for a creation message, not a write on every market poll. Audit reports have read/time/byte budgets. Measure actual I/O and resource impact after deployment; no claim of zero overhead. A disconnected feed or rejected event cannot be retrospectively recovered by this release.

The separate observer backup retains the complete ledger, cursor, registrations and failure evidence. Isolated restore verification never runs the observer or sends quotes. Actual disaster recovery must reconcile scanner source identity before restarting; do not silently rewrite cursors to make mismatched sources appear compatible. Local retention is 14 completed archives. B2 quote archives are not automatically deleted; review cloud growth before setting a dedicated prefix lifecycle rule. This new timer does not yet have its own external failure notification.

For any future executor, fail closed on new entries when uncertain, while preserving an explicitly designed reconciliation/exit policy for existing positions. Stopping every action indiscriminately can leave open exposure unmanaged. No funded pilot or wallet integration is authorized by this document.

## Assessment cadence

After deployment, validate readiness, registry version, counters and one complete local/cloud backup. A short availability audit can immediately reveal missing fields and schema mistakes; no arbitrary overnight wait is necessary for correctness.

After enough received creations to characterize availability, select the first study and its fixed evidence requirements. Continue automated collection during development. Review the strategy only at preregistered checkpoints, not whenever a recent winner makes a rule look attractive. Calendar duration supports coverage; it is not proof of an edge.

## Technical references reviewed

- PumpPortal data and fees: https://pumpportal.fun/data-api/real-time/ and https://pumpportal.fun/fees/
- Jupiter walletless order, slippage tolerance and fee fields: https://developers.jup.ag/docs/api-reference/swap/order
- Solana estimated block production time: https://solana.com/docs/rpc/http/getblocktime
- Pump instruction versions: https://github.com/pump-fun/pump-public-docs/blob/main/docs/instructions/TRADE_V3.md

These references explain capabilities and interpretation; no provider calls are made by this plan.
