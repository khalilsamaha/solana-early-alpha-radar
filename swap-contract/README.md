# Unsigned swap instruction policy 1

An offline, protocol-specific check of raw unsigned transaction bytes against a separate caller-supplied policy. It closes a gap between quote observation and the signed receipt/position tools: a plausible quote or a reconciled receipt does not prove that the proposed transaction encoded the intended swap before signing.

**A result of `instruction-policy-match` is not signing permission, a live preflight, proof of an executable route, or proof of profit.** There is no signer, transport, wallet access, ledger update, broadcaster, service, or scanner integration in this component. The current devnet sender and position book do not call it. It must not be used as a bypass for their existing restrictions.

## Run on Kali

The default command runs twelve deterministic synthetic cases and writes a public report. No sudo, environment file, keys, rebuild, restart, funding or collection wait is needed:

```bash
cd ~/apps/solana-early-alpha-radar
python3 -E -s ~/apps/solana-radar-dev/swap-contract/cli.py \
  --output "$PWD/radar-swap-contract-check-$(date -u +%Y%m%dT%H%M%SZ).json.gz"
```

Upload the printed report. Repeating the self-check cannot repeat a chain transaction. Existing output filenames are refused; reports are atomically published with mode 0600. `capturedAt` is the host run time, while fixture policy times use a fixed synthetic clock. Synthetic accounts are hashes and were never funded or checked on chain. The fixture serializer is test-only, not a production transaction builder.

For engineering use, `--input public-packet.json[.gz]` validates a supplied packet against the current local clock. The input is limited to 4 MiB decompressed, rejects duplicate keys and nonfinite JSON, and cannot contain extra schema fields. A syntactically valid rejected packet produces a report with `state=rejected`; shell exit zero means the report was written, not that the policy matched. Malformed input/publication failure exits nonzero without a complete report. No report is a reusable authorization token.

## Exact supported contract

- Devnet-labelled policy only. Fixed direct Raydium CP-Swap program `DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb`; `swap_base_input` only. This is one constant-product DEX contract, not the Jupiter aggregator or all Raydium products.
- Legacy or v0 messages without lookup descriptors. Exactly one all-zero signature slot for the expected fee-payer wallet; signed or partially signed inputs are refused. Version 1 and lookup-bearing messages are unsupported.
- Exactly three outer instructions, in order: `SetComputeUnitLimit`, `SetComputeUnitPrice`, then the swap. No setup, cleanup, tip, additional transfer, authority change or other instruction can be appended. Compute instructions reference no accounts.
- Exact 24-byte swap data: the eight-byte Anchor `global:swap_base_input` discriminator, followed by little-endian u64 input quantity and minimum output. Both must equal the independently supplied policy and be positive canonical decimal strings. Units are token atomic units; no decimals, prices or USD assumptions are inferred.
- Thirteen ordered swap account roles: wallet, authority, config, pool, source, destination, input vault, output vault, input token program, output token program, input mint, output mint, observation. Both token programs must be the standard SPL Token program. Every other role is distinct and cannot alias a reserved program/native-mint key. All message keys must be used by this contract, and the complete global writable set is exact. The wallet is the only signer and fee payer.
- Existing nonnative standard SPL accounts only. Account state is not fetched, so “existing” and nonnative mint identity still require independent verification. ATA creation, closure, WSOL wrap/unwrap, Token-2022, multihop routing and arbitrary Jupiter instructions are outside this contract.
- A policy lasts at most 15 seconds and expires at its exclusive deadline. A separately supplied message-fee assertion must refer to the exact SHA-256 of serialized message bytes, be no older than 10 seconds, not precede policy issuance and not be future-dated. The assertion is not authenticated RPC evidence. Local time and its correctness are trusted.
- Compute units are bounded by policy and the supported 1,400,000-unit ceiling. Micro-lamports per unit, priority fee and asserted total fee each have their own cap. Priority fee is calculated with exact integer ceiling division, never floating point. Total fee must be at least the calculated priority fee and at most policy's total cap. This does **not** derive or verify a base fee: a future live adapter must supply and verify `getFeeForMessage` for these exact bytes and check payer funds separately.

