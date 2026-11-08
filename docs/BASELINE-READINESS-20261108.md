# Baseline readiness increment — November 8, 2026

Parent: agenda commit `c0ce2332cc0f76a42cb470963fec93512b4dc86f`, based on accepted
main `e62e2f26f8ea03bac123c774a2d8f224383e9c0e`.

## Changes

- Research CI push triggers now require `main` as well as the existing path
  filters. Pull-request and explicit manual triggers, suites, dependency pins,
  permissions and job budgets are unchanged. Development publication can precede
  Kali acceptance without automatically launching the research workflow.
- The joined launch/quote wrapper calls the `0.9.0` installed exporter, matching
  current source and the dataset wrapper. It does not install or restart it.
  The existing executable wrapper tests cover the exact exporter invocation,
  padded window, successful private publication and cleanup on export failure.

## Validation and limits

Local validation passed all 77 launch-study Python tests and all 19
operational-review Python tests. Parsed workflow YAML matches the parent
definition except for the explicit main-only push restriction; PR/manual
triggers and job definitions are preserved. Shell syntax checks passed.
Source/package integrity, partition coverage and whitespace are checked before
publication. This increment changes no scanner policy,
quote budget, ledger, study registration, signer, sender or runtime installation.

Host inventory is pending. Do not run the joined export until installed observer
version, configured service and live self-report are corroborated by that report.
If they differ, diagnose rather than silently switching an exporter or installing
one. The baseline gate also needs actual rates, retained history and backup
coverage; this code correction does not establish them.

## First host action

Use the pinned development commit supplied in chat and invoke
`operational-review/run.sh` from `/home/redeye/apps/solana-early-alpha-radar`.
Upload its `radar-operational-review-*.json.gz`. This reads local inventory,
loopback health and bounded metadata; it does not call market/cloud providers,
evaluate a model, restart services or send transactions.

Expect a diagnostic report, not necessarily `observed-ok`. The closed frozen
study may produce an old-capture warning. Preserve that evidence and interpret
it separately from active collection/backup failures; do not extend the closed
study to clear a warning. No new PR, CI dispatch, merge or deployment is needed
before reviewing this first host report.
