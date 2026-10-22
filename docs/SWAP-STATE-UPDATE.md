# 19 October 2026 — bounded current pool/account evidence

The 09:49:51 UTC host `radar-swap-contract-check-20261019T094950Z.json.gz` exactly reproduced all twelve expected unsigned instruction-policy cases with zero network requests and transactions. This passes the prior host regression gate, not a live swap gate.

Added `swap-state`, a standalone raw account decoder and bounded public devnet capture. It cross-checks a pool with its config, mint, vault and observation accounts, fixed authority and program-account pointer, under one finalized batch context. Optional prior-packet mode binds the original unsigned contract to wallet accounts, available quantities, exact-message RPC fee and blockhash validity. It does not infer a prior intent from a sampled transaction, approve signing, simulate, or send.

The default command runs fifteen deterministic synthetic cases. The live command reads one latest program transaction as an untrusted pool hint and stops on unavailable/unsupported data without resampling. An explicit pool can also be inspected. Existing WSOL vaults are readable for backing checks, while the unsigned swap contract remains nonnative-only. Flags distinguish pool consistency, packet consistency, blockers, unavailable evidence and unverified deployed binary/consensus/intent provenance.

Development's one live attempt failed to reach devnet on its first genesis request and retained `network-error`. No real pool capture is claimed. The next host gate is the synthetic check plus one read-only capture; upload both reports even if the latest transaction does not contain a supported swap.

See [full commands, bounds and source provenance](../swap-state/README.md). No installation, sudo, rebuild, restart, keys, funding or waiting period is needed. Scanner, observer, research protocols and backups continue unchanged.

Following host review, the next integration work is controlled devnet pool/account selection and program provenance, then a purpose-restricted signer and signed simulation using the same immutable policy. Position accounting and durable unknown-outcome recovery already exist as separately verified components. Funded execution remains gated by their integration, explicit scope/budget and a separate strategy assessment.
