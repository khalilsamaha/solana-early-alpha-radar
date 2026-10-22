# 20 October 2026 — controlled test-token provisioning

## Evidence reviewed

`radar-devnet-setup-costs-20261020T104342Z.json.gz` passed exact deterministic replay. Its pinned pool/program capture, rent observations and wallet balance support:

| Item | Devnet lamports |
| --- | ---: |
| Wallet balance | 9,980,000 |
| New test pair rent | 5,110,480 |
| New pool account rent | 30,769,560 |
| Selected config creation fee | 150,000,000 |
| Full setup fee allowance | 100,000 |
| Full estimated setup | 185,980,040 |
| Full estimated shortfall | 176,000,040 |

Pool creation is enabled. The full setup needs more devnet SOL, but the token-pair stage fits the observed balance. The report did not create accounts or authorize a transaction.

## This release

Added `devnet-token-pair`, a separate atomic provisioner with fixed supply, authority revocation, a narrow signer, fresh rent/fee checks, a 0.006 devnet SOL total cap, exact signed simulation, one durable send boundary, finalized receipt and account checks, and read-only recovery. Existing signer modules and production components are unchanged.

The host execution command creates two new six-decimal standard SPL test tokens, each with 1,000 tokens in a holder account owned by the dedicated wallet. Neither mint nor freeze authority remains. There is no pool creation, swap, mainnet action or strategy activation in this release.

Use the exact release commit supplied in chat, then run the default offline self-check and explicit `execute --allow-devnet-submit` from `pair_cli.py`. The expected fee is 25,000 lamports if freshly quoted; rents/fee/balance are rechecked, not copied from the report. The current estimate is a 5,135,480-lamport debit, leaving 4,844,520 lamports. Rent stays in the new accounts.

For unknown/pending outcome, run `recover` without the submission flag. Never delete private state or repeat execute as a retry. Upload only the public JSON reports, not the wallet directory. Detailed commands and limits: [README](../devnet-token-pair/README.md).

## Remaining sequence

1. Validate the actual host token-pair receipt and account state.
2. Obtain sufficient devnet faucet SOL and implement controlled pool initialization with independently fixed account, deposit, fee and receipt scope.
3. Run an actual-wallet signed swap simulation, then separately scoped devnet execution and recovery.
4. Continue frozen forward strategy validation; execution engineering alone does not demonstrate profitability or authorize real-money testing.
