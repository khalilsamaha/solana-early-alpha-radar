# Signed token-receipt accounting 1

Offline engineering tool for comparing a declared prior swap intent, signed transaction bytes and finalized RPC token evidence. It does not construct transactions, read wallet keys, connect to RPC, send transactions, write an execution ledger or change the scanner/observer. The report cannot authorize trading.

## Run on Kali

From the production project directory, run the CLI from the separate development checkout:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/token-reconciliation/cli.py" \
  --output "$PWD/radar-token-reconciliation-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

No flags beyond `--output` are needed for the twelve public synthetic cases. No installation, rebuild, restart, additional faucet funding or waiting period is required. Upload the resulting report. Synthetic fixtures use invented balance/slot/router metadata and public signatures from ephemeral keys that were discarded; they are not chain observations or usable funded accounts.

Optional `--input /path/to/public-bundle.json.gz` audits supplied evidence. It accepts JSON or gzip with a 4 MiB decompressed cap, rejects duplicate keys/nonfinite numbers, and publishes a private atomic gzip report without overwriting an existing path. Parser errors publish no report. Semantically unsupported/mismatched evidence produces an explicit report; CLI completion alone is not a pass. Raw RPC text, logs and transaction wire bytes are not exported into the summary.

## Input

Exactly three top-level keys:

```json
{
  "format": "signed-token-evidence-1",
  "signedTransactionBase64": "PUBLIC_SIGNED_TRANSACTION_BYTES",
  "bundle": {
    "format": "intent-evidence-bundle-1",
    "network": "devnet",
    "capturedAtMs": 1800000005000,
    "intent": {},
    "rpcEvidence": {}
  }
}
```

`intent` and `rpcEvidence` follow the [intent-lab contract](../intent-lab/README.md). The caller must retain a real prior intent; inventing it from the outcome does not establish what was intended before submission. This file interface does not authenticate registration time or the network. Never provide private keys or seed phrases. The public synthetic fixtures show complete inputs.

## Added checks

1. Verify every required Ed25519 signature and exact message bytes, bind canonical parsed message and wallet to the declared intent, and require the complete receipt signature vector to match. Legacy and v0 without lookup tables are supported.
2. Require finalized status/slot consistency, exact input debit, minimum output, wallet prebalance, bounded fee, and supported account creation/closure evidence using integer atomic amounts.
3. Decode standard SPL `Transfer` and `TransferChecked` movements involving each managed wallet token account. Sum split transfers; match direction, source authority, counterparty mint/program/decimals, checked mint/decimals and destination-side counterparty owner/authority. Missing instructions remain unknown; amounts inconsistent with endpoint balances are mismatches.
4. Require new standard token accounts to be initialized before receiving a transfer and closed source accounts to have explicit closure evidence. The underlying limited `CreateAccount` + `InitializeAccount3`/`CloseAccount` layouts remain the only supported lifecycle shapes.
5. Reject extra wallet-native System operations even when their net effect cancels, and unrelated Token Program authority operations involving the wallet. Other recorded wallet-owned token accounts must retain token identity/amount and account lamports, including on failed transactions.
6. Permit **existing** standard-program WSOL source or destination accounts with nine decimals, both token endpoints, and a positive unchanged `account lamports − token atomic amount`. Report this as an **implied backing reserve**, not verified account data or proof of rent exemption. Wallet fees and rent stay separate from the WSOL token movement. WSOL creation, closure, SyncNative, wrap/unwrap and unsynchronized balances are unsupported.

The opt-in `wrapped_existing` keyword is used only by this auditor. Default intent-lab and durable intent-journal behavior continues to reject WSOL. This does not widen signer or submission permissions.

## Results and limits

- `signed-token-accounting-consistent`: supported signed identity, supplied RPC balances and decoded transfer amounts agree. This is **not** independent router validation, a consensus proof, an executed trade in our ledger or a profitability result.
- `finalized-failure-fee-only`: supplied finalized failure leaves token balances unchanged and charges the bounded fee. No successful transfers are inferred from instructions of a failed transaction.
- `unknown`: insufficient finality, balances, instructions or counterparty identity.
- `mismatch`: contradictory identity, balances, transfer amounts, fees, reserve or lifecycle order.
- `unsupported`, `unsupported-or-invalid-wire`, `invalid-input`: evidence outside the supported contract or invalid encoding/signatures. No automatic retry or fallback.

