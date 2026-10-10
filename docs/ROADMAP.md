# Current roadmap — 2026-10-10

Goal: determine whether timely Solana signals can support a repeatable, executable strategy. Faster alerts alone are insufficient; measure entry timing, available routes, exit availability, costs and severe losses.

| Stage | Evidence/status | Next gate |
| --- | --- | --- |
| Host and recovery | Kali service, heartbeat, local/cloud scanner backups and restore checks established | Add verified backup/restore for the separate quote ledger; continue restart and memory monitoring |
| Discovery and paper evidence | Scanner 0.2.9 and research tools 1.1.0 installed | Preserve missing, stale, alternate-pool and interrupted evidence explicitly |
| Timing and execution research — current | Observer 0.5.0 and initial Fast30 deployed; observer 0.6.0 and bounded follow-up prepared for review | Compare mature forward cohorts, timing and route observations; do not mix sampling policies |
| Controlled execution engineering | Not implemented or approved for deployment | Transaction simulation, amount/fee/slippage caps, independent stop control, idempotency and reconciliation |
| Small real-money engineering pilot | Not ready | Stable operation, documented forward evidence, tested controls and explicit user-approved budget/limits |

## Immediate priorities

1. GitHub baseline and CI are established. Review the Fast30 update in docs/FAST30-UPDATE.md; its guarded installer retains the existing host directory and Compose volume.
2. Review the first mature Fast30 report: activation, sample intervals, repeated values, missing outcomes, pool continuity and lead relative to the 60-second cohort. No need to wait a full day to detect an implementation failure.
3. Keep the fast rule frozen while comparing distinct forward entries across time windows. Report selected, excluded and unknown groups separately; deduplicate overlapping exports. Fast30 currently has price observations, not route-quote validation.
4. Protect the quote ledger and automate evidence-quality summaries. Preserve failed buys/sells and unavailable quotes in denominators; never treat them as zero returns or omit them silently.

Recent paper and quote results have negative average outcomes and severe downside cases. They do not establish an edge. A favorable small subset is a hypothesis to test prospectively, not grounds for enabling real trades.

Correctness can be reviewed after the first completed five-minute paths. Strategy validation requires enough distinct observations and separate forward windows for uncertainty and loss tails to be assessed. There is no evidence-based calendar date for real-money testing yet.
