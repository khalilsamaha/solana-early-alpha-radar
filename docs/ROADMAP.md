# Current roadmap — 2026-10-10

Goal: determine whether timely Solana signals can support a repeatable, executable strategy. Faster alerts alone are insufficient; measure entry timing, available routes, exit availability, costs and severe losses.

| Stage | Evidence/status | Next gate |
| --- | --- | --- |
| Host and recovery | Kali service, heartbeat, local/cloud scanner backups and restore checks established | Add verified backup/restore for the separate quote ledger; continue restart and memory monitoring |
| Discovery and paper evidence | Scanner 0.2.9 and research tools 1.1.0 installed | Preserve missing, stale, alternate-pool and interrupted evidence explicitly |
| Timing and execution research — current | Observer 0.6.0 and bounded Fast30 follow-up deployed; evidence diagnostics prepared for review | Compare mature forward cohorts, timing and route observations; do not mix sampling policies |
| Controlled execution engineering | Not implemented or approved for deployment | Transaction simulation, amount/fee/slippage caps, independent stop control, idempotency and reconciliation |
| Small real-money engineering pilot | Not ready | Stable operation, documented forward evidence, tested controls and explicit user-approved budget/limits |

## Immediate priorities

1. GitHub baseline and CI are established. Review the evidence update in docs/EVIDENCE-UPDATE.md; its guarded installer retains the existing host directory and Compose volume.
2. Review the first mature Fast30 report: activation, sample intervals, repeated values, missing outcomes, pool continuity and lead relative to the 60-second cohort. No need to wait a full day to detect an implementation failure.
3. Keep the fast rule frozen while comparing distinct forward entries across time windows. Report selected, excluded and unknown groups separately; deduplicate overlapping exports. Fast30 now has sampled walletless route quotes; these are not fills or a random sample.
4. Protect the quote ledger and automate evidence-quality summaries. Preserve failed buys/sells and unavailable quotes in denominators; never treat them as zero returns or omit them silently.

Recent paper and quote results have negative average outcomes and severe downside cases. They do not establish an edge. A favorable small subset is a hypothesis to test prospectively, not grounds for enabling real trades.

Correctness can be reviewed after the first completed five-minute paths. Strategy validation requires enough distinct observations and separate forward windows for uncertainty and loss tails to be assessed. There is no evidence-based calendar date for real-money testing yet.

## Latest assessment and development

The 2026-10-10 14:12 UTC reports contain 342 post-update Fast30 entries. Mature five-minute coverage is 321/336 (95.5%); entries without a later early-activity link have 112/117 usable endpoints. This addresses the earlier coverage imbalance, though periods differ and 15 endpoints remain missing. New-policy Fast30 has 17 two-minute quote outcomes: mean -2.92%, median -17.00%, and three losses of at least 50%. There is no demonstrated positive strategy edge.

Evidence diagnostics adds joined price/quote clocks and valuations, two registered independent entry-feature comparisons, and bounded checkpoint attempt reasons. It is a measurement release, not promotion to live trading. Use subsequent entries for forward validation; do not optimize the two thresholds on the same data used to judge them. Remaining engineering work includes quote-ledger backup/restore and, only after strategy evidence supports it, transaction simulation and execution controls.
