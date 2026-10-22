# Controlled devnet submission — 18 October 2026

The user's 05:47:36 UTC report records a successful real devnet signed simulation. All six RPC calls completed. The wallet held 10,000,000 test lamports, the simulated fee was 5,000 (below the 10,000 cap), and the simulated wallet post-balance was 9,995,000. Nothing was submitted by that preparation tool. This host report is a sanitized summary; we did not receive the private key, journal or signed transaction bytes for independent replay.

This release adds a standalone explicit one-send workflow and read-only recovery. It reuses the existing dedicated wallet, preserves the simulation record, and permits at most one explicitly authorized replacement of an expired original plan before any submission boundary. Expiry requires finalized block-height evidence and absent signature/receipt records. Once any send boundary is committed, all retries and replacements are blocked. This includes timeouts, RPC errors, process crashes and later expiry.

Before transport, the journal durably records `submission-unknown`; preflight is enabled and provider retries are disabled. The receipt check binds finalized RPC evidence to the exact locally verified signed bytes and expected fee-only wallet change. Unknown evidence remains unresolved; contradictory evidence is quarantined. Recovery has a separate read-only RPC allowlist. A persistent stop marker works independently of the session lock but cannot recall in-flight traffic.

All sending tests use synthetic transport. No transaction was sent from the development environment. The first host execution is pending. Commands and state interpretations are in [the rehearsal README](../devnet-rehearsal/README.md#release-2-explicit-submission-and-read-only-recovery).

The scope is one 1-lamport System self-transfer on devnet, maximum 10,000 test lamports of fee, one application send call, and at most two recorded plans. This is not a token trade or mainnet execution system. No production scanner, observer, signal, ML, quote budget, Telegram, timer or Backblaze configuration is changed. Strategy evidence remains an independent gate. Successful devnet finality will establish this narrow execution/recovery path, not liquidity, sellability, slippage or profitability.

Next engineering gates: validate the actual host receipt and recovery behavior; then develop bounded token-account lifecycle tests and independent spend/position controls. Do not enlarge the scope or authorize real funds merely because this self-transfer succeeds.
