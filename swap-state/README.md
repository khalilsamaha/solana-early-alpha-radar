# CPMM account state review 1

Read-only current account evidence for the direct Raydium CP-Swap devnet contract introduced in `swap-contract`. This release connects decoded pool/vault/mint state to optional prior unsigned policy bytes. It has no wallet/key access, signer, transaction sender, simulator, production adapter or ledger mutation.

## Host checks

Run the synthetic check and one bounded live sample from the existing project directory:

```bash
bash <<'SH'
set -euo pipefail
umask 077
cd "$HOME/apps/solana-early-alpha-radar"
radar_check_stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
python3 -E -s "$HOME/apps/solana-radar-dev/swap-state/cli.py" \
  --output "$PWD/radar-swap-state-check-$radar_check_stamp.json.gz"
python3 -E -s "$HOME/apps/solana-radar-dev/swap-state/cli.py" \
  --sample-devnet \
  --output "$PWD/radar-swap-state-capture-$radar_check_stamp.json.gz"
SH
```

Upload both public reports. No sudo, `.env`, restart, rebuild, funding, private key or collection wait is required. The first command runs fifteen deterministic synthetic cases. The second performs at most seven public read requests; it cannot sign or submit a transaction. Existing output filenames are refused. Reports are atomically published with mode 0600 and are capped at 8 MiB; compressed inputs have the same decompressed cap and reject duplicate/nonfinite JSON.

The live command may report `unavailable`, `unsupported` or `mismatch`. Upload that result too. A completed report is not necessarily a passed check. The development environment's one live attempt stopped with `network-error` on the first genesis request; successful actual pool decoding remains a host gate. Do not repeatedly run discovery looking for a favorable result.

## Capture modes and bounds

- Default: fifteen synthetic offline cases, no RPC. Fixtures use public hash-derived accounts and a fixed synthetic clock; no keys or accounts were created on chain.
- `--sample-devnet`: read the latest finalized transaction involving the fixed devnet program, with `limit=1`. The first supported `swap_base_input` instruction in its outer/inner compiled instructions supplies a **pool hint only**. Missing, failed, unsupported or rate-limited evidence stops the sequence. No resampling, queue, retry, outcome ranking or alternate endpoint exists. Discovery signatures and loaded addresses are not cryptographically authenticated here; nothing about that transaction is accepted as our prior intent or our fill.
- `--pool PUBLIC_ADDRESS`: inspect one explicitly chosen devnet pool, normally five read requests. This is an engineering input, not a token discovery recommendation.
- `--packet PUBLIC_UNSIGNED_PACKET.json[.gz]`: developer integration mode, normally seven reads. The previous release's unsigned contract must match at start and still match at capture finish. It is not generated from the captured transaction. Packet expiry stops subsequent requests. A real current packet is required; old synthetic examples are not live inputs.
- `--input PUBLIC_CAPTURE_OR_REPORT.json[.gz]`: offline replay. It recomputes the review from retained raw evidence and preserves its original capture time, not current eligibility. `currentRunNetworkRequests=0` distinguishes replay from original requests.

Only `https://api.devnet.solana.com` is used. Redirects and environment proxy inheritance are disabled by the existing RPC client. Responses are capped at 4 MiB before projection, account data at 6,000 base64 characters, a batch at eleven keys, and the capture at seven attempts. Reads have a ten-second timeout and no new request starts after the thirty-second monotonic budget; a final in-flight read may finish later. A review rejects invalid or over-45-second wall-clock capture intervals. Provider errors are reduced to diagnostic states, without raw error text. Failed captures retain a bounded complete failure report, not a fabricated account snapshot.

## What is checked

1. Before/after RPC genesis identity must equal devnet. A bootstrap read supplies pool bindings. All pool, config, mint, vault, observation, program and optional wallet accounts are then reread together in one `getMultipleAccounts` response at finalized commitment with a minimum context slot. The second slot cannot regress, its exact key order is bound, and its pool bindings must still agree with the requested set. The bootstrap's changing reserves/status are not substituted for the second snapshot.
2. Fixed-size raw layouts and Anchor discriminators are checked: PoolState 637 bytes, AmmConfig 236, ObservationState 4,075, standard SPL Mint 82, Token Account 165. Owners, executable flags, positive lamports, enum/option tags, initialization and frozen state are checked. Token-2022 and unknown layout/program variants are unsupported.
3. Pool mint/program/vault/config/observation relationships must agree. Mint decimals match the pool; vault mints and token authorities match their roles. The authority equals the SDK-published devnet PDA, and its bump/seed hash is verified against that constant. This is a fixed known-address check, not a new general curve/PDA implementation. Observation state points back to the same pool. Vault balances cannot fall below accrued fees or exceed nonnative mint supply. Effective reserves are exact integer quantities, never clamped or converted to dollar values.
4. Swap-disabled/not-yet-open pools, empty effective reserves, mint freeze authorities and vault delegates/close authorities remain explicit `eligibilityBlockers`. Structural consistency may coexist with these blockers. An empty blocker list is not a comprehensive token-security assessment. Mint authorities are retained in the decoded evidence and do not imply fixed supply or safe economics.
5. Pool opening time is compared with `getBlockTime` for the same account snapshot slot. Null block time stays unavailable. This does not prove recent market movement or continuous availability.
6. The executable program account must be owned by the upgradeable loader and have the expected Program-state pointer layout. Its ProgramData address is recorded. **The deployed binary, upgrade authority, source equivalence and future upgrades are not verified.** No large program binary is downloaded in this release.
7. In prior-packet mode, account roles and swap direction are compared with the captured pool. Existing standard token source/destination accounts must be owned by the declared wallet and have the expected mints, no delegate/close-authority options, enough source quantity and room for at least minimum output. The output reserve must cover that minimum; the system-owned fee payer must cover the declared total fee cap. The exact serialized message is sent to `getFeeForMessage`; its returned fee must equal the packet's assertion. `isBlockhashValid` must report true. Both RPC contexts must be at least the account snapshot slot. No replacement packet, blockhash, fee budget or account is silently created.

