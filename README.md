# Solana Early Alpha Radar

Private research system for discovering Solana tokens, recording paper signals and observing walletless route quotes. The scanner and quote observer do not trade. Separate, explicitly invoked tools can sign and submit tightly scoped **devnet** test transactions; they are not connected to trading signals or mainnet.

**Current engineering release: 25 October 2026.** The [consolidated release and rollback procedure](docs/ENGINEERING-RELEASE-20261025.md) brings the frozen-study tools, controlled devnet spending/recovery, two-cycle accounting and local readiness inspection onto one source base. The release does not deploy the scanner or enable mainnet trading. The **October 28 frozen review is complete: no strategy or model is promoted**. See the [review decision and offline diagnostic](docs/FROZEN-REVIEW-DECISION-20261028.md). Engineering reliability can improve independently; profitable execution remains unproven. The [October 29 availability confirmation](availability-study/README.md) adds a separate fixed-window research protocol after the accepted diagnostic replay.

**October 27 observation batch, under PR review:** the [consolidation record](docs/OBSERVATION-CONSOLIDATION-20261027.md) joins fresh quotes, locked reservations, unsigned simulation and single-leg cost evidence. Host checkpoints passed; round-trip economics and execution approval remain separate gates. No scanner deployment is required.

This repository imports the deployed source captured on **2026-10-09 at 21:59 UTC**. The original hashes are preserved in SOURCE-REVIEW-MANIFEST.json. Subsequent changes are reviewed separately; see docs/FAST30-UPDATE.md for the deployed follow-up and sampling update, and docs/EVIDENCE-UPDATE.md for the subsequent evidence diagnostics update.

| Directory | Component |
| --- | --- |
| `scanner/` | Scanner 0.2.9, dashboard and SQLite evidence store; includes memory, worker and research-quality patches |
| `quote-observer/` | Walletless quote observer 0.9.0 in source, separate evidence ledger; confirm deployed version with host inventory |
| `research-tools/` | Research collector and scenario analysis 1.1.0 |
| `quality-tools/` | Fast30 timing, coverage, joined price/quote reports and registered shadow comparisons |
| `forward-study/` | Fixed feature/target protocol, fitting guards, immutable model freeze and later unseen evaluation |
| `devnet-pool/` | Controlled test-token pool, signed entry/reverse, exact receipts and read-only recovery |
| `position-book/` | Generic offline budget/position tests plus separate historical controlled-receipt accounting |
| `docs/` | Current roadmap, import provenance and development workflow |

The complete project record is in [project history](docs/PROJECT-HISTORY.md). The research concept is in [edge research plan](docs/EDGE-RESEARCH-PLAN.md); its dated phase descriptions are historical. The [current project review](docs/PROJECT-REVIEW-20261022.md) distinguishes implemented tools, supplied host evidence and remaining gates.

Controlled receipt accounting is available for [one historical cycle](docs/CONTROLLED-POSITION-UPDATE.md) and [the fixed two-cycle rehearsal](docs/TWO-CYCLE-ACCOUNTING.md). The latter complements prospective spending reservations; historical imports never retroactively grant pretrade approval.

Start with [development instructions](docs/DEVELOPMENT.md), [current roadmap](docs/ROADMAP.md) and [import review](docs/IMPORT-REVIEW.md). Component READMEs are preserved historical documentation; they may describe earlier deployment layouts.

The [local devnet readiness check](docs/DEVNET-READINESS.md) consolidates the fixed two-cycle journals, spending state and historical accounting into one read-only report. A consistent result does not authorize another cycle or assess the frozen strategy study.

The [private evidence snapshot and isolated restore check](docs/PRIVATE-EVIDENCE-BACKUP.md) preserves closed devnet journals and accounting locally, excludes the signing key, and verifies a disposable stopped copy. It does not restore into the active wallet or provide off-machine disaster recovery.

The [consolidated operational review](docs/OPERATIONAL-REVIEW.md) checks local health, release files, backup stages and preserved capture windows without evaluating the frozen study. A separate explicit capture-only helper bridges evidence before the October 28 review.

The [fresh controlled quote observation](docs/FRESH-CONTROLLED-QUOTE.md) derives an
integer quote from current raw pool evidence, builds an unsigned instruction and
rechecks the pinned deployment, account balances and scoped local reservations.
It makes at most 18 public devnet reads when explicitly invoked. It cannot sign,
submit, reopen a completed cycle or activate a research model.

The separate [unsigned quote simulation](docs/UNSIGNED-QUOTE-SIMULATION.md) adds
one explicitly requested devnet simulation and checks its own token/native
pre/post balances against a new quote. It cannot sign or send a transaction.

## Checks

Requires Node.js 24.10 or newer in the 24.x series and Python 3.12. There are no third-party runtime packages to install for these tests.

```bash
bash scripts/check.sh
```

GitHub Actions runs the same offline tests on pushes and pull requests, plus source hygiene and original-package integrity checks. No production credentials are needed. CI does not deploy, send notifications, call market providers or trade.

## Deployment boundary

Kali remains the running host. **Do not run Docker Compose from this new layout against production yet.** Moving Compose into `scanner/` can change its project name and select a different database volume. A separate deployment migration must preserve the existing Compose project, environment and named volume, with verified rollback.

Paper price changes and route quotes are research observations, not fills or demonstrated profitability. Fast30 is a shadow cohort: no additional notifications or trade execution; bounded follow-up priority is recorded separately.
