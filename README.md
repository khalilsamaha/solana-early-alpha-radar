# Solana Early Alpha Radar

Private research system for discovering Solana tokens, recording paper signals and observing walletless route quotes. The scanner and quote observer do not trade. Separate, explicitly invoked tools can sign and submit tightly scoped **devnet** test transactions; they are not connected to trading signals or mainnet.

**Current review: 22 October 2026.** A controlled devnet entry and reverse have finalized, with exact token/fee reconciliation and local terminal recovery. PR #43 consolidated the tested development chain into `main`. Strategy profitability remains unproven. See the [current project review and next gates](docs/PROJECT-REVIEW-20261022.md).

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

Next release: [controlled receipt position accounting](docs/CONTROLLED-POSITION-UPDATE.md). It imports replayed local entry/reverse receipts into a bounded, idempotent historical ledger. It makes no network requests and does not sign or submit. Pretrade budget enforcement is not retroactively claimed.

Start with [development instructions](docs/DEVELOPMENT.md), [current roadmap](docs/ROADMAP.md) and [import review](docs/IMPORT-REVIEW.md). Component READMEs are preserved historical documentation; they may describe earlier deployment layouts.

## Checks

Requires Node.js 24.10 or newer in the 24.x series and Python 3.12. There are no third-party runtime packages to install for these tests.

```bash
bash scripts/check.sh
```

GitHub Actions runs the same offline tests on pushes and pull requests, plus source hygiene and original-package integrity checks. No production credentials are needed. CI does not deploy, send notifications, call market providers or trade.

## Deployment boundary

Kali remains the running host. **Do not run Docker Compose from this new layout against production yet.** Moving Compose into `scanner/` can change its project name and select a different database volume. A separate deployment migration must preserve the existing Compose project, environment and named volume, with verified rollback.

Paper price changes and route quotes are research observations, not fills or demonstrated profitability. Fast30 is a shadow cohort: no additional notifications or trade execution; bounded follow-up priority is recorded separately.
