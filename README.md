# Solana Early Alpha Radar

Private research system for discovering Solana tokens, recording paper signals and observing walletless route quotes. It does not execute trades.

This repository imports the deployed source captured on **2026-10-09 at 21:59 UTC**. The 113 captured files are unchanged. Added regression tests and repository tooling make future changes reviewable and reproducible.

| Directory | Component |
| --- | --- |
| `scanner/` | Scanner 0.2.9, dashboard and SQLite evidence store; includes memory, worker and research-quality patches |
| `quote-observer/` | Walletless quote observer 0.5.0, separate evidence ledger |
| `research-tools/` | Research collector and scenario analysis 1.1.0 |
| `quality-tools/` | Fast30 shadow report and observation-quality verification from research-quality 1.0.0 |
| `docs/` | Current roadmap, import provenance and development workflow |

Start with [development instructions](docs/DEVELOPMENT.md), [current roadmap](docs/ROADMAP.md) and [import review](docs/IMPORT-REVIEW.md). Component READMEs are preserved historical documentation; they may describe earlier deployment layouts.

## Checks

Requires Node.js 24.10 or newer in the 24.x series and Python 3.12. There are no third-party runtime packages to install for these tests.

```bash
bash scripts/check.sh
```

GitHub Actions runs the same offline tests on pushes and pull requests, plus source hygiene and original-package integrity checks. No production credentials are needed. CI does not deploy, send notifications, call market providers or trade.

## Deployment boundary

Kali remains the running host. **Do not run Docker Compose from this new layout against production yet.** Moving Compose into `scanner/` can change its project name and select a different database volume. A separate deployment migration must preserve the existing Compose project, environment and named volume, with verified rollback.

Paper price changes and route quotes are research observations, not fills or demonstrated profitability. Fast30 is a shadow cohort: no additional notifications, trade execution or polling priority.
