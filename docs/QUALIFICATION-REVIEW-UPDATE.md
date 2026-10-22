# Qualification review and pricing evidence update

This update answers whether existing entry-time retain/defer labels separate better and worse quoted outcomes. It does not create a new trading strategy or promote those labels into an alert filter.

## What changes

1. An offline review groups observed quotes by sampling policy, cohort, recorded qualification version and retain/defer/unknown label. It validates quantities and clocks, keeps failures in admission denominators, reports on-time subsets and daily results, and shows means without the best result. Skipped signals never become invented zero returns.
2. Observer **0.7.0** captures optional USD valuations, platform fees and exact route quantities from responses it already receives. Missing fields stay unknown. The first reverse quote is labelled as delayed by request spacing, not an instantaneous spread or fee estimate.
3. Dashboard and Telegram wording explicitly identifies research-only signals. An activity score is not an execution or safety check; retain is not approval. Unknown liquidity is displayed as unknown rather than zero.

Scanner version remains **0.2.9**. Existing qualification thresholds, signal rules, polling, three-cohort sampling, request budgets and notifications settings are unchanged. No trades or additional API requests are introduced. Backblaze is outside this update.

## Validation and current evidence

The complete offline suite passes **505 tests**. Tests cover malformed optional pricing, exact integer amounts, entry-time provenance, mismatched identities, duplicate records, failed/missing quotes, legacy labels, actual quote clocks, notification formatting, installation and rollback.

Replay of the uploaded October 12 17:38 UTC quote export produced these descriptive 30-second results. These are legacy labels without recorded qualification versions, kept separate from future versioned records.

| Cohort | Recorded label | Valid quoted returns / admitted | Mean quoted change |
| --- | --- | ---: | ---: |
| Baseline | defer | 9 / 9 | -17.51% |
| Baseline | retain | 2 / 2 | -8.50% |
| Early activity | defer | 1 / 1 | -2.34% |
| Early activity | retain | 11 / 11 | -6.68% |
| Fast30 | unknown | 11 / 11 | -3.36% |

The tiny retained baseline sample does not validate a filter. These are nonrandom quoted returns, not fills or net profits. Pricing evidence only starts accumulating after the upgrade; historical fields are not fabricated.

## Installation on Kali

Use the exact reviewed commit supplied with the release message in `~/apps/solana-radar-dev`. Do not copy the whole development checkout over production.

Apply the guarded presentation update and rebuild the existing scanner:

```bash
python3 ~/apps/solana-radar-dev/deployment/install-alert-quality.py \
  --project "$HOME/apps/solana-early-alpha-radar" && \
cd ~/apps/solana-early-alpha-radar && \
sudo docker compose up -d --build --force-recreate radar
```

The installer checks installed source hashes, tests a staged copy and saves a source backup. If it rejects unexpected source, stop and share the error; do not bypass the checks.

Upgrade the observer after the scanner rebuild succeeds:

```bash
sudo python3 ~/apps/solana-radar-dev/quote-observer/install.py \
  --project "$HOME/apps/solana-early-alpha-radar" \
  --enable-service
```

This preserves its ledger and feed cursors. A watch active during restart may be marked interrupted. Optional response fields slightly increase stored evidence; request frequency and limits do not change. Review work runs on the host from an export and does not query the scanner database.

Check readiness and observer version:

```bash
cd ~/apps/solana-early-alpha-radar
sudo docker compose ps
curl --max-time 10 --silent --show-error \
  --write-out '\nHTTP %{http_code}\n' http://127.0.0.1:8787/readyz
sudo python3 -E -s \
  /usr/local/lib/solana-radar-quotes/0.7.0/manage.py status
```

Generate the first comparison immediately from retained evidence:

```bash
cd ~/apps/solana-early-alpha-radar
bash ~/apps/solana-radar-dev/qualification-review/run.sh
```

Upload the printed `radar-qualification-review-*.json.gz` file. Keep the accompanying source export. Later reviews can inspect new versioned evidence without changing the protocol. Overlapping reports must not be summed; identify repeated probes by source identity and sequence.

To review an existing export offline instead:

```bash
python3 -E -s ~/apps/solana-radar-dev/qualification-review/review.py \
  --input /path/to/quote-export.json.gz \
  --output /path/to/new-qualification-review.json.gz
```

## Rollback

The observer rollback requires the previously installed, verified 0.6.0 payload:

```bash
sudo python3 ~/apps/solana-radar-dev/quote-observer/rollback.py
```

For scanner presentation rollback, use the exact backup directory printed by the source installer:

```bash
python3 ~/apps/solana-radar-dev/deployment/install-alert-quality.py \
  --project "$HOME/apps/solana-early-alpha-radar" \
  --rollback /absolute/path/to/the/printed/source-backup && \
cd ~/apps/solana-early-alpha-radar && \
sudo docker compose up -d --build --force-recreate radar
```

Neither rollback restores an old database or discards accumulated evidence.

## Roadmap position

Hosting, notifications, bounded collection and memory fixes are in place. Current work is measurement integrity and prospective signal evaluation. Next, assess versioned qualification groups across days and inspect pricing/route failures before selecting any fixed candidate rule for a separate forward test. Evidence does not yet justify a funded trading trial. A calendar deadline cannot substitute for reliable execution evidence and a demonstrated result after realistic costs.
