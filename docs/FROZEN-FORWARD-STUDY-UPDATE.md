# Frozen forward study — October 22, 2026

## Accepted evidence and project direction

PR #44, controlled devnet position accounting, was merged into main as `cf47600b6294a31d534929b8cc0ad81f0a6259b0`. The supplied 17-case check passed. The host import exactly matches the independently rebuilt position from the original forward and reverse receipts: 1,000 original atomic units spent, 997 returned, no acquired-token position remaining, and 10,000 lamports in confirmed transaction fees. The 500,000,000 acquired-token units already in the wallet were correctly excluded. This proves historical accounting for the controlled devnet round trip. It does not prove prospective budget enforcement or mainnet performance. Host repeat-import evidence was not supplied; repeat behaviour is covered by offline regression tests.

All twelve uploaded research chunks passed checksums, identity, window and count checks. Rebuilding readiness exactly reproduced the supplied report. The 72-hour capture ended October 22 at 13:30:27.349 UTC, spans four UTC calendar dates and contains 395 admitted watches. These are quota-sampled cohorts, not a random sample of all opportunities.

| Cohort | Admitted watches | Valid 30s returns | Mean quoted change | Return model | Availability model |
|---|---:|---:|---:|---|---|
| baseline | 119 | 119 | -6.94% | fitted | blocked: no failure examples |
| early-activity | 141 | 107 | -11.55% | fitted | fitted: 107 available / 33 provider failures; 1 unknown |
| fast30-shadow | 135 | 133 | -2.47% | fitted | blocked: only 2 failure examples |

These available-quote means are neither fills nor net profit. Provider quote failures are not proof a token is unsellable. No failed or missing quote was assigned a zero return. The evidence supports testing whether entry context improves prediction; it does not support funding the current signal rules. Faster detection alone has not demonstrated an advantage.

## What is frozen

The existing protocol and model implementation were used once without feature, threshold or hyperparameter searches. Four cohort/target groups met the unchanged fitting guards. Each has fixed legacy-feature and context-feature logistic models plus a training-rate constant comparator. Two availability targets remain unfitted. Training preprocessing and weights stay fixed during all later reports.

- Artifact: `radar-forward-model-20261022.json.gz`, supplied privately in the chat.
- Canonical artifact SHA-256: `016f8d0cf2b9c960e6dfa8406a4566e4473df2200e0040e95ab0480c44f50355`.
- Protocol SHA-256: `65cf32c393a369a3b6fd01e768636e1696eb15abc533457825156db5490edbb8`.
- Training cutoff: October 22, 13:30:27.349 UTC.
- Freeze: October 22, 13:38:57.491 UTC.
- Original earliest test entry: October 22, 13:43:57.491 UTC.
- Host installation uses the later of that boundary and first installation plus five minutes. Reinstalling preserves the original host boundary.

The checksum is of canonical JSON excluding `artifactSha256`, not the gzip bytes. The installer verifies it automatically. The private artifact includes learned weights and training-token exclusions; it is deliberately absent from GitHub. Publication was blocked by automatic approval review, so private delivery is used. This does not change or refit the frozen model.

Local timestamps/checksums are reproducibility controls, not independent proof of an untouched holdout. Keep the original download, installation report and reviewed Git commit. Never reset the experiment directory to restart the evaluation clock.

## Install once

Fetch and check out the exact release commit supplied in the chat. Download the private model to `~/Downloads/radar-forward-model-20261022.json.gz`. Then run, as your regular user:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s "$HOME/apps/solana-radar-dev/forward-study/experiment.py" install \
  --artifact "$HOME/Downloads/radar-forward-model-20261022.json.gz" \
  --directory "$HOME/solana-radar-forward-experiment-20261022" \
  --output "$PWD/radar-forward-install-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
SH
```

Upload that installation report. It excludes weights and training-token identifiers. Installation needs only Python's standard library, creates private 0700/0600 files, and never overwrites or resets an existing experiment. A partial installation stops explicitly. No scanner rebuild, observer restart or devnet transaction is needed.

## Prepare isolated evaluation dependencies

This environment belongs to the development checkout, not the scanner container:

```bash
cd ~/apps/solana-radar-dev
python3 -m venv .venv-research-ml
.venv-research-ml/bin/python -m pip install -r research-ml/requirements.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv-research-ml/bin/python -m unittest discover -s forward-study -p test_experiment.py
```

## Collect and evaluate

Run once to verify the end-to-end workflow, then approximately every 48 hours during this experiment. A first review immediately after installation should report insufficient forward evidence. Do not interpret the training rows as new test results.

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/forward-study/collect-review.sh
```

The script checks the installed artifact, captures the last 72 hours from the local quote ledger, preserves the capture under `~/solana-radar-forward-experiment-20261022/captures`, and evaluates all captures in that directory. Upload the resulting `radar-frozen-forward-*.json.gz`; keep every capture directory. Collection uses sudo only for the existing local read-only collector. There are no cloud, market, notification, signing or transaction requests.

Limits are explicit: eight captures, 512 MiB cumulative decoded input processed sequentially, 100,000 unique audited signal identities and 5,000 admitted watches. Each capture's existing exporter/decoder limits remain unchanged. At the current volume, a 72-hour capture is about 59 MiB decoded. The cumulative limit is separate from the per-capture limit. No old capture is deleted or silently excluded when a cap is reached.

Overlapping watches are deduplicated. Later evidence may append observations to unfinished watches; changed immutable entry fields, revised terminal probes, missing previously present probes, differing source identities, invalid chunk checksums and future evidence clocks stop the review. Counts for skipped signals remain visible, without inventing their outcomes. Source intervals and gaps are reported; query coverage does not establish uninterrupted observer uptime.

For a manual offline evaluation, repeat `--capture-dir` for each preserved capture:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  ~/apps/solana-radar-dev/.venv-research-ml/bin/python -E -s \
  ~/apps/solana-radar-dev/forward-study/experiment.py evaluate \
  --directory "$HOME/solana-radar-forward-experiment-20261022" \
  --capture-dir /absolute/path/to/first/capture \
  --capture-dir /absolute/path/to/second/capture \
  --output /absolute/path/to/new-forward-report.json.gz
```

The first compatible watch per forward token/cohort is used, excluding tokens admitted during training across any cohort. Unknown outcomes and provider failures remain in denominators. Prediction quality is compared with both constant and legacy-feature models; selected quote changes, severe losses, day/token concentration and illustrative cost stresses remain explicit. Nothing refits or activates a model.

## Roadmap from here

1. **Completed:** live collection, bounded evidence, local/cloud backup mechanisms, devnet send/recovery, exact controlled round-trip receipts and historical position accounting.
2. **Started in this release:** the fixed ML comparison is actually fitted and frozen. Next evidence must come after the host installation boundary. Minimum forward guards remain 200 valid labels per target/cohort across at least seven UTC dates; they are review gates, not profitability or deployment approval. Sparse failure labels can take longer. Do not change the guards or choose the best repeated review.
3. **Next engineering focus while collecting:** prospective execution risk accounting, with reservation before any send, durable recovery of ambiguous outcomes, prevention of duplicate spend, and explicit fee/inventory limits. Historical imported receipts must never be misrepresented as having passed a pretrade gate. Keep this work isolated on devnet.
4. **Before any funded pilot:** review out-of-sample evidence, quote failures, measured execution costs and reliability together; define a separate limited experiment and obtain explicit authorization. A successful devnet rehearsal alone supplies no evidence of trading profitability.

No calendar date can be promised for profitable deployment. This release replaces indefinite waiting with a fixed experiment, reproducible captures and measurable comparison gates while prospective risk engineering can continue.