Read-only pool inspection can decode an existing WSOL vault and check its native reserve plus token amount against lamports. Any unsynchronized surplus remains separate. This does **not** extend the previous unsigned swap contract or position book to native tokens, and does not enable wrap/unwrap or account creation/closure.

## Meaning of results

`pool-state-consistent` means the retained **RPC-reported current account relationships** passed this narrow decoder. `policy-state-consistent` additionally means the original unsigned packet and its wallet/state/fee/blockhash checks matched at capture time. Neither means the transaction would succeed, the code is approved, the opportunity is profitable, or the state is still current. A review can retain proven subchecks while its overall state is `mismatch` or `unavailable`; consumers must not accept a partial flag as a pass.

Every report leaves `signingApproved=false`, `executionApproved=false`, `simulationVerified=false`, `deployedBinaryVerified=false`, `independentConsensusVerified=false`, `historicalStateProven=false`, `signatureVerified=false` and `priorPolicyProven=false`. A malicious RPC can fabricate consistent state. One endpoint's before/after genesis and contexts are provenance checks, not independent consensus verification. A local capture is not authenticated, and editing its timestamps or content does not grant signing rights. The current signer, sender, scanner and position book do not consume these reports.

Next: review a real host account capture, establish a controlled supported devnet pool/wallet contract and deployed-program provenance, then bind the restricted signer and signed simulation to the same immutable policy before integrating the existing durable submission/position path. No funded trade, model activation or strategy-performance claim follows from this release.

## Source provenance

Official sources reviewed on 19 October 2026. SHA values are Git **blob** IDs identifying reviewed file content, not deployment hashes or repository commit IDs; branch links can change.

| Official source | Reviewed blob SHA |
|---|---|
| [PoolState](https://github.com/raydium-io/raydium-cp-swap/blob/master/programs/cp-swap/src/states/pool.rs) | `bc80829f58f8652bcffba9c559327dd37f63f507` |
| [AmmConfig](https://github.com/raydium-io/raydium-cp-swap/blob/master/programs/cp-swap/src/states/config.rs) | `eaa966e7977315c4a5d3361c6b9bde0ce973515e` |
| [ObservationState](https://github.com/raydium-io/raydium-cp-swap/blob/master/programs/cp-swap/src/states/oracle.rs) | `6f46cc1cf66b3d80bbef844587b62ed5042d9ca8` |
| [SDK devnet authority](https://github.com/raydium-io/raydium-sdk-V2/blob/master/src/common/programId.ts) | `f034a53d4cb419c82e9b3c31146674ba2eb2cb38` |
| [Standard SPL account layouts](https://github.com/solana-program/token/blob/main/interface/src/state.rs) | `1bf00f7a1b28eb0b776d3bc90605c7e44bfdbcfd` |
| [Native mint identity and decimals](https://github.com/solana-program/token/blob/main/interface/src/native_mint.rs) | `376520229c4446a51c0442b7b8383fd548683db1` |

RPC contracts: [getMultipleAccounts](https://solana.com/docs/rpc/http/getmultipleaccounts), [getFeeForMessage](https://solana.com/docs/rpc/http/getfeeformessage), [isBlockhashValid](https://solana.com/docs/rpc/http/isblockhashvalid). Fixed PDA hash construction: [PDA derivation](https://solana.com/docs/core/pda). Program pointer layout: [loader-v3 interface source](https://docs.rs/crate/solana-loader-v3-interface/9.0.0/source/src/state.rs).

Regression includes raw layout/role/owner tampering, authority bump, stale/expired policies, snapshot regression, missing/frozen accounts, native backing, fee accruals and supply, pool blockers, wallet balances, exact message-fee binding, discovery without resampling, RPC errors/caps/deadlines and atomic host report/replay behavior. None of the synthetic states is promoted to a real network observation.
## Declared quote binding development increment

`quote_binding.py` additionally checks one declared direct devnet quote against
the exact unsigned policy and raw account evidence, including original clocks,
minimum output and funding after declared reservations. `quote_cli.py` provides
an offline eight-case host self-check. This does not activate trading or support
mainnet routes. See [scope, schema and validation](../docs/QUOTE-STATE-BINDING-UPDATE.md).
