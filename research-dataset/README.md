# Research dataset and pricing audit 1.0

An offline development step for evaluating entry conditions and preparing machine-learning experiments. This tool does **not** fit a model, change signals, send notifications, make market requests or trade. Scanner 0.2.9 and observer 0.7.0 continue running unchanged.

## Run on Kali

After checking out the exact reviewed commit supplied in the release message:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/research-dataset/run.sh
```

No installer, rebuild or service restart is required. This reads the observer's retained ledger through its existing export command, then performs analysis as the normal host user. It defaults to the last **24 hours**, publishes a private source export and a private compressed analysis, and prints their paths. Upload `radar-research-dataset-*.json.gz`; retain the source for follow-up. The source exporter may stop at its existing byte/row caps; it never silently samples or publishes a partial export.

The initial 72-hour default exceeded the deployed export cap on October 15. The observer enforces a combined 32 MiB raw-data cap and a 20,000-row cap per table; its generic error does not identify which one was reached. This wrapper keeps those limits intact and accepts an explicit window of 1..72 hours:

```bash
bash ~/apps/solana-radar-dev/research-dataset/run.sh --hours 24
# Only if that export also reaches a cap:
bash ~/apps/solana-radar-dev/research-dataset/run.sh --hours 12
```

The selected window is printed, and no automatic narrowing or partial report is allowed. Three exports of the latest 24 hours taken at the same time do not recover three historical days. For a single consistent capture of retained historical windows, or verified **local** quote-ledger backups, use the new [historical capture instructions](HISTORY.md). The installed observer exporter remains unchanged.

To use already exported files or merge overlapping windows without touching the running service:

```bash
python3 -E -s ~/apps/solana-radar-dev/research-dataset/build.py \
  --input /absolute/path/to/first-source.json.gz \
  --input /absolute/path/to/second-source.json.gz \
  --output /absolute/path/to/new-dataset.json.gz
```

Each input must be an original `quote-observer-report-0.2.0` export, not a derived qualification review. Only reports with the same source identity may be combined. Up to 16 inputs, 64 MiB per decompressed input, 128 MiB total and 20,000 unique signals/probes are accepted. Output has the existing publication byte cap and refuses overwrite. No dependencies beyond the existing checkout and Python standard library are added.

## What is in the report

- **Deduplication:** source identity plus sequence identifies a watch. Immutable entry changes and revised completed quotes fail explicitly. In-progress watches may append unchanged observations. Export window gaps remain visible. Never concatenate report counts by hand.
- **Entry-condition breakdown:** deferred entries are separated into incomplete history, recorded adverse metrics, both, unchanged fields, and other conditions. Flags use the existing qualification rule's price/liquidity deterioration thresholds and negative short-window returns; they do not alter those thresholds. Original qualification state/reason strings were not captured, so this is an evidence breakdown, not a reconstruction of the exact decision. An absence of recorded adverse metrics is not a clean bill of health.
- **Pricing audit:** validates fixed hypothetical quantities and quote clocks, then compares input/output USD valuations in the provider response. Ratios are descriptive accounting identities. A valuation change is not proof of real market movement, and a quote/value difference is not measured execution slippage or fees. The first reverse quote retains its actual delay. Missing platform fee amounts remain unknown.
- **Entry-only dataset:** predictors are an allowlist of immutable entry metrics, availability ages and categorical labels. Token identities, quotes, routes, provider USD valuations and future outcomes are outside the predictor object. Missing fields remain null. No imputation or normalization is fitted on the full dataset.
- **Outcome evidence:** each horizon retains valid quoted returns, failures, missing and late observations. A failed quote is never assigned a zero return. `sellQuoteReturned=0` is reserved for a recorded HTTP 400 quote-generation failure; transport failures stay unknown. This is a provider response label, not proof of unsellability.
- **Feature availability:** recorded counts are broken out by cohort. Field presence is not evidence of freshness, completeness or accuracy.

Provider valuation factors, when all four values are positive and available:

1. Buy output USD value / buy input USD value.
2. Later sell input USD value / buy output USD value.
3. Sell output USD value / sell input USD value.

Their product equals sell output USD value / buy input USD value. This is deliberately separate from the fixed-quantity USDC return. Do not subtract price impact or fees again. Routes can use gross or net amounts differently, and provider valuations can change or be stale.

## Optional chronological split audit

Supply an explicit timezone-aware boundary to inspect a proposed 30-second return dataset:

```bash
python3 -E -s ~/apps/solana-radar-dev/research-dataset/build.py \
  --input /absolute/path/to/source.json.gz \
  --output /absolute/path/to/new-split-audit.json.gz \
  --test-start 2026-10-14T00:00:00Z
