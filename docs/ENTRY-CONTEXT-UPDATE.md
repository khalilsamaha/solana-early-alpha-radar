# Entry context update — 15 October 2026

This release captures missing entry-time evidence for baseline, early-activity and Fast30. It uses observations already held by the scanner; it adds no provider calls. Scanner remains 0.2.9 with `entryContextVersion: entry-context-1`. Observer becomes 0.8.0.

## What changes

Each new signal records a bounded, detached snapshot:

| Context | Source | Interpretation |
|---|---|---|
| Liquidity, market cap, volume, buy/sell counts | Candidate market fields | Provider-reported values; unknown is distinct from zero |
| Total transactions, average reported trade size | Both valid counts; volume divided by a positive count | Unknown if either count is missing; not organic-demand evidence |
| Organic score, holder count | Candidate metadata | May be absent, especially in young tokens |
| Concentration and authority presence | Candidate security fields | Unadjusted top-ten token accounts; not holder ownership or a safety verdict |
| Market/security/Jupiter timestamps | Existing provider receipt/check timestamps | Ages at signal time; future/invalid clocks rejected |
| Market/security TTL labels | Captured scanner configuration | Within configured TTL does not prove the underlying market data is current |

Jupiter age is recorded without inventing a freshness limit. Security observations may remain recorded but stale. Null parsed authorities mean no active authority; missing or malformed authority fields remain unknown. Supplemental context preserves neither authority addresses nor arbitrary provider text.

The observer validates time, mint, pool, numeric types and clock consistency. Malformed context does not block an otherwise eligible signal; it is labelled invalid. Old events are labelled absent and are never enriched from present-day candidates. Derived activity is recomputed from validated fields.

Legacy `features`, `featureCapture`, qualification groups and ML inputs are unchanged. The dataset adds `supplementalEntryContext` and `supplementalContextCoverage`. The existing fixed ML benchmark ignores the supplemental fields. A separately frozen future protocol must explicitly select new predictors and handle stale/missing values. This release does not train or activate a model.

No scoring, signal threshold, focus scheduling, polling, quote quantity, request budget, notification policy, SQLite schema or backup configuration changes. Additional storage is approximately 1–2 KB per new entry/signal, rather than per market snapshot. Actual collection coverage and timing should be checked after deployment; offline tests cannot certify host performance.

## Install from this reviewed checkout

Run from the original host project. The final chat instructions pin the reviewed Git commit. Keep the dev checkout separate from the running project.

```bash
python3 ~/apps/solana-radar-dev/deployment/install-entry-context.py \
  --project "$HOME/apps/solana-early-alpha-radar" && \
cd ~/apps/solana-early-alpha-radar && \
sudo docker compose up -d --build --force-recreate radar && \
node --env-file=.env ~/apps/solana-radar-dev/deployment/verify-entry-context.mjs
```

The scanner installer validates the known source hashes, stages and tests the combined source, and saves a rollback copy. Unexpected installed edits stop the installation. No configuration or database is copied. If the immediate readiness check runs during startup, wait a few seconds and repeat only the verification command.

After scanner verification succeeds:

```bash
sudo python3 ~/apps/solana-radar-dev/quote-observer/install.py \
  --project "$HOME/apps/solana-early-alpha-radar" --enable-service
sudo python3 -E -s /usr/local/lib/solana-radar-quotes/0.8.0/manage.py status
```

The observer installer runs its tests, verifies managed configuration, takes a local safety copy of its ledger and preserves existing cursor/budgets. An in-progress watch may be labelled interrupted on restart. `entryContextRegistration` records observer activation, not proof that a new signal has already been captured. An old scanner plus new observer remains supported with absent context.

## Check actual collection

After fresh signals arrive, run:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/research-dataset/run.sh --hours 6
sudo docker inspect \
  --format 'StartedAt={{.State.StartedAt}} RestartCount={{.RestartCount}} Status={{.State.Status}}' \
  "$(sudo docker compose ps -q radar)"
```

Upload the generated research dataset. Inspect recorded/absent/invalid context by cohort, field missingness, timestamp ages, unchanged sampling limits and quote failures. The six-hour export may contain old events with absent context; those are expected. No need to wait a day to discover capture defects. Do not restart repeatedly to gather evidence.

## Rollback

Scanner: pass the printed `source-backups/entry-context-...` path to `install-entry-context.py --project ... --rollback ...`, then rebuild radar. Modified sources or rollback copies are refused. Observer: `sudo python3 ~/apps/solana-radar-dev/quote-observer/rollback.py` verifies and restores the installed 0.7.0 program. Historical context and the current ledger remain retained; rollback does not rewrite evidence.