## Public packet schema

See `swap_fixtures.fixture()` for a complete synthetic example, not an approved policy. The exact top-level keys are `format: unsigned-cpmm-contract-1`, `policy`, `unsignedTransactionBase64`, `feeAssertion`.

Policy contains `format: cpmm-instruction-policy-1`, `network: devnet`, integer `issuedAtMs` and `expiresAtMs`, `accounts` (all roles above except the fixed two token-program roles), `blockhash`, decimal-string `amountIn`, `minimumAmountOut`, `maxMicroLamportsPerCU`, `maxPriorityFeeLamports`, `maxTotalFeeLamports`, and integer `maxComputeUnits`.

Fee assertion contains `format: message-fee-assertion-1`, `network: devnet`, `messageSha256`, integer `observedAtMs` and decimal-string `lamports`. It must come from a trusted independent fee observation in a future adapter; changing both the assertion and message to agree is not proof of a real fee. Similarly, copying a quote's account list into the policy would make matching circular.

Successful output binds policy digest, exact unsigned wire digest and message digest, and records the checked amounts/fees. `validUntilExclusiveMs` is only the earliest local assertion/policy deadline, not chain blockhash expiry. A future signer must recheck the same bytes, independent policy and state at its own boundary; it must not trust a caller-provided summary.

## Trust boundaries and following phase

Every result explicitly has `signingApproved=false`, `executionApproved=false`, `ledgerUpdated=false`, `priorPolicyProven=false`, `clusterVerified=false`, `accountStateVerified=false`, `blockhashValidityVerified=false`, `feeAssertionVerified=false`, `deployedProgramVerified=false` and `simulationVerified=false`.

The next engineering phase is a bounded read-only state/preflight adapter: verify cluster and deployed program provenance; associate actual pool/config/vault/observation bytes and authority PDA; verify source/destination owners, mints and balances; check blockhash validity, exact-message fee and signed simulation under the restricted signer contract. Only after those checks can a separately scoped devnet swap be integrated with durable submission and position accounting. Program upgrades and RPC truth remain distinct trust questions. This release does not claim that source review proves deployed bytecode identity.

The strategy track continues separately. An engineering contract match cannot qualify a signal, train/activate ML, or demonstrate a profitable edge. No sampling, scoring, notification, research registration, backup or production setting changes.

## Sources and validation

Contract source reviewed on 19 October 2026 in the official `raydium-io/raydium-cp-swap` repository:

| Source | Reviewed Git blob SHA | Used for |
|---|---|---|
| [swap_base_input.rs](https://github.com/raydium-io/raydium-cp-swap/blob/master/programs/cp-swap/src/instructions/swap_base_input.rs) | `514a2dec36f7bf337302c1b25a2a883f2e230945` | Ordered roles, data arguments, mutable accounts |
| [lib.rs](https://github.com/raydium-io/raydium-cp-swap/blob/master/programs/cp-swap/src/lib.rs) | `4e70f936196ab1ee2487718bebb61e2923fe3518` | Devnet program ID |

These are file-content Git blob IDs, not deployment or repository commit IDs. Branch links can change. The implementation deliberately supports only the reviewed contract. Solana's [fees documentation](https://solana.com/docs/core/fees) supplies the priority-fee formula and compute ceiling. Jupiter's [build documentation](https://developers.jup.ag/docs/swap/build) explains why aggregator/setup/cleanup instructions need their own validation rather than acceptance based on a quote label.

Regression covers both supported wire versions, exact roles and all writable permissions, fee rounding/overflow/caps/message binding, strict atomic amounts, short policy/fee deadlines, malformed/trailing/noncanonical wire data, disallowed versions/lookups, already-signed inputs, extra instructions/accounts, deterministic host replay, and private exclusive report publication. Tests exercise mismatches even when the synthetic fee assertion is rebound to the mutated message; fee binding alone cannot hide a changed swap.
