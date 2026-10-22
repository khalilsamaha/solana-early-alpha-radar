# Offline transaction-intent reconciliation 1

This lab compares a caller-declared **prior intent** with bounded raw RPC evidence. It is a separate offline component: no wallet access, signing, transaction construction, network calls, service installation, execution-ledger writes or resubmission. It does not change the scanner, observer or registered ML protocol.

Run six synthetic scenarios:

```bash
cd ~/apps/solana-early-alpha-radar
python3 -E -s ~/apps/solana-radar-dev/intent-lab/intent_cli.py \
  --output "$PWD/radar-intent-self-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

The scenarios cover existing token accounts, destination creation, source closure, a finalized failure consuming only fees, unknown submission evidence and an unexplained native-wallet debit. They do not create accounts on a blockchain. Fixture balances and programs are synthetic, not suggested trading parameters.

## Contract and evidence

Optional `--input /path/to/bundle.json.gz` reads a saved bundle (JSON or gzip, at most four MiB uncompressed). Duplicate JSON keys and nonfinite numbers are rejected. Invalid JSON produces no report; a well-formed bundle that fails reconciliation produces an explicit failure/unknown report. Outputs are private, atomic, refuse overwrites, and omit raw logs, instructions and RPC text.

A `intent-evidence-bundle-1` object has exactly `format`, `network`, `capturedAtMs`, `intent` and `rpcEvidence`. `rpcEvidence` contains the raw `signatureStatus` and `transaction` envelopes used by `chain-reader/reader.py`. A summarized chain-reader report is not sufficient evidence because it omits the original message and instruction metadata.

A `transaction-intent-1` intent has exactly:

- `format`, `network` (`devnet` or `mainnet-beta`), `signature`, public `wallet`, `preparedAtMs` and `messageSha256`.
- `walletPreLamports`, `inputAtomic`, `minimumOutputAtomic`, `maximumFeeLamports`, `maximumRentLamports`: canonical unsigned decimal strings, bounded to u64. Input and minimum output must be positive.
- `source` and `destination`: `account`, `mint`, `programId`, `decimals`, `preAmountAtomic`, `lifecycle`. Source lifecycle is `existing` or `close`; destination is `existing` or `create`.

Only standard SPL Token Program token-to-token contracts are currently supported. Token-2022, wrapped SOL, sponsored fee payers, multisig transfer layouts and unsupported account operations remain explicit unsupported/unknown cases. This limited account model is not suitable for all tokens discovered by the radar.

`binding(tx)` hashes a canonical representation of the complete compiled outer message, version and resolved loaded addresses. It binds account order, header, blockhash, instruction bytes/account indexes and address lookups. It intentionally excludes provider-only stack-height metadata. **This is not the Solana wire-message hash or cryptographic signature verification.** The expected binding must come from separately retained prepared-transaction evidence before submission, not be reconstructed from the outcome to manufacture a match. This release has no signer or durable prior-intent registrar; preparation times and network labels remain caller assertions.

## Checks

- Reuse finalized signature, slot, wallet-signer and status consistency checks from the chain reader.
- Match the expected canonical message; require the declared wallet to be fee payer.
- Verify declared wallet and token pre-balances, account owner/mint/program/decimals, exact input debit, minimum output credit and fee/rent caps with integer arithmetic.
- Preserve other recorded wallet-owned token accounts unchanged; reject unexplained native-wallet changes.
- Existing accounts need both token-balance sides and unchanged account lamports.
- Creation needs zero pre-lamports, a recorded post-token balance, an explicit System `CreateAccount` funded by the wallet for a 165-byte standard token account, then SPL `InitializeAccount3` for the expected owner/mint. Funding must match post-lamports and the wallet delta. This subset can occur as inner instructions. Missing or different lifecycle instructions stay unknown/unsupported.
- Closure needs a recorded pre-token balance, zero post-lamports, an explicit SPL `CloseAccount` to the wallet with wallet authority after relevant transfers, and a matching wallet refund. It is allowed only for the declared source account. Standard non-native SPL closure requires an empty token balance; that program rule plus the explicit closure evidence supports the zero endpoint, not absence alone.
- A finalized failure must leave the token accounts and their lamports unchanged and debit only the bounded transaction fee from the wallet. It is not an executable fill or permission to resubmit.

Native-wallet delta must equal `-fee - proved creation funding + proved closure refund`. This is native accounting, not P&L in quote currency. Extra native swaps, tips, rent movements or ambiguous evidence remain mismatches/unsupported, even if a transaction may have been legitimate under a broader policy.

Successful comparison is labelled `balance-consistent-with-bound-message`. It does not mean a router has been independently decoded/audited or a swap was safe, spendable or profitable. Every result keeps `executionApproved`, `resubmitAllowed` and `ledgerUpdated` false. Nothing feeds this result into the simulation or production ledger.

## Verification and remaining work

Regression tests exercise message replacement, network/time disagreement, unknown/failing RPC evidence, partial input amounts, minimum output, fees, native debits, owner/mint/program/decimals, changed wallet token accounts, lifecycle proof, v0 loaded keys, malformed instructions, unsupported token programs, bounded input and private report publication. Tests are synthetic and offline.

Before any execution integration: preserve immutable pre-submission intents; cryptographically verify signed transaction/message identity and trusted chain identity; validate expected router instruction semantics; handle wider token-program/account lifecycle cases; obtain recorded/devnet end-to-end evidence; implement independent spending limits, stop controls and uncertain-submission recovery. A separate explicit funded-test decision is still required.

Primary references: [Solana JSON structures](https://solana.com/docs/rpc/json-structures), [SPL Token instruction source](https://docs.rs/spl-token-interface/3.0.0/src/spl_token_interface/instruction.rs.html), [System instruction source](https://docs.rs/solana-system-interface/latest/src/solana_system_interface/instruction.rs.html), [token account closure](https://solana.com/docs/tokens/basics/close-account).
