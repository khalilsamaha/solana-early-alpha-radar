# Controlled devnet CPMM pool

This module initializes one pool using the verified test-token pair from `devnet-token-pair`. It does not swap, trade on mainnet, change scanner rules, or approve a financial pilot.

The two mints are sorted by their raw public keys. Exactly 500 tokens of each six-decimal mint are deposited; 500 of each remain in the wallet. All pool/vault/oracle/LP/associated-token addresses are derived locally. No new secret key is generated. Only the existing devnet wallet signs.

## Policy and evidence

- Fixed devnet endpoint, genesis, Raydium CPMM program, configuration and fee receiver.
- Standard SPL tokens only. Both test supplies remain 1,000, mint/freeze authorities absent; wallet holders have no delegate or close authority.
- 300,000 compute units, zero priority price; exact-message fee at most 10,000 lamports.
- Observed creation fee at most 150,000,000 lamports; observed rent plus creation fee plus fee allowance at most 190,000,000 lamports.
- **These spending caps are pre-send checks, not on-chain fee ceilings.** Raydium `initialize` has no creation-fee ceiling argument. Configuration or rent changes between checks and execution can change the actual debit. Receipt disagreement is quarantined, not retroactively prevented. This is a devnet-only workflow.
- Full ProgramData fingerprint must match the reviewed deployment both before signing and after simulation. This does not prove source/build equivalence or prevent later upgrades.
- Existing finalized token-pair journal and exact signed message must validate. Fresh on-chain accounts must still have the full test supplies.
- One combined finalized account snapshot; initial observation at most ten seconds old when preparing intent. Thirty-second intent deadline and block-height margin before sending.
- Independent Python and Node address/message compilers. PDA tests include official SDK vectors and previously recorded real devnet account addresses at bumps 255, 253 and 252. Curve arithmetic is used only for public PDA derivation; Node crypto performs signatures.
- Simulation verifies native balances, token balances, raw account ownership, mint authorities, LP supply, reserves, rent and oracle linkage. The observed deployment and pre-accounts are checked again before sending.
- Exclusive, fsynced signing and send markers. One application send with `maxRetries: 0`, no automatic re-signing, no resend after unknown outcomes. RPC/server behavior and parties holding signed bytes are outside the application's boundary.
- Receipt verification binds the complete signed transaction to finalized status and checks every native balance delta and exact token balance rows. Post-transaction raw accounts are a separate later observation. Third-party use of the pool or fee receiver can make strict checks fail; this is not a reason to execute again.
- A successful initialization has reserves of 500,000,000 atomic units each. LP mint/holder supply is 499,999,900 atomic units (nine decimals), while pool accounting includes the 100 locked LP units and records 500,000,000.
- Public reports contain no private keys or signed transaction bytes. The signer is same-user software, not an OS sandbox or hardware wallet.

## Actions

Default `self-check` uses disposable unfunded wallets and synthetic RPC, exercising the real restricted signer. It makes no public requests. `inspect` checks the existing wallet identity and performs seven read-only RPC requests without creating the pool journal. It does read the local wallet key to verify its public identity; it does not sign.

`execute` requires `--allow-devnet-submit`. It repeats preflight itself, so an exported inspection report cannot authorize a stale transaction. Insufficient funding returns `funding-required` **before** creating `controlled-pool-v1`, allowing a later execution after faucet funding. Once that directory exists, repeated execute only reports its state. Never delete it or replace it to retry. A partial preparation needs investigation rather than an automatic reset.

`recover` only reads RPC evidence for the recorded signature, even after timeout or expiry. `status` makes no RPC calls. A finalized result is an as-of result, not a fresh inventory.

All wallet actions use the common session lock. A `STOP` marker in the wallet directory prevents signing/sending. Recovery remains available to establish the outcome. Existing scanner, observer, backups and research tools are unchanged.

See [host commands and release notes](../docs/DEVNET-POOL-UPDATE.md).

## Source basis

Reviewed official source on 2026-10-20:

