# Fixed entry-context comparison 1

The reviewed October 22 freeze is now available privately. Use the [frozen experiment release](../docs/FROZEN-FORWARD-STUDY-UPDATE.md) to install that exact artifact and evaluate multiple later captures. The generic freeze command below documents the mechanism; do not rerun it for this experiment.

This release separates data readiness, model fitting, and later evaluation. It reads original local observer exports or one verified local history capture, rebuilds the validated dataset, and makes no market, cloud, notification or transaction requests. It does not change the scanner or observer. Existing production collection continues without restart.

`protocol.json` fixes the cohorts, entry-only features, two independent targets, model settings, preprocessing, comparisons and minimum evidence guards. The primary horizon is 30 seconds after buy response; 120 seconds is secondary descriptive evidence. Organic/holder receipt ages remain separate from dedicated search age. Missing metadata is not zero; missing or stale security is not a safety approval.

Models compare a training-label-rate constant, logistic regression using the established cohort-specific legacy features, and logistic regression using the supplemental context features. Both logistic variants use this protocol's identical fixed preprocessing, including a missing indicator for every feature. This legacy-feature comparator is not a replay of the earlier benchmark's different preprocessing. The original benchmark remains unchanged.

Two targets are fitted independently per cohort:

- Positive quoted return, conditional on a validated on-time returned quote.
- Exit quote availability: an on-time validated quote versus a provider-reported HTTP 400 quote-generation failure. Transport failures, absent observations, failed buys, interruptions and late quotes remain unknown, with explicit counts.

There is no multiplication into a profitability score. No hyperparameter, feature or threshold search is implemented. A target with insufficient failure examples remains unfitted, even if the return model can be fitted. All fitting uses labels available by the recorded training cutoff, with five minutes between the latest permitted training evidence and model freeze. Minimum training guards are 100 labelled watches, 20 examples per class and three UTC days for each target/cohort. They do not establish statistical sufficiency.

## First step: register the protocol and audit collection

Run from the host project, passing an original **source** export (not the derived dataset):

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/forward-study/run.sh \
  "$PWD/radar-dataset-source-20261016T053120Z-308824.json.gz"
```

This creates a private `radar-forward-protocol-registration.json.gz` once and a new readiness report on each run. Existing registration is reused and its protocol hash checked. The timestamp is local registration, not independent proof of an untouched test set. Preserve the reviewed Git commit and registration file. This command does not fit a model; it needs only Python and the existing repository.

A missing feature is allowed and reported. Old or invalid context/provenance is excluded explicitly. The one-hour upload has only five admitted watches, so it cannot satisfy fitting guards. Do not change the guards just to obtain a model. Repeated/overlapping original exports are deduplicated by the existing immutable evidence builder; conflicting evidence fails.

## Freeze models when training guards are met

Use the isolated research environment from `research-ml/README.md` with the pinned requirements. Do not install research dependencies into the scanner container. For larger windows use the existing bounded local history collector, retaining its capture directory. It performs no Backblaze transfer.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  ~/apps/solana-radar-dev/.venv-research-ml/bin/python \
  ~/apps/solana-radar-dev/forward-study/model.py freeze \
  --history-dir /absolute/path/to/training/capture \
  --registration "$HOME/apps/solana-early-alpha-radar/radar-forward-protocol-registration.json.gz" \
  --output /absolute/path/to/new-model-freeze.json.gz
```

`--source /path/to/original-source.json.gz` can replace `--history-dir`; at most 16 bounded exports are accepted. Output is exclusively created, never overwritten. It stores fixed numeric preprocessing/weights, constant priors, protocol and training identity hashes, source provenance, training-period tokens, cutoff and freeze time. No pickle/joblib or executable model is loaded. Insufficient targets have null models and explicit reasons. `modelFrozen: false` is a collection result, not a deployment problem.

A freeze artifact is a new experiment. Do not repeatedly freeze, evaluate and choose the best outcome while calling it one untouched forward test. A local timestamp cannot prove when a researcher first saw data. Preserve the artifact before acquiring its later evaluation evidence.

## Evaluate later evidence without retraining

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  ~/apps/solana-radar-dev/.venv-research-ml/bin/python \
  ~/apps/solana-radar-dev/forward-study/model.py evaluate \
  --history-dir /absolute/path/to/later/capture \
  --artifact /absolute/path/to/model-freeze.json.gz \
  --output /absolute/path/to/new-forward-comparison.json.gz
```

The evaluator checks artifact integrity and source identity. It excludes pre-freeze/embargo entries and tokens seen in the admitted training period across any cohort. Within each forward cohort, only the first compatible watch per token enters metrics; repeat tokens remain in exclusion counts. Unknown/failed outcomes retain predictions and denominators. Nothing is refitted, and neither outcome labels nor post-entry valuations enter predictors.

Metrics include Brier/log loss, AUC where defined, calibration, paired day-block descriptive uncertainty, all-watch and selected-watch states, return means/medians, severe losses, best-token/day removal, and illustrative 1%/3% additional costs on each side. These stresses are not measured fees or fills. Cost assumptions must never be presented as realized P&L; reported provider fees are not subtracted twice.

At least seven UTC days and 200 valid labels per target/cohort are required before reporting the forward minimum reached. This is not automatic approval. Sparse failures can keep the availability model unresolved much longer. Repeated looks, quota sampling, few days and unknown outcomes limit inference. No model or result enables trading; `liveUseAllowed` remains false.

## Detailed readiness review

`readiness_details.py` and `run-review.sh` replay a bounded historical capture with the existing registration and include descriptive returns, failure transitions, entry-feature ages, actual quote request clocks and guard deficits. They do not fit a model or change the protocol. See [release commands](../docs/READINESS-RECONCILIATION-UPDATE.md).
