# Project review — 22 October 2026

## Assessment

The project has built useful data collection and execution-safety infrastructure. The controlled devnet entry/reverse now works. The unresolved question is whether the selection strategy offers a repeatable advantage after execution costs and failed exits. Further devnet milestones cannot answer that question. The next work combines actual receipt accounting with an immediate refresh of the existing fixed research protocol.

## What has been achieved

| Area | Evidence and practical value | Remaining boundary |
| --- | --- | --- |
| Hosting | Kali Docker deployment, local dashboard authentication, restart policy, external heartbeat and DOWN notifications were host-tested | The repository merge does not deploy or verify current host health |
| Recovery | Local SQLite snapshots, cloud copies and restore checks were demonstrated; backups are full snapshots, not incremental | Backblaze caps previously blocked cloud jobs; pay-as-you-go was selected, but current successful recovery needs host evidence |
| Discovery | Solana token creation/discovery, batched market enrichment, separate metadata/security checks and fairer queue coverage | Limited providers, 1,000 retained candidates and selective focus are not complete market coverage |
| Evidence | Versioned entry features, observation-quality labels, continuous-path checks, explicit missing/pending/gapped outcomes | Reported changes are not necessarily new provider observations; unknown security/liquidity remains unknown |
| Quotes | Separate walletless fixed-quantity entry/exit sampling and historical exports; failures and exclusions preserved | Quotes are not fills; 2 watches/cohort/hour and 48/day, first eligible arrivals after spacing, not random samples |
| Research | Historical datasets, leakage-aware ML baseline, fixed feature comparison, model-freeze and later-evaluation tools | No demonstrated edge or activated production model |
| Execution | Signed identity, durable one-send boundaries, bounded devnet preflight, finalized receipts and terminal recovery | Controlled direct pool and test tokens only; not arbitrary routes, assets or mainnet |
| Positions | Generic offline reservation/accounting tests exist; this release adds actual controlled-receipt historical accounting | No retrospective claim that generic risk limits protected the already executed swaps |

## Latest verified execution outcome

The four supplied reverse reports were checked for consistent scope, signed-message/wire hashes, signature verification, fee and token arithmetic, time/slot ordering, and agreement with the prior forward report.

| Item | Result |
| --- | ---: |
| Original input | 1,000 original-token atomic units |
| Acquired on entry | 998 acquired-token atomic units |
| Reverse input | 998 acquired-token atomic units |
| Original token returned | 997 atomic units |
| Original-token net change | −3 atomic units |
| Residual acquired position | 0 atomic units |
| Entry + reverse transaction fees | 10,000 devnet lamports |
| Reverse application sends | 1 |
| Terminal recovery RPC / signing / sends | 0 / 0 / 0 |

Both tokens have six decimals. These are fixed test quantities, not market returns. Token loss and SOL fees remain separate units. The terminal recovery is a local replay of retained finalized RPC evidence, not a fresh independent chain observation. Private raw receipt replay is performed by the host tools; public summaries alone are not accepted as ledger input.

PR #43 merged the tested chain into `main` at `ee394cae5f713bea3ca987933fde3fa778fa6610`. Its tree matches the tested head. The 40 superseded open draft PRs (#3–42) were closed after confirming every head was included. New releases branch from and target `main`; avoid extending the earlier chain of draft development branches. Historical branches are retained for provenance.

## Strategy: what the results actually support

The reviewed 15 October historical ML benchmark had AUC 0.5163 (baseline), 0.4931 (early activity) and 0.5026 (Fast30): near chance ranking. Some apparent positive averages depended strongly on individual winners. The old Fast30 price cohorts also deteriorated over longer horizons. Faster detection alone has not solved selection quality or exitability.

The latest reviewed fixed-protocol readiness capture is 17 October: 50 baseline, 59 early-activity and 57 Fast30 compatible watches across two UTC days. All fitting guards failed. It is now 22 October; those numbers must not be presented as current. Re-read already collected evidence now, rather than wait another arbitrary day or change thresholds from stale results.

The fitting guards are 100 labelled watches, 20 examples in each class and three UTC days per target/cohort. Meeting them permits fitting, not trading. Exit-availability targets with too few failures remain unfitted. Protocol registration does not start a frozen-model holdout: the model must first be frozen, then evaluated on later unseen tokens and periods with the existing embargo. The forward minimum is seven UTC days and 200 valid labels per target/cohort; that minimum is also not proof of profitability.

Maintain the fixed primary 30-second quoted-return comparison, secondary descriptive 120-second results, failures, missingness, tail losses, best-winner sensitivity and cohort/sampling versions. Do not pool overlapping exports, incompatible policies or repeated tokens as independent samples. Compare feature models against the fixed simple/constant baselines. Do not add larger models, more alerts or paid streams until the current comparison identifies a specific useful deficit.

## Next engineering sequence

1. **Historical actual-receipt position ledger — this release.** Replay the private controlled journals, distinguish acquired inventory from pre-existing holdings, record confirmed fees once, preserve unresolved exits, and quarantine contradictory or lost evidence. No network requests or key access.
2. **Current strategy readiness — run now.** Capture a bounded 72-hour local quote history and evaluate the existing registration. Preserve capture chunks. If guards pass, prepare a fixed model freeze; if they fail, report the exact deficit and keep the target unfitted. Current data may also justify retiring a weak approach rather than collecting indefinitely.
3. **Prospective risk integration.** Connect reservation, fee/loss limits and persistent stop state to the actual devnet signer/submission boundary. Record unresolved exposure before sending. Allow only bounded, explicit risk-reducing exits; keep duplicate-send prevention and exact receipt reconciliation. Test crash points before/after signing, boundary recording, transport and receipt persistence.
4. **Operational qualification.** Verify host inventory, restart counts, recent backup results, retained evidence and ledger backup coverage. The new small accounting ledger lives with the dedicated devnet journals and is not automatically included in scanner/quote backups. Do not export private journals to GitHub.
5. **Pilot decision.** Review strategy evidence and execution controls together. A tiny funded mechanics test, if later authorized, is distinct from proving a profitable strategy. No mainnet execution is enabled by this release, and no date or expected income is supported yet.

## Technical debt to control

- The scanner remains labelled 0.2.9 despite independent patches. Record component/revision inventories; a version number alone cannot establish deployed code.
- The production directory differs from the repository's `scanner/` layout. Never deploy by running Compose in a new directory without preserving project/volume/environment identity and rollback.
- Statistics now stream and run in a worker, but retained events, alert outcomes and notification records can still grow. Measure before changing retention; preserve research denominators and required receipts.
- Quote evidence has a separate ledger and retention horizon. Archive and deduplicate it by source identity plus sequence; scanner backups alone do not contain it.
- Successful local checks do not prove a current remote backup or today's scanner uptime. Keep operational and research success separate.

## Direction

Continue with two bounded workstreams: a fixed, failure-aware strategy comparison and a narrow, auditable execution path. The engineering has value even if a strategy is rejected: it can distinguish genuine results from missing observations, quote failures, execution errors and accounting mistakes. Revenue remains an empirical question, not a consequence of the number of releases.
