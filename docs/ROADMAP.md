# Current roadmap — 2026-10-11

Goal: determine whether timely Solana signals support a repeatable, executable strategy. Current stage: forward strategy and execution-evidence validation. See [project history](PROJECT-HISTORY.md) for the complete chronology.

| Stage | Status | Next gate |
| --- | --- | --- |
| Host, alerts and scanner recovery | Established in supplied tests | Verify separate quote-ledger backup/restore and sustained resource stability |
| Discovery and paper evidence | Operating on scanner 0.2.9 | Maintain bounded coverage, explicit gaps and unknown data |
| Forward strategy and quotes | Current stage; observer 0.6.0 and fast-evidence-1 deployed | Distinct forward windows, failure denominators, realistic timing and robustness beyond isolated winners |
| Pool/timing/fixed-exit evidence | Prepared update, deployment unconfirmed | Guarded install and first complete paths; separate alternate pools and registered exit periods |
| Execution engineering | Not implemented | Simulation, fee/slippage/amount caps, idempotency, reconciliation and independent stop control |
| Small funded pilot | Not ready | Stable operation, credible strategy evidence, tested controls and explicit approved limits |

The 11 October report contains 404 forward entry-test observations. The ≤50% preceding-rise group has a −7.56% mean two-minute paper return; known liquidity ≥$5,000 has −1.75%. Neither is validated for live promotion. Only 18 Fast30 forward quote watches exist, with mean −9.08% at two minutes. Failed exits remain outside numerical averages but inside denominators.

Immediate development: bounded alternate-pool observations, backward-only timing comparison, and prospective fixed 30/60/120-second exit evaluation. No new provider requests or trade execution. Keep entry rules frozen while collecting this evidence; do not tune thresholds to today's sample and present the same sample as validation.

Correctness can be checked after completed five-minute paths. Strategy validation requires adequate independent windows and execution evidence. There is no justified calendar date for real-money testing yet. Remaining reliability work includes the separate quote ledger and long-term storage growth.
