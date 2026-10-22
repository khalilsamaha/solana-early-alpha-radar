# Evidence diagnostics update — 2026-10-10

Requires the Fast30 follow-up deployment from commit a55e567a11ba8baa0f308a71061ebd4892183b8a and quote observer 0.6.0. This update changes one production scanner file plus offline reporting helpers. Scanner version remains 0.2.9; health exposes evidenceVersion `fast-evidence-1`. The observer service needs no reinstall or restart.

## What changes

- New Fast30 entries store immutable feature snapshots and two independent shadow comparisons: known reported liquidity >= $5,000; preceding 30-second price increase <= 50%. Missing values remain `unknown`, separate from selected/excluded. These are hypotheses chosen after inspecting prior results, not optimized or proven filters. They do not alter entry eligibility, scoring, scheduling, quotes, alerts or trades. Forward evaluation begins at the persisted `fast-evidence-registration` timestamp and must remain separate from exploratory historical groups. Repeated exports must be deduplicated by entry ID, and quotes by source identity plus sequence.
- Each active Fast30 position records at most four checkpoint-window counter sets and the last attempt. Outcomes distinguish provider errors, no usable market, a different returned pool, stale/invalid observations, no attempt within the checkpoint window, restart interruption and queue eviction. Mixed or inconclusive evidence stays explicitly inconclusive. Different pools do not prove migration; no-attempt is not proof of scheduler failure. Historical rows keep their original reason. Restarted positions have partial diagnostic history, not reconstructed counters.
- `research-quality-report-3` retains the original summaries and adds `joinedEvidence`, `entryShadows` and `missingDiagnostics`. The join uses exact Fast30 entry ID, mint, pool, signal timestamp and entry price. New captures include the source database identity and reject cross-database joins. Older exports without identity can only yield provisional joins. Other cohorts remain explicit but are not joined against this Fast30-only price capture.
- The joined report retains raw atomic amounts, the initial buy quote, fixed hypothetical quantity, both observation clocks, route plans, reported impact/fees and failed quotes. Return arithmetic is recalculated from validated amounts. Token decimals are not exported, so the report does not invent a per-token buy price. A paper/quote discrepancy is not attributed to fees or slippage; quotes remain unexecuted observations.

Costs: no new provider calls, timers or event types for ordinary observations; extra fields on existing entry/outcome rows and one registration record. In-memory diagnostics are bounded per active position and do not write on every poll. Reports retain the existing 10-second database read budget and 48 MiB size cap. Post-capture offline analysis adds CPU time but does not hold the SQLite read transaction. Missing evidence is never filled synthetically.

## Upgrade

Use the exact reviewed commit supplied with the PR. Keep the running Compose directory and database volume at `~/apps/solana-early-alpha-radar`.

From the separate development checkout:

```bash
python3 deployment/install-evidence.py --project "$HOME/apps/solana-early-alpha-radar"
```

The installer verifies expected installed hashes, runs scanner tests in a temporary copy, backs up the changed source and applies it atomically. Unexpected local edits stop installation before changes. Re-running the installer is idempotent. Save its printed backup path.

Only after installation succeeds:

```bash
cd ~/apps/solana-early-alpha-radar
sudo docker compose up -d --build --force-recreate radar
```

Check `/readyz` and then run:

```bash
node --env-file=.env ~/apps/solana-radar-dev/quality-tools/verify.mjs
```

Expected: `ready: true`, `research.fastShadow.evidenceVersion: fast-evidence-1`, and existing follow-up policy `fast-followup-1`. `evidenceRegisteredAt` can be null until the first new Fast30 entry. The restart deliberately marks unfinished paths as interrupted/gapped; it does not rewrite prior outcomes.

## One collection command

Run from the existing host directory:

```bash
bash ~/apps/solana-radar-dev/quality-tools/run-evidence.sh --hours 12
```

This exports the existing observer ledger and captures a bounded read-only scanner snapshot. It does not request new quotes. It writes two private files: `radar-auto-quotes-*.json.gz` and `radar-evidence-review-*.json.gz`. Upload both. `Joined source identity: matched` confirms same-source provenance; it does not certify provider freshness. Compare forward groups only after new entries and their checkpoints exist; immediate reports legitimately contain mostly exploratory rows.

The new collector is manual; existing research and backup timers are unchanged. The observer ledger still needs its own scheduled backup/restore coverage.

## Offline replay

No running scanner is required:

```bash
python3 quality-tools/quality_report.py --shadow-report /path/to/quality.json.gz --quotes /path/to/quotes.json.gz --output /path/to/new-review.json.gz
```

Existing output paths are refused. Old evidence without new registration stays exploratory.

## Rollback

Run `python3 deployment/install-evidence.py --project "$HOME/apps/solana-early-alpha-radar" --rollback /exact/printed/source-backup/path`, then rebuild from the original Compose directory. Rollback checks current and saved file hashes. It restores the prior source, not databases; existing reports and events remain intact. Do not run the older Fast30 installer from this newer checkout; use its original pinned commit for that earlier release.