- [Raydium initialize](https://github.com/raydium-io/raydium-cp-swap/blob/master/programs/cp-swap/src/instructions/initialize.rs), blob `36f4301e186240eeedc1e829edf32b95b8fb2a2e`: ordered accounts, fixed initial deposits, LP lock, native creation fee and SyncNative.
- [Raydium program constants](https://github.com/raydium-io/raydium-cp-swap/blob/master/programs/cp-swap/src/lib.rs), blob `4e70f936196ab1ee2487718bebb61e2923fe3518`: devnet program and fee receiver.
- [Pool layout](https://github.com/raydium-io/raydium-cp-swap/blob/master/programs/cp-swap/src/states/pool.rs), blob `bc80829f58f8652bcffba9c559327dd37f63f507`: seeds and pool accounting fields.
- [Solana SDK public-key derivation](https://github.com/solana-foundation/solana-web3.js/blob/maintenance/v1.x/src/publickey.ts), blob `c8195b4a84c72d81a3eac7932bb9ab23ae3d50c5`; [test vectors](https://github.com/solana-foundation/solana-web3.js/blob/maintenance/v1.x/test/publickey.test.ts), blob `bc4b9cb4c3fa3802845033c63e1010b20e4b07d0`.

These source references describe the implementation interface, not a reproducible-build attestation for the pinned deployed binary.

## Journal size correction (2026-10-20)

The recorded devnet Associated Token Program is a legacy executable with 140,044 base64 characters of data. The original 128 KiB plan readers rejected the resulting intent before signing, and reporting repeated the read failure. Empty executable fixtures had missed this case. Simulation and post-account handling also used a 6,000-character cap, while inherited observation readers accepted only 32 KiB.

Pool journal readers and the restricted signer now use a 512 KiB file bound. Only the Associated Token Program position, when executable, permits up to 256 KiB of base64 payload in the twenty-account evidence set; other regular accounts retain the 6,000-character bound. The separately pinned ProgramData slot retains its existing larger bound. The twenty-account JSON set is bounded to 500,000 bytes. Observations use pool-specific bounded readers with the same sequence and count checks. No account data is discarded or substituted.

`status` exports `journalFiles` presence and byte sizes plus `journalReaderVersion=pool-journal-size-1`. It makes no RPC calls and does not sign, send, delete, rewrite or resume an intent. Existing incomplete journals remain blocked from execute. After upgrading, run **status only** and review its public report before choosing any further action. Do not remove the journal to retry. The fix does not establish whether an earlier host attempt signed or sent; its saved markers must be inspected.

## Explicit replacement of the unsigned size-failure plan

`execute --allow-devnet-submit --allow-unsigned-size-replacement` supports one narrowly scoped replacement. Under the common wallet lock, it requires exactly an oversized `plan.json` and the original `preparation-incomplete` observation, with no signing-attempt, signed transaction, simulation or submission files. It validates the original message and test pair, requires intent time expiry and finalized block height beyond its validity, and repeats deployment, funding and absent-pool checks.

Before replacement it saves an exclusive durable boundary with file hashes, then renames the complete old journal to `controlled-pool-v1-unsigned-size-archive-v1`. It retains every original byte. The fresh attempt uses the same wallet, test pair, pool addresses and spending checks, with a fresh blockhash and the normal signed simulation before its single permitted send. The flag does not allow replacement of a signed, simulated, submitted, ambiguous or previously replaced attempt. Ordinary execute and recovery never perform replacement.

A crash around the archive boundary remains blocked for inspection; no automatic resume or cleanup occurs. The intact same-user local journal is the basis of these checks, not a guarantee against another process or a user deleting or modifying files. Never manually delete or move state to obtain another attempt.

## Controlled swap submission

After a successful controlled swap simulation, `swap_submit_cli.py` supplies a separate one-send devnet execution journal and read-only receipt recovery. The old simulation is preserved; fresh policy, program/accounts, signature verification, simulation and pre-send checks are required. Fixed input is 1,000 atomic units and minimum output is 990. Terminal reports replay private finalized receipt evidence. See [the submission release](../docs/CONTROLLED-SWAP-SUBMISSION-UPDATE.md) for limits, outcomes and host usage. There is no journal reset, automatic resend or mainnet path.

## Receipt-bound reverse and round-trip accounting

`reverse_cli.py` derives one reverse from a verified finalized forward receipt, using its complete acquired quantity and only the original controlled accounts. It creates `swap-reverse-v1`, preserves prior journals, and requires fresh deployment/accounts, simulation and native/holder continuity. Terminal accounting keeps token changes and native fees separate; failed exits retain the open acquired quantity. See [release and host commands](../docs/CONTROLLED-REVERSE-SWAP-UPDATE.md). No production trading integration or mainnet submission is enabled.

## Durable spending reservations

New controlled executions reserve principal and the round-trip fee allowance before signing. Unknown outcomes retain reservations across process crashes; verified finalized receipts settle them. Historical executions remain explicitly unguarded, and cannot authorize a new guarded reverse. See [the spending guard release and offline host check](../docs/DEVNET-SPENDING-GUARD-UPDATE.md). Do not reset existing journals to exercise this change.

## Preparation of a subsequent controlled cycle

`cycle_cli.py` checks closed historical receipts and current finalized balances, then records one separately identified subsequent cycle with cumulative input and fee allocation. It preserves prior journals and has no signer or send method. See [scope, refusal conditions and host commands](../docs/DEVNET-CYCLE-PREPARATION-UPDATE.md). A prepared record is not executable; sender integration and a controlled network demonstration remain separate milestones.
