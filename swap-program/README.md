# Devnet program deployment observations

This standalone tool records the fixed Raydium CP-Swap devnet deployment and detects changes against an earlier capture. It never loads a wallet, signs, simulates, sends, changes a ledger, or modifies the scanner or research rules.

## Why this follows pool-state validation

The Kali report from 19 October 2026 at 15:43:54 UTC replayed exactly: pool `3CxsELVbhg3L37ptLm7aihdWoSohUFnJxE3JxdCURFce`, finalized account snapshot slot 512847269, seven read requests, zero signatures and transactions. Its 15-case self-check also replayed exactly. The pool, mint, vault, configuration and observation relationships passed the narrow decoder. Both token mints retained mint authorities; neither had a freeze authority. This is test-chain structural evidence, not token quality, our own swap, or strategy validation.

The previous report recorded ProgramData address `3KvTa2fYhMxMZNfHho5oX34yLQLwRauoU2JScBkugvXF`, but did not fetch its bytes. This release closes that observational gap for the same fixed program `DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb`. It does not assume that the pointer or deployment stayed unchanged since that report.

## Commands

From the project directory, using the development checkout:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/swap-program/program_cli.py" \
  --output "$PWD/radar-program-check.json.gz"

python3 -E -s "$HOME/apps/solana-radar-dev/swap-program/program_cli.py" \
  --capture-devnet --output "$PWD/radar-program-capture.json.gz"
```

Use unique output filenames: existing files are never overwritten. The first command runs fourteen deterministic synthetic cases, making zero requests. The second performs at most five public read requests. Upload both public reports even if the capture is unavailable or unsupported. Do not repeat requests merely to obtain a passing sample.

Once a complete actual observation exists, a later capture can explicitly compare with it:

```bash
python3 -E -s "$HOME/apps/solana-radar-dev/swap-program/program_cli.py" \
  --capture-devnet --baseline "$PWD/radar-program-capture.json.gz" \
  --output "$PWD/radar-program-comparison.json.gz"
```

For offline replay use `--input REPORT.json.gz` instead of `--capture-devnet`. Original observation times remain in the capture and review; `capturedAt` is the new report-generation time. A comparison requires an explicit `--baseline`; an embedded baseline in an input report is not implicitly reused. Both raw captures are embedded when comparing, so the resulting report can be checked offline. Supplied summaries and hashes are not trusted. The baseline is an observation, never a trust grant, and is not replaced automatically.

## Checks and interpretation

The five reads are devnet genesis, executable Program bootstrap, one finalized Program + ProgramData batch, block time for that batch slot, and devnet genesis again. The batch must not regress from the bootstrap slot and its Program pointer must still match. The Program must be executable, owned by the upgradeable loader, and contain its 36-byte tagged pointer. ProgramData must have the same loader owner, not be executable, and contain a tag-3 header. Its deployment slot cannot exceed the batch context slot. The authority uses a one-byte Rust Option tag, unlike SPL's four-byte COption.

We hash the complete payload after the fixed 45-byte ProgramData header, including allocation padding, and separately hash the metadata and complete account bytes. Only the 64-bit little-endian ELF envelope is recognized. This is **not** an ELF verifier, reproducible build comparison, bytecode safety audit, or cryptographic account-state proof. The code is not loaded or executed. Public RPC is one source of evidence; the reports are editable and not authenticated authorization records.

| Result | Meaning |
| --- | --- |
| `deployment-observed` | The raw current account relationships and supported layout passed; hashes, slot and authority were recorded. |
| `deployment-unchanged` | Two valid observations have equal identity fields; not approval or proof of source equivalence. |
| `deployment-changed` | Pointer, payload bytes/length, deployment slot, upgrade authority, or metadata differs. Review the change before using it in any future preflight. |
| `comparison-unavailable` | One capture is incomplete/invalid, origins differ, or current evidence predates the baseline. |
| `not-compared` | No explicit baseline was supplied. |

Changes to lamports or the observation slot alone do not imply a deployment change. A redeployment with identical payload bytes is detected through deployment slot/header changes. Authority removal remains a change requiring review; it is not automatically accepted as safer. `sameCapture` marks comparisons of identical evidence. A null upgrade authority describes the observed state, not program safety. Synthetic captures are explicitly labelled and cannot be compared with live captures. No result sets signing or execution approval.

## Bounds and scope

- Fixed `https://api.devnet.solana.com`; only `getGenesisHash`, `getMultipleAccounts` and `getBlockTime`.
- Five attempts maximum, ten seconds per request, no retries, redirects or inherited proxies. No new request after thirty monotonic seconds; a final in-flight read can finish later. Reviews reject capture intervals over forty-five seconds.
- Full account reads only; no data slices. Transport response cap 4 MiB; decoded ProgramData cap 2 MiB; at most two accounts per batch; decompressed input/output report cap 8 MiB. Oversized data produces explicit failure, not a prefix hash presented as a full-code hash.
- Errors are classified without exporting raw provider error text. Complete failure reports are retained. Successful outputs are exclusively published with mode 0600.
- No rebuild, daemon, scheduling change, extra ongoing polling, cloud transfer or restart. Development code does not touch Backblaze.

Next gate: inspect the actual ProgramData observation and decide how to establish an independently reviewed deployment baseline. Purpose-restricted devnet simulation/signing and live position-book integration remain separate engineering work. Strategy validation remains independent; this release changes no signal selection or financial readiness threshold.

## Primary references

- [Solana loader v3 interface 9.0.0 state layout](https://docs.rs/crate/solana-loader-v3-interface/9.0.0/source/src/state.rs): Program 36 bytes, ProgramData metadata 45 bytes, deployment slot and optional upgrade authority. Referenced version is pinned; it is not a claim that the deployed Raydium binary was built with that package.
- [Solana getMultipleAccounts](https://solana.com/docs/rpc/http/getmultipleaccounts): ordered account results, finalized commitment and minimum context slot.
- Prior module [swap-state](../swap-state/README.md) documents the fixed devnet program source and remaining RPC trust limitations.