```

The timestamp above is a **historical example**, not a registered forward test. Training rows must precede the boundary, their labels must be available before it, and a five-minute boundary embargo applies. Every token occurring in any admitted test cohort is purged from all training cohorts. Cohorts, sampling policies and feature-capture versions have separate audit groups. Only verified entry schemas and on-time validated 30-second returns enter this return-target split; all excluded and failed cases remain in the report.

This split is for a **conditional quoted-return target**, not for estimating the probability of a successful exit. The quote-availability label is exported separately; a future failure model needs its own denominator and validation protocol. Do not train on the `metadata`, identities, `targets` or `pricingAudit` fields, and do not randomly shuffle tokens across train/test.

## Machine-learning decision

It is appropriate to build the offline data and validation foundation now. It is not yet appropriate to replace alert decisions with a model or claim that ML creates an edge.

Start with a small, regularized model such as logistic regression for an explicit target, compared with a constant predictor and the existing fixed rule. Fit preprocessing on training data only. Separate quote availability from conditional return. Evaluate on later dates with token separation; report calibration, class balance, quoted-return distribution, severe losses, missing labels and sensitivity to the best result. A single accuracy score is insufficient.

Before calling an evaluation forward validation, freeze the model, feature list, target, cost assumptions and evaluation protocol before the test period. Inspecting a historical split, choosing a winning rule and then reporting that same split as validation is not acceptable. New features must collect forward evidence; do not enrich historical entries from current token data. Sample counts alone cannot establish readiness, and capacity-limited observation remains nonrandom.

References:
- https://scikit-learn.org/stable/common_pitfalls.html (data leakage and training-only preprocessing)
- https://scikit-learn.org/stable/modules/cross_validation.html (time-dependent and grouped evaluation)

## Replay of the supplied October 14 exports

The 19:53 and 20:39 UTC source exports were merged without changing their contents. There are 135 unique watches, with 126 duplicate watches removed; 3,353 eligible cohort signals remain after deduplication. All three new 0.7.0 watches contain the expected USD pricing fields. Baseline and early activity carry qualification provenance; Fast30 remains unclassified by that rule.

| New watch cohort | Quoted change at 30 seconds | Quoted change at 120 seconds |
| --- | ---: | ---: |
| Baseline | -0.64% | +5.00% |
| Early activity | -23.95% | -57.16% |
| Fast30 | -14.35% | -47.77% |

These three watches verify capture, not strategy quality. Liquidity is recorded for 40/40 baseline watches, 3/48 early-activity watches and 4/47 Fast30 watches across the merged sample. Pooling these cohorts and treating unknowns as zero would hide important data limitations.

The historical example split has only 7 baseline, 7 early-activity and 8 Fast30 training rows. No model was fitted on that small split. The initial 72-hour collection attempt reached an export cap. Use bounded exports and merge retained source files to assess available history; a shorter window does not establish ML readiness.

## Operational scope and rollback

This release only adds offline files and extends repository checks. It does not update the installed scanner or observer, change their request budgets, access wallets or modify Backblaze. Analysis consumes bounded host CPU/memory while running. To stop using it, stop invoking the script; no production rollback is needed. Existing reports are immutable and remain available.

## Supplemental entry context (15 October 2026)

Observer 0.8.0 exports optional `entryContext`. The dataset validates its identity, clocks, missing-value states and numeric bounds into `supplementalEntryContext`, with counts in `supplementalContextCoverage`. Existing `predictors` and model inputs remain unchanged; supplemental fields require a separately frozen future protocol. Source exports containing conflicting context fail validation. Use the coordinated deployment in `../docs/ENTRY-CONTEXT-UPDATE.md` before running this checkout’s exporter. Historical captures remain supported.
