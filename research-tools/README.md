# Solana Radar research tools 1.1.0

This is a host-only update for the existing v0.2.9 scanner with the previously applied 24-sample checkpoint patch. No scanner rebuild/restart, database writes, provider requests, paid feeds, notification changes or trading. Existing half-hour reporting continues. Python standard library only.

## Install

```bash
python3 -m zipfile -e ~/Downloads/solana-radar-research-tools-1.1.0.zip ~/Downloads &&
sudo python3 ~/Downloads/solana-radar-research-tools-1.1.0/install.py \
  --project "$HOME/apps/solana-early-alpha-radar" --enable-timer
```

The installer verifies bundle hashes and runs 49 tests before installing. It accepts exact managed 1.0.0/1.0.1 installations or an identical 1.1.0 installation. Edited system files are preserved and cause refusal. The scanner must remain version 0.2.9. It creates a dated shadow-rule registration; repeating installation preserves that date. Scanner source, `.env`, database and backup services are unchanged.

Capture richer existing evidence immediately:

```bash
bash ~/Downloads/solana-radar-research-tools-1.1.0/run-now.sh --backup
bash ~/Downloads/solana-radar-research-tools-1.1.0/run-now.sh --live
```

Upload the two `.json.gz` files printed by these commands. Do not wait a day: old data can now be investigated immediately. New entries after installation populate the separate prospective comparison over subsequent half-hour runs.

Check the automatic report:

```bash
systemctl list-timers solana-radar-research.timer --all --no-pager
sudo cat /var/lib/solana-radar-research/last-run.json
sudo cat /var/lib/solana-radar-research/latest-summary.txt
```

The status files appear after the first scheduled run. `sudo systemctl start solana-radar-research.service` runs it now. If a capture is already running, the host lock refuses a second capture; retry once the first finishes. A failed run marks `success:false`; the last successful summary may remain and is not a fresh success.

## New evidence and reports

- `entryFeatures`: allowlisted entry-time liquidity, market cap, concentration, organic score, short-window price direction, activity, recorded security description and available observation/check timestamps. Missing fields remain null. No later snapshot is used to invent an entry-time feature. Values are recorded observations, not independently verified market facts. Pool age and some security details are not present in the existing records.
- `path[].liquidityUsd`: available liquidity beside recorded prices, for collapse investigation. Conflicting liquidity at the same pool/time/price becomes null with a conflict flag; conflicting prices remain subject to evaluator invalidation.
- `checkpoints`: bounded four-horizon evidence, including why an original-pool checkpoint failed and whether an alternate follow-up was recorded.
- `analysis.poolEvidence`: original-pool sample counts and alternate-pool identifiers/times. An alternate pool is not a verified migration, a proven exit route or permission to splice prices.
- `analysis.scenarioEvidence`: explanations beside the unchanged model status for the primary 10-second entry-delay scenarios. An unresolved young entry without its five-minute checkpoint is labelled `awaiting-checkpoint-evidence` for up to six minutes. This is provisional, not a promise that evidence will arrive. All unresolved counts and stress cases stay in the original results. Mature cases with other-pool evidence are labelled `unresolved-with-alternate-pool`; that association does not prove causation.
- `analysis.severeLossCases`: all >=50% modeled losses at 10-second entry delay and 1% costs per side across the three fixed policies. Includes trigger price change, observed price step and its timing, entry features, and available liquidity. The same entry can appear under several policies; do not sum cases as unique tokens. These are observed collapses, not verified rugs or manipulation.
- `analysis.shadowGroups`: selected, excluded and unknown-feature outcomes for each frozen rule, separately by cohort and exploratory/prospective period. Rejected winners and missing paths remain visible. See RULES.md.

The `paper_model.py` evaluator is byte-identical to 1.0.1. Old policy results, cost assumptions, gap handling and exit-price rules are preserved. Baseline and early-activity are separate, potentially overlapping cohorts, not independent portfolio trades. Exact mints identify tokens; display names are not unique.

## Cost and timing assumptions

Fixed policies: 60-second exit, 120-second exit, and first observed +20% target / -15% stop / 120-second deadline. Entry delays 0/10/30 seconds; exit response delay 10 seconds. Use first eligible original-pool observation within 30 seconds of the applicable time; gaps >45 seconds make the scenario unresolved. Threshold crossings do not receive imaginary fills at the threshold price.

Costs are illustrative 0%, 1%, 3% EACH side:

`net = (exit / entry) * (1 - sell cost) / (1 + buy cost) - 1`

This is not an executable P&L model. Fixed network fees, position-size impact, route availability, failed swaps and capital concurrency are not measured. Repeated provider responses are not exchange trade timestamps. The largest-winner exclusion and explicit missing-as-total-loss stress cases are sensitivity checks, not forecasts.

## Resource boundaries

Same SQLite read windows/caps as 1.0.1: one read-only consistent transaction, live 15-second budget plus 17-second alarm guard, 64 MiB WAL-growth guard, closed backup up to 90 seconds. Only completed validated backups without WAL/journal sidecars use immutable read-only mode. The connection closes before analysis or compression.

Caps: 3,000 entries; 300,000 rows per event kind; 240 raw observations per entry; 48 MiB uncompressed output. No partial publication on entry/scan limit failure. Truncated paths are explicit and invalidate their simulations. Extra analysis is bounded by these caps and adds host CPU, memory and report bytes, not scanner requests or database writes.

Scheduled service: 50% CPU quota, 384 MiB memory limit, 90-second total timeout. Retains up to 48 scheduled reports within approximately 512 MiB. Manual reports are not pruned. The report directory and registration are private; report files are mode 600.

Both previously uploaded reports were replayed locally with exactly unchanged evaluator outputs. In this workspace, replay plus analysis took approximately 0.50 seconds for the 1,222-entry backup and 0.06 seconds for the 159-entry live report. These are local processing measurements, not measurements of your Kali host. The enhanced old backup report was about 13 MB as ordinary JSON, below the 48 MiB cap. New exports include additional features, so actual size will differ.

If a backup scan still hits its cap, use an explicitly shorter window:

```bash
cd ~/apps/solana-early-alpha-radar
sudo /usr/local/sbin/radar-research --backup --hours 12 --output radar-research-backup-12h.json.gz &&
sudo chown "$(id -u):$(id -g)" radar-research-backup-12h.json.gz
```

A live budget failure can similarly use `--live --hours 1`. A shorter window is not a full-day cohort.

## Offline replay

```bash
python3 ~/Downloads/solana-radar-research-tools-1.1.0/radar_research.py \
  --replay /path/to/report.json.gz --output /path/to/replayed.json.gz
```

Accepts 1.0.0, 1.0.1 and 1.1.0 complete research exports. Old exports lack the richer entry fields; those remain unknown. Recapturing the existing database/backup is necessary to obtain fields still retained there. Replay preserves the original capture format and evidence cutoff, adds `processedBy`, and preserves an existing matching registration. Without registration, all comparisons are exploratory. The collector does not import current host registration into an old offline export.

## Pause, remove or roll back

```bash
sudo systemctl disable --now solana-radar-research.timer
sudo systemctl stop solana-radar-research.service
```

Uninstall only this add-on's command/configuration/units:

```bash
sudo python3 ~/Downloads/solana-radar-research-tools-1.1.0/install.py --uninstall
```

Payloads, reports and registration are preserved. For a collector rollback, uninstall 1.1.0 first, then run the saved 1.0.1 installer with `--project ... --enable-timer`. No scanner rollback/rebuild is involved. Keep the earlier scanner history patch active.

For the route to a real-money pilot, see ROADMAP.md. This release does not connect a wallet or authorize transactions.
