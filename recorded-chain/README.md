# Recorded-chain identity check 1

This component captures an **existing public transaction** and checks its signed wire bytes against the RPC JSON representation. It does not create a transaction, sign, request a faucet transfer, broadcast, register an intent or update any ledger. No wallet or secret is required.

## Live read and reproducible replay

One bounded devnet sample:

```bash
cd ~/apps/solana-early-alpha-radar
python3 -E -s ~/apps/solana-radar-dev/recorded-chain/recorded_cli.py \
  --sample-devnet \
  --output "$PWD/radar-recorded-chain-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

The command reads the fixed official devnet endpoint. At most six requests:

1. `getGenesisHash`: require the pinned devnet genesis hash before proceeding.
2. `getSignaturesForAddress`: request exactly one finalized signature for the System Program.
3. `getTransaction`: finalized JSON encoding, maximum supported version 0.
4. `getTransaction`: finalized base64 encoding for the same signature.
5. `getSignatureStatuses`: historical search for the same signature.
6. `getGenesisHash`: require the same pinned cluster identity again.

The sample is the single returned signature. There is no success filtering, alternate transaction search, rate-limit retry or background service. A transport error stops further requests. An empty discovery stops at two calls. Failed transactions are retained. Null transaction history can still receive the remaining status/cluster checks; it never becomes a successful verification.

An explicit existing transaction uses `--network devnet` (or `mainnet-beta`) and `--signature PUBLIC_SIGNATURE` instead of `--sample-devnet`. It makes at most five read requests because there is no discovery. The quote observer's sequence IDs and route quotes are not transaction signatures.

Each request has a ten-second timeout and four-MiB response cap. Redirects, environment proxies, credentials, arbitrary endpoints and write RPC methods are disabled. JSON-RPC IDs must match exactly; duplicate JSON keys and nonfinite numbers fail. Provider errors are classified without their arbitrary text. Logs, discovery memos, return data and unrelated response fields are omitted; the retained public compiled instruction bytes are necessary for identity verification. No API keys or paid provider subscriptions are used.

The private `.json.gz` report includes the bounded projected capture and its review together. Inputs/replays are capped at 20 MiB after decompression. Replaying a saved report or capture makes zero requests:

```text
python3 -E -s recorded-chain/recorded_cli.py --input saved-report.json.gz --output new-replay.json.gz
```

Output filenames must be new. The report is atomically published with mode `0600`; an existing output is refused before networking. An I/O failure can prevent report publication even after reads occurred; there is no automatic recapture.

Running with only `--output` executes nine synthetic checks. The bundled `devnet-recorded-fixture.json` is different: it is an actual public RPC capture, and can be used with `--input` for offline regression/replay.

## Results and trust boundaries

| Result | Meaning |
| --- | --- |
| `signed-transaction-consistent` | Required signatures verify, legacy/v0 message matches JSON, and RPC cluster/finality/metadata checks agree; no ALT needed |
| `signed-message-consistent-lookup-unverified` | The same signed-message checks pass, but resolved lookup-table addresses are still unverified RPC claims |
| `unknown` | Missing history, unavailable provider/cluster evidence or insufficient finalization |
| `mismatch` | Cluster/signature/message/slot/status or cross-encoding metadata contradiction |
| `unsupported` | Unsupported message version, encoding or evidence shape |
| `invalid-input` | Malformed or excessive data |

`signatureVerified` means Ed25519 verified the exact serialized message bytes for every required signer. `wireAndJsonMatched` means static keys, header, blockhash, instructions and signed lookup descriptors match between encodings. `rpcClusterIdentityMatched` and `rpcFinalized` are **RPC-reported** checks, not independent consensus proofs. Two encodings from the same endpoint are not two independent sources. A signature cannot authenticate balances, execution results or cluster identity.

ALT references (table addresses and indices) are signed, but their resolved addresses are not part of the signed message. The current release validates the shape/counts of RPC loaded addresses without claiming their correctness. Even consistent substitutions in both RPC responses leave `lookupResolution=unverified-rpc-addresses`. No table resolver, historical table reconstruction, Merkle proof or cross-provider confirmation is implemented.

The lower-level wire decoder now exposes signed-message verification for ALT descriptors. The existing intent journal still calls the strict full-binding verifier and **rejects ALT-bearing transactions**. Its registration identity hashes and duplicate/recovery semantics are preserved and regression-tested. There is no database migration.

Native fee-payer changes are reported as raw deltas, not profit or fee-only reconciliation. Missing token recording remains unavailable. A failed transaction can pass identity checks while retaining `transactionOutcome=rpc-reported-failure`.

No prior intent is inferred from a historical transaction. `intentProven=false`, `executionApproved=false`, `resubmitAllowed=false`, and `ledgerUpdated=false` remain explicit. Capture origin/time/request counts are provenance statements, not authenticated proofs; a replay cannot prove where a file was obtained. This component cannot show that an arbitrary transaction met our strategy or that the account belongs to us.

## Recorded development observation

On 17 October 2026 at 18:11:57 UTC, the single selected devnet sample completed all six read requests. Signature:

`TKmSQGWn9AdvSvQZz1bj81bth4gULAqcvgKYfHczZyNsX9fP9kpEDDsetSAcnZSNRSAJu7Z4i3fs4dLrzRiLmaL`

Slot: `512159775`; version: `0`; required signatures: `1`; lookup tables: `1`.

The recorded bytes verify with message SHA-256 `c22a39ddb4c3626fc281017b09b97933a9fc35a5e6b1e0841e034a93d674aaf7`. The result is `signed-message-consistent-lookup-unverified`. RPC reported success; no intent or swap success is inferred. This was someone else's existing public transaction, not a transaction generated or funded by this project.

The initial shipped-transport attempt could not connect directly from the development environment and stopped after one request. The retained development capture used the environment's standard HTTPS proxy route through an injected opener; that distinction is recorded in `transportNote`. The shipped CLI still disables environment proxies. No endpoint, request selection, validation rule or retry limit was changed to obtain a passing sample. No additional transaction was selected after discovering the lookup-table requirement. CI replays this capture offline and does not access RPC.

The 11-case signed-intent journal self-check supplied from Kali at 17:45 UTC matched the prior release exactly. This new host capture remains to be run.

Primary references:
- https://solana.com/docs/rpc/http/getgenesishash
- https://solana.com/docs/rpc/http/gettransaction
- https://solana.com/docs/rpc/http/getsignaturesforaddress
- https://solana.com/docs/rpc/http/getsignaturestatuses
- https://solana.com/docs/core/transactions/versioned-transactions
- Known genesis constants: https://github.com/solana-labs/solana/blob/master/sdk/src/genesis_config.rs

## Lookup account follow-up

`lookup_cli.py --live --input <recorded-report.json.gz> --output <new-report.json.gz>`
re-verifies the existing capture before at most three reads for its referenced table accounts.
`--replay <lookup-report.json.gz> --output <new-report.json.gz>` uses no network.
See [lookup scope, commands and reboot recovery](../docs/LOOKUP-EVIDENCE-UPDATE.md).

The lookup result is current RPC account consistency only. The original transaction review
is not rewritten; journal ALT rejection is unchanged. Account nulls, temporal uncertainty,
wrong ownership and incompatible index state remain explicit. Tests synthesize table bytes
for the two-table public message; synthetic account rows are not presented as chain captures.

The two-table public fixture was supplied by the user from their successful Kali capture
at 2026-10-17T21:54:25.147Z (capture hash
`1bbf74bcbb02be2457ba081f7b8026f3d47f41e36bc900d8ad1264c5d84212dc`).
It is an existing public transaction, not a transaction created by this project.

`devnet-lookup-fixture.json` contains an actual three-request account capture made during
development for that same two-table transaction. It resolves all 14 referenced addresses
consistently; the second table was extended after the transaction, and the replay correctly
retains `unknown-later-extension`. The capture records that the development environment's
standard HTTPS proxy route was used; the shipped CLI disables environment proxies. CI
replays the saved bytes and never contacts an RPC endpoint.


## Standard token-program sampling

The existing CLI still samples the System program by default. The separate
[token capture CLI](../token-reconciliation/README.md#recorded-token-flow-capture-and-replay)
uses the same bounded transport with `sample_program=TOKEN` and records
`selection=recent-token-program-devnet`. Review binds that selection to the
selected signature, finalized slot/error and presence of the selected program
in the signed/resolved key list. It does not assert that every transaction
referencing the program performs a token transfer. No extra selection, retry,
lookup resolution or sender is introduced.
