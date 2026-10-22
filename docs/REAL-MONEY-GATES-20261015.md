# Real-money readiness — 15 October 2026

Status: research infrastructure and the first offline ML benchmark exist. A reliable trading edge has not been demonstrated. Current work is entry-evidence quality and prospective validation. No live order execution is enabled.

## What the six-day study supports

The frozen exploratory logistic baseline was evaluated on chronological, token-disjoint data with an embargo. Test AUC was 0.516 (baseline), 0.493 (early activity), and 0.503 (Fast30): approximately chance-level ranking. Brier improvements were small/inconsistent. Positive selected Fast30 mean depended heavily on one winner, with only seven returned quotes and one failed sell quote in that selected group. Full details are in `research-ml/RESULTS-20261015.md`.

This is evidence against deploying the current selection logic with money. It is not proof that no strategy can work. Faster detection alone has not produced a reliable edge. More features and ML can also fail; neither is a guaranteed solution.

## Planning estimate, not a launch commitment

| Stage | Work and acceptance | Planning estimate |
|---|---|---|
| Consistent entry evidence | Deploy this release; confirm all three groups, valid clocks and no restart/budget regressions | Next engineering/deployment cycle |
| Revised research protocol | Select a small feature set and fixed policy using training data only; freeze costs, missing-data treatment, comparison and acceptance criteria before examining future outcomes | Several days, while collecting |
| Forward evaluation | Evaluate on later days, keep every admitted watch and failed quote, cluster uncertainty by token/day, examine downside and dependence on individual winners | At least 1–2 weeks as an initial review window; extend if coverage is inadequate |
| Execution-only pilot | Build and dry-run bounded execution, manual arming, position reconciliation, restart recovery, balance limits and an independent stop; pass evidence/reliability review | Earliest plausible planning window: 2–4 weeks, conditional on the preceding work |
| Strategy capital | Evidence from actual fills and exits; acceptable net downside and operating failures | No defensible date today |

Two to four weeks from 15 October is approximately 29 October–12 November. This is an optimistic engineering window for a tiny controlled execution test, not a prediction of profitability or authorization to trade. If the strategy still fails forward evaluation, do not fund a strategy trial on schedule. An execution-only experiment answers whether trades can be placed/reconciled; it cannot establish an edge.

Before any funding, agree a separate disposable pilot budget, maximum total loss, position/exposure limits and a supervised session. Validate insufficient balances, unavailable sell routes, stale signals, RPC timeouts, duplicate requests, partial/ambiguous transaction status and restart recovery without real orders first. Stop-loss labels do not guarantee an exit or limit losses in illiquid tokens.

## Confidence and stopping conditions

Confidence is high that the system is useful as a monitoring and research platform: it captures auditable events, distinguishes missing evidence, and has already exposed misleading apparent gains and operating faults. That usefulness does not imply it will repay development costs through trading.

Confidence in the current strategy generating money is low. A probability would be invented from too little, selected data. The observed model performance does not justify a positive claim. Profitability could remain unattainable.

Proceed only when a frozen forward comparison improves on simple/no-model baselines, remains positive after defensible cost and execution assumptions, is not dominated by one token/day, and preserves failure/coverage denominators. Define the exact statistical and downside thresholds before the forward period. If two properly specified forward iterations fail, review the signal/data hypothesis and whether to stop, rather than repeatedly tuning thresholds against the same history.

Next engineering after capture verification: freeze one small richer-feature benchmark and build the dry-run execution/reconciliation harness in parallel. Neither activates trading. No additional cloud downloads are needed.