Signatures authenticate the outer message, not RPC inner instructions, token metadata, balances, cluster identity or finality. Account-data snapshots, delegate/close-authority state, arbitrary router semantics, transient accounts absent from both balance arrays, all ALT resolution, Token-2022 extensions/transfer fees, sponsored fee payers, multisig transfers, tips and WSOL lifecycle operations remain outside this release. The arithmetic cannot prove actual liquidity or future sellability. Off-transaction accounts are not inspected. Reports always keep execution approval, resubmission and production-ledger update false.

Next integration gate: independently captured token-lifecycle evidence tied to retained prior intent and cluster identity, then supported router semantics and independent wallet spending/position controls. Do not connect this report directly to mainnet execution.

Primary references checked 18 October 2026:
- https://solana.com/docs/rpc/json-structures
- https://www.solana-program.com/docs/token
- https://solana.com/docs/tokens/basics/sync-native
- https://solana.com/docs/tokens/basics/close-account


## Recorded token-flow capture and replay

`capture_cli.py` is a separate historical-evidence workflow. It never constructs a prior intent from the observed outcome and does not call the prior-intent auditor with invented expectations.

- Default: eleven public synthetic offline checks; output `recorded-token-self-check-1`.
- `--sample-devnet`: exactly one newest finalized standard SPL Token program discovery row, then its JSON/base64 transaction and signature status with before/after genesis checks. At most six public RPC reads. Unsupported/failed selections are retained without resampling.
- `--network devnet --signature <public-signature>`: explicit capture, at most five reads. Explicit `mainnet-beta` is also read-only; there is no automatic mainnet discovery.
- `--input <capture-or-report.json.gz>`: entirely offline replay. Accepts original `recorded-chain-report-1` and new `recorded-token-report-1` envelopes, or a raw capture.
- `--output <new-path>` is always required. Input is capped at 20 MiB decompressed, RPC responses at 4 MiB each, with duplicate/nonfinite JSON rejected. Private atomic output refuses overwrite. Fixed public endpoints, no redirects/environment proxies/retries; each RPC call has a ten-second socket timeout. No wallet directory or private material is read.

Recorded successful accounting checks all recorded token endpoints and all native balance deltas. Decoded standard SPL transfer quantities are applied in instruction order, with intermediate underflow/overflow checks. Source owner authority, mint, program and decimals must match. Supported creation is System CreateAccount followed by InitializeAccount3; supported closure must empty a non-native account before refund. Existing WSOL requires unchanged positive implied backing and matching native/token movement. Raw missing lifecycle endpoints remain null in exported summaries. Failed finalized receipts must preserve token balances and have only the payer fee as native change.

Results never approve execution or resubmission. Unknown/missing evidence is not an empty balance or an executed transfer. ALT resolution, Token-2022, mint/burn, delegated/multisig authorities, wrap/unwrap and transient unrecorded token accounts are not supported. A router's signed instruction is authenticated but its semantics are not audited. The report records RPC claims rather than independently proving consensus or safety.

See [host commands and current evidence](../docs/RECORDED-TOKEN-FLOWS-UPDATE.md). The live development attempt could not connect and stopped after one read attempt; a successful actual token-flow capture remains a host gate.

Primary references for the decoded standard instructions and public capture:
- https://github.com/solana-program/token/blob/main/interface/src/instruction.rs
- https://solana.com/docs/rpc/http/getsignaturesforaddress
- https://solana.com/docs/rpc/http/gettransaction


`devnet-token-fixture.json` is the actual six-request host capture supplied at
2026-10-18T20:40:13.436047+00:00: legacy devnet slot 512559524, two verified signatures,
one ten-atomic-unit transfer between existing accounts, and a 10,000-lamport fee.
Its capture hash is `b371549550e88146ee057c98a766005a46b9e96735b78db2ae27ef6376ce5153`.
CI replays it offline. It is an existing public transaction, not one submitted by this project,
and supplies no account-creation/closure or prior-intent evidence.
