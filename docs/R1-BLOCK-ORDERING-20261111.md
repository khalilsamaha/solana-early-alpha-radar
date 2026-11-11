# R1 finalized block positions — Kali accepted for their limited scope

Date: 2026-11-11. Deployment metadata is accepted on Kali at
`7fe649340ec0ccfa133a625f9e21e5e733adbd81` for its limited scope; see
[the acceptance record](R1-DEPLOYMENT-METADATA-20261111.md). This increment
locates the same three saved transactions within finalized block signature
lists. It does not select new tokens or inspect subsequent trade outcomes.

## Source question and request contract

The saved RPC evidence establishes provider-reported transaction slots and
instruction indices but lacks block-list transaction positions. Those positions
are needed to sort multiple accepted records in the same slot without substituting
feed arrival time or a signature's lexical order. This probe supplies that
narrow key; it does not establish complete trade history or execution timing.

Primary references:

- [Solana getBlock](https://solana.com/docs/rpc/http/getblock): finalized commitment, signature-only transaction details and rewards suppression.
- [Pinned transaction-status source](https://github.com/solana-labs/solana/blob/d9f20e951a06b61e4505da0955228020b96a8915/transaction-status/src/lib.rs): `TransactionDetails::Signatures` maps the block transaction vector to transaction signatures in vector order. This is a format reference, not an attestation of the current RPC server's implementation.

The only endpoint is `https://api.mainnet.solana.com`. The exact sequence is
mainnet genesis, `getBlock` once per distinct saved slot in ascending order,
then mainnet genesis again. There are at most five attempts for one to three
slots. Current saved slots are 468049828, 468049941 and 468050019.
Each block request uses exactly:

```json
{"commitment":"finalized","transactionDetails":"signatures","maxSupportedTransactionVersion":0,"rewards":false}
```

The original public-RPC transport retains a 30-second monotonic network budget,
at most five seconds per request, one-MiB responses, half-second inter-request
spacing, no retry/fallback, disabled redirects and disabled inherited proxies.
The ordering client also rejects other methods and parameter forms. Only
public block metadata and signature lists are requested; no balances, account
snapshots, prices, transaction bodies or outcomes. Signature lists necessarily
include the other transactions' public identifiers in the selected blocks.

Block metadata requires valid hashes, a parent slot below its queried slot,
bounded optional height/time/reward-partition values, and 1–8,192 unique valid
64-byte signatures. Nonempty rewards or unrequested fields (including full
transactions) cause sanitization and an immediate stop. Duplicate blockhashes
across distinct queried slots are rejected. Where a reported parent happens to
be another queried block, its hash must agree; intervening blocks are not read.

The selected signature must match the saved transaction's primary signature
and occur exactly once in its reported block. Each record key consists of
`[slot, zero_based_transaction_position, parent_instruction_index, inner_instruction_index]`.
Instruction indices come from the already validated saved evidence. Successful
output includes the selected cases in block-list order and a hash of each
ordered signature list. It never claims wall-clock execution order.

## Evidence and acceptance limits

Before any new traffic, original input checksums, source pins, RPC replay,
schema comparison and native-SOL accounting must pass. The new bundle binds
the exact selected samples and original input hashes to the requests/responses.
All ten probe source files are hashed before and after execution. A private
new directory receives `report.json` and `evidence.json.gz`; existing paths
are refused. The original files are preserved. Evidence must replay identically
before output and after rereading it. Independent replay makes no network calls.
Compressed and decoded replay inputs are capped at six MiB.

| Status | Interpretation |
| --- | --- |
| finalized-block-positions-reconciled-live-blocked | All selected primary signatures located in the reported finalized blocks; genesis recheck and retained replay agree. |
| selected-transaction-missing-from-reported-block | A structurally valid returned block omits a selected signature. No partial positions are accepted. |
| block-ordering-unavailable | Missing, malformed, inconsistent, unsupported or unavailable evidence, including a failed genesis recheck. No positions accepted. |

Exit zero means a diagnostic was written, not that the check passed. An
unavailable/null/pruned block is not evidence that a token trade failed. Upload
the diagnostic once; do not automatically retry or change providers.

One provider's finalized response is not independent consensus proof. Sparse
block positions cannot establish feed order, completeness, early-event capture,
subscription gap recovery or uninterrupted chain history. Historical fee
configuration, executable/version equivalence, curve reconstruction, paid
collection and profitability remain unaccepted. Local replay verifies internal
reproducibility, not independent chain authenticity.

## Development validation and Kali action

**181 tests passed**, zero failures/errors/skips: 167 existing and 14 new checks.
The runner used Python 3.12.14 and SQLite 3.53.1, ResourceWarning as an error,
and an audit hook forbidding IPv4/IPv6 socket creation. Elapsed time was
0.977230 seconds. The report pins 23 source files. Tests cover exact bounded
requests, shared-block selection, ordering keys, malformed/oversized/duplicate
lists, missing selected signatures, wrong genesis at either boundary, observed
parent inconsistencies, method/parameter restrictions, deadlines, no-retry
transport failure, sanitized payload retention, tampered replay, exclusive
private output and original-input preservation.

Integration with the original uploaded RPC inputs and **mocked** block responses
passed five-read capture, retained replay and separate offline replay. It produced
case order 3,2,1 for the distinct saved slots and preserved both original files.
The uploaded real deployment bundle also replayed unchanged offline. No actual
block endpoint availability or actual block positions were tested by the developer.

Run the 181-test offline runner from the new pinned isolated checkout, then
`r1-data/ordering_probe.py --read-public-rpc` against the original RPC inputs.
Upload the offline report plus the new ordering `report.json` and
`evidence.json.gz`. No sudo, key, funding, Docker restart or production checkout
change is needed. See [the CLI instructions](../r1-data/README.md).

## Next decision and full gate

After Kali review, consolidate the source-feasibility verdict: what can be
measured, what remains unavailable, and whether a narrowly bounded pilot is
justified. Do not turn this result into another automatic sequence of pricing
diagnostics. Actual collector-adapter validation, provider connection coexistence,
gap handling/recovery limits, off-machine preservation and an explicit numeric
funding/billing decision remain before paid activation. Historical configuration
and executable pricing applicability remain required for any reconstruction claim.

The five-working-day build/validation effort cap remains unchanged. Missing
evidence at that limit leads to a limited/incomplete verdict and reassessment,
not an automatic extension. This development increment does not close R1 or
authorize PR/CI consolidation, main merge, deployment, signing, trades or ML fitting.

## Kali acceptance — 2026-11-11

Reviewed implementation `4d46229bdb8405eff55cc755fe1717f9be26152f`, tree
`5f358af4184bdaf8abcd2c54540c45cd5402e2c3`. The uploaded runner passed all
**181 tests** with zero failures/errors/skips in 2.435042 seconds on Python
3.14.6 and SQLite 3.53.4. All 23 runner and ten probe source hashes match.
The compressed/decoded bundle checksums and original input hashes match;
independent socket-forbidden offline replay exactly reproduces the report.
All five captured calls have the expected method, request ID and received state.

Result: `finalized-block-positions-reconciled-live-blocked`, mainnet genesis
verified before/after. Positions are zero-based:

| Case | Slot | Transaction position | Block transaction count |
| --- | --- | --- | --- |
| 1 | 468050019 | 22 | 253 |
| 2 | 468049941 | 45 | 188 |
| 3 | 468049828 | 89 | 273 |

Case order is 3,2,1. None of the three sparse blocks is another selected block's
immediate parent, so zero parent links were checked. Broader chain continuity,
feed completeness/recovery, executable pricing and full R1 remain unaccepted.

| Uploaded artifact | SHA-256 |
| --- | --- |
| radar-r1-ordering-offline-20261111T130837Z-889211.json | b0cb9cb88942a897fe40faff12a2c7f02e8f6569860bbdb4a602a82208becbde |
| report(2).json | 703cc9e24e3acebd91bc1645f22bf59eafda046db464331f7d25f97d5f78fe9b |
| evidence.json(2).gz | 4f24a702047eb52ba4f25a7dc0bc3d9c008df89a1f9d5a038158a3a4bb0eca33 |
| decoded evidence | 31825a93f29964ddfa7a6a5261f3b0b6535d061bd1f7f67edbac0a49fd9a22d6 |

No new public ordering reads are required. Continue with the consolidated
[source verdict](R1-SOURCE-VERDICT-20261111.md) and the offline
[capture handoff](R1-CAPTURE-HANDOFF-20261111.md), preserving the existing R1 cap.
