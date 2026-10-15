# Offline ML baseline 1

This is an exploratory, retrospective benchmark, not a trading model deployment. It reads one or two verified historical capture directories, rebuilds their datasets from the original quote records, fits small cohort-specific classifiers, and publishes a private JSON report. It has no wallet, provider, notification, service-install or cloud code. No pickle/joblib model is written or loaded.

## Fixed first experiment

The first six-day experiment uses October 9–15, 2026 evidence with an explicit test boundary of **2026-10-13T08:32:43.912Z**: the first four days precede the test period and the last two days follow it. Historical aggregate outcomes were inspected before this experiment; this is not a previously untouched forward test. No hyperparameter, feature or threshold search is performed.

The only sampling policy fitted is `three-cohort-budgets-v3`. Baseline/early activity require verified `entry-features-1`; Fast30 requires verified `fast-entry-features-1`. Older policies and missing entry provenance remain in the exclusion counts. Model groups never mix cohorts.

| Cohort | Fixed predictors |
| --- | --- |
| Baseline | Liquidity, organic score, top-10 account concentration, 30-second price change |
| Early activity | 30-second and 60-second price change, latest-interval price change, average reported trade size |
| Fast30 | 30-second price change, latest-interval price change, liquidity |

The target is whether the validated, on-time fixed-quantity USDC quote return at 30 seconds after the buy response is positive. This is **conditional on a quote being returned**, not the probability of a successful real trade. Fees and execution are not inferred. No current token enrichment or post-entry valuation is used as a feature.

All cohorts use L2 logistic regression (`C=0.1`, `lbfgs`, maximum 1,000 iterations, no class weighting). Dollar amounts and return features use fixed signed `log1p` transforms. Median imputation, missing indicators and scaling are fitted only on training rows. A probability threshold of 0.5 is fixed before the run. Training needs at least 50 rows and 10 examples of each class; at least 20 valid test labels are required. These are engineering fit guards, not evidence of statistical sufficiency.

The split excludes five minutes on **each** side of the boundary. All tokens present in any admitted test cohort are purged from training across cohorts. Training labels must have been available before the boundary. Test failures and missing/late outcomes remain in the prediction report and selected-case denominators; they are not assigned zero returns or losses.

## Evaluation

- Compare logistic probabilities against the training positive-rate constant using Brier score and log loss (lower is better), plus ROC AUC when both classes exist.
- Show accuracy, coarse calibration bins with counts, and daily results. Accuracy alone can reward always predicting the common class.
- Report all compatible test watches, model-selected watches, failures, validated quoted returns, mean/median, loss-at-least-50% count and mean with the best result removed.
- Preserve existing `qualification-1` retain/defer labels as a separate descriptive comparison. Legacy/unknown qualification is not fabricated. This label is not treated as a calibrated probability, and its subset must not be confused with the entire test population.
- Record the protocol hash, source index hashes, dependency versions, training IDs hash, fitted preprocessing/coefficients and each test prediction. The report is evidence for reproducibility, not an installable production model.

A model can improve probability metrics while its selected quotes still lose on average. A few large winners can dominate the mean. No result automatically promotes a model, changes sampling or enables real-money testing. A future forward study must freeze its model and protocol before evaluating new evidence.

## Run in a separate development environment

Python 3.11+ is required. Do not install dependencies into the scanner container or its production environment. These commands create an isolated environment in the development checkout:

```bash
cd ~/apps/solana-radar-dev
python3 -m venv .venv-research-ml
.venv-research-ml/bin/python -m pip install -r research-ml/requirements.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv-research-ml/bin/python -m unittest discover -s research-ml -p 'test_*.py'
```

Dependency installation uses the Python package index. The actual benchmark does not use the network. Set the two capture paths to the existing directories printed by `history-run.sh`; use the directories containing `capture-index.json.gz` and `part-NN.json.gz`, not the derived dataset file:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  ~/apps/solana-radar-dev/.venv-research-ml/bin/python \
  ~/apps/solana-radar-dev/research-ml/benchmark.py \
  --capture-dir /absolute/path/to/older/capture \
  --capture-dir /absolute/path/to/newer/capture \
  --test-start 2026-10-13T08:32:43.912Z \
  --output /absolute/path/to/new-offline-benchmark.json.gz
```

Use a new output filename each time. The publisher refuses overwrite. An alternative test boundary defines another exploratory experiment; do not select the best boundary and call that a forward validation.

## Bounded input and archival handling

Each capture passes the existing checksum, source, clock, window and record validation. The benchmark rebuilds each capture independently, preserving its original evidence cutoff. The two source identities must match. Identical overlapping dataset rows are deduplicated; conflicting overlaps fail, including updates to pending outcomes. Use disjoint windows when possible. File names may differ after downloading attachments: copy them into separate directories under their original `part-NN.json.gz` names without changing their bytes.

At most two captures (32 chunks), 128 MiB combined decompressed source JSON and 20,000 unique **eligible dataset rows** are accepted. This does not raise any production exporter or per-capture raw-row limit. The six-day upload has 20,716 raw signal records, but 18,336 eligible cohort rows; ignored event types are still counted in each input capture. Query-window coverage does not prove the observer ran continuously. No Backblaze transfer is performed.

## Tests and references

Regression tests cover train-only preprocessing, immunity of fitted weights to changed test labels/features, cross-cohort token purging, label-availability clocks, two-sided embargo, policy/schema exclusions, missing versus zero, prediction of failed test quotes, small-sample guards, repeatability, source matching and overlap conflicts.

- https://scikit-learn.org/1.8/common_pitfalls.html
- https://scikit-learn.org/1.8/modules/generated/sklearn.linear_model.LogisticRegression.html
- https://scikit-learn.org/1.8/modules/generated/sklearn.impute.SimpleImputer.html
- https://scikit-learn.org/1.8/modules/generated/sklearn.metrics.brier_score_loss.html
