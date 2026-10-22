# Metadata provenance and exit availability — 16 October 2026

This update adds evidence needed to distinguish missing source timing from old metadata and failed quote requests from missing observations. It does not improve the entry strategy by itself. Scanner remains 0.2.9, with `metadataProvenanceVersion: metadata-provenance-1`; observer becomes 0.9.0.

## Evidence changes

Organic score and holder count each retain their own Jupiter source (`recent`, `top-organic` or dedicated `search`), local response-processing time, application time and age at signal. A partial response cannot refresh an unchanged field's timestamp. An overwritten value without a known source loses its prior provenance. The values and timestamps are bound together and validated across scanner, observer and offline Python reader. Future, mismatched or malformed receipts stay invalid; old records remain explicitly unrecorded.

These are local receipt timestamps, not provider measurement time. Discovery receipts do not overwrite `jupiterCheckedAt`: that timestamp already affects refresh scheduling and scoring. There are no extra provider requests or changes to signal eligibility, polling, notifications, quote sizes, sampling budgets or backup configuration. The additional bounded fields are stored on candidates and immutable signal context; no new event stream is created.

The dataset adds `exitAvailabilityReview` with a primary 30-second and secondary 120-second horizon. It separates on-time quotes, late quotes, provider-reported quote-generation failures, transport/service failures, other failures, interruptions, missing observations and pending observations. Failed buys stay in a separate category. Skipped signals are retained separately and never assigned returns. Group denominators, per-field provenance coverage and sources remain explicit. Returns describe only validated on-time quotes; failures are not imputed as zero, and provider failure does not prove permanent unsellability. The report also shows the mean excluding the best observation to expose outlier sensitivity.

This is a descriptive report, not a prospective strategy test or trained model. Existing predictors, targets and historical summaries are unchanged. The existing ML benchmark ignores the supplemental fields. Choosing a new feature set, outcome definition or rule needs a separately frozen protocol and forward validation.

## Install

Use the exact reviewed commit provided in the accompanying chat. Keep `solana-radar-dev` separate from the running project. This scanner patch expects the previous entry-context release; unexpected installed edits stop the update before writes.

```bash
python3 ~/apps/solana-radar-dev/deployment/install-metadata-provenance.py \
  --project "$HOME/apps/solana-early-alpha-radar" && \
cd ~/apps/solana-early-alpha-radar && \
sudo docker compose up -d --build --force-recreate radar && \
node --env-file=.env ~/apps/solana-radar-dev/deployment/verify-metadata-provenance.mjs
```

If readiness is still warming up, repeat only the verification command after a few seconds. After it succeeds:

```bash
sudo python3 ~/apps/solana-radar-dev/quote-observer/install.py \
  --project "$HOME/apps/solana-early-alpha-radar" --enable-service && \
sudo python3 -E -s /usr/local/lib/solana-radar-quotes/0.9.0/manage.py status
```

The first observer upgrade snapshots its local ledger and restarts once; an active watch can become interrupted. Repeating the exact verified installation while the managed service is already running does not restart it or duplicate the safety snapshot. Managed configuration and payload modifications still stop installation. Cursor, historical evidence and rolling quotas remain intact. `metadataProvenanceRegistration` records observer activation, not proof of captured field coverage.

## Verify collection

After fresh signals arrive, collect a bounded six-hour export:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/research-dataset/run.sh --hours 6
sudo docker inspect \
  --format 'StartedAt={{.State.StartedAt}} RestartCount={{.RestartCount}} Status={{.State.Status}}' \
  "$(sudo docker compose ps -q radar)"
```

Keep both the dataset and source export. Mixed old/new records are expected. Check field states and ages by cohort, source binding, restarts, failed-buy/exit counts and all denominators before changing a rule. Do not wait a full day to investigate a collection defect; several fresh signals can verify capture, while performance assessment requires independent forward evidence.

## Rollback

Scanner: use the backup path printed by installation:

```bash
python3 ~/apps/solana-radar-dev/deployment/install-metadata-provenance.py \
  --project "$HOME/apps/solana-early-alpha-radar" \
  --rollback /absolute/path/printed/by/installer
```

Then rebuild radar. Modified sources or backup contents are refused. Observer: `sudo python3 ~/apps/solana-radar-dev/quote-observer/rollback.py` verifies and restores the previously installed 0.8.0 program/configuration. Stored evidence is retained. After rollback use that version's exporter, rather than this release's wrapper targeting 0.9.0.
