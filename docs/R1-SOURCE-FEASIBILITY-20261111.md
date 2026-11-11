# R1 source feasibility — documentation and bounded host probe

Date: 2026-11-11. Status: **source feasibility not established; live blocked**.
The 44-test offline core is accepted on Kali. The second implementation increment
adds a transport controller exercised with fake wires and a read-only host probe.
Neither opens PumpPortal or spends money. No scanner/runtime/frozen-study changes.
Local validation: 72 tests and the standalone acceptance runner passed on Python
3.12.14 with ResourceWarning treated as an error. The previously Kali-accepted
`capture.py` is byte-identical. The new controller/probe are accepted on Kali
within the limited scope recorded below; source completeness is not accepted.

## Facts and unresolved requirements

| Area | Verified basis | What remains unresolved |
| --- | --- | --- |
| Cost | PumpPortal documents 0.01 SOL per 10,000 token/account trade events and a funded linked-wallet condition | Actual billing granularity, in-flight accounting and an enforceable charge ceiling |
| Stream | FAQ describes processed commitment and live-only data | Finality reconciliation and recovery of early/missed events |
| Connection | Provider asks for one WebSocket; current scanner already owns one | Scope of the restriction across applications/keys/hosts; two independent clients are not assumed permitted |
| Existing creation evidence | Scanner projects optional signature, slot, decimal, actor, curve and reserve fields into `launch_registry` | Actual recent non-null counts on Kali; these fields remain unverified provider reports |
| Event identity/order | Required by the R1 reconstruction question | Complete trade schema, intra-slot and intra-transaction ordering, deduplication identity |
| Initial curve state | Needed for early-delay calculations | Same-transaction initial trades, subscribe-after-create gap and correct program/fee version |
| RPC reconciliation | Solana documents transaction-by-signature and block-by-slot methods | Existing provider access, quotas, coverage and preservation are not tested by this increment |

The provider's pages do not establish the complete event schema/ordering contract
needed here. This is a documentation gap, not proof that every required field is
absent. Existing creation metadata cannot validate a paid trade stream or recover
exact numeric lexemes already parsed by the scanner.

## Zero-spend evidence collection

The new host probe locates the running radar container by local Compose labels,
inspects only the matching `/app/data` mount and reads the newest at-most-128
retained creation records within 24 hours. It uses the receipt index, a three-second
read budget, 4096-byte rows, read-only/query-only SQLite and allowlisted table access.
It emits aggregate non-null/absent counts and freshness only. No outcome table,
model, trading API, provider connection or credential file is used.

The normal Docker data directory is a named volume, not necessarily the project
folder's `data/` path. The probe discovers that mount; it does not guess. If the
mount, index or read is unavailable, preserve the explicit unavailable report.

These metadata counts are feasibility diagnostics only. They do not reopen a
closed study or constitute untouched performance validation.

## Transport implementation and its limits

The injected-wire controller is implemented and offline-tested for a single
connection, bounded sends and receive polling, selective subscriptions, expiry,
migration unsubscribe, terminal capture budgets, failed cleanup and cancellation.
No automatic reconnect is allowed. A real network adapter is not implemented in
this increment. Provider acknowledgements and billing are never inferred from
successful local sends. The presence of this controller is not connection-policy
approval, and it does not solve coexistence with the existing scanner.

Do not solve coexistence by stopping the scanner, altering its discovery stream,
or creating another wallet/IP and assuming that exempts the experiment. Obtain
an applicable provider clarification or review a compatible architecture first.
No provider message was sent by this work.

## Next decision

Review the host metadata report and the new Kali tests. Then resolve the
connection policy and specify the smallest paid source-quality probe, including
the exact fields/reconciliation checks it must establish and its stop conditions.
The owner's willingness to fund data is not an approved numeric budget. The
proposed 0.05 SOL wallet funding / 0.02 SOL intended data charge remains a proposal.

Build/validation remains within the previously proposed five-working-day effort
cap; new metadata checks do not create additional open-ended research phases.
If feasibility cannot be justified, report the blocker and stop rather than add
an indexer or keep building speculative execution functionality.

## Sources checked

- https://pumpportal.fun/data-api/real-time/
- https://pumpportal.fun/FAQ/
- https://pumpportal.fun/fees/
- https://solana.com/docs/rpc/http/gettransaction
- https://solana.com/docs/rpc/http/getblock
- https://pkg.go.dev/github.com/docker/compose/v2/pkg/api (Compose label definitions)
- Repository: `scanner/src/adapters/pumpportal.js`,
  `scanner/src/core/launch-registry.js`, `scanner/compose.yaml`.

Only original provider/project documentation is used for the source claims.
Third-party example payloads were not treated as a guaranteed PumpPortal schema.

## Kali review of November 11 reports

Reviewed implementation: `55ddf7ac5e53a5b74e4e2d4b235a67ac520ebc77`.
Tree: `8a12f2f99c513931557b095842c186ad29b181fa`.

| Uploaded report | SHA-256 of exact uploaded bytes |
| --- | --- |
| `radar-r1-transport-20261111T073615Z-157358.json` | `44489b0c61ed89d18ce1ec04a047bb4441bfa3909d3787b1d1a20c73e5b3c758` |
| `radar-r1-source-20261111T073615Z-157358.json` | `d90275191663f67054b1ac03864230530ae1d8be3ff286e5a5f33fde7a2e5ea6` |

All nine offline-runner source hashes and both probe source hashes match the
published implementation. Python 3.14.6 / SQLite 3.53.4 passed 72 tests with no
failures/errors/skips. Runner duration was 1.196284 seconds; capture/restart/
terminal-budget/local-restore evidence remains consistent with the fixture.
This is an offline test duration, not a trading-latency measurement.

The source probe found the local data mount and read 128 valid creation records,
with no malformed or oversized records. Database-read duration: 0.035478 seconds.
Newest stored creation receipt was 15,692 ms before the probe cutoff; this is
receipt age, not provider or execution latency. No provider requests, credential
reads or outcome reads were reported.

| Retained creation field | Non-null out of 128 |
| --- | ---: |
| Signature | 128 |
| Reported trader | 128 |
| Reported initial purchase | 128 |
| Reported SOL amount | 128 |
| Bonding curve address | 125 |
| Reported virtual SOL reserves | 126 |
| Reported virtual token reserves | 126 |
| Reported slot | 0 |
| Reported decimals | 0 |
| Explicit reported creator | 0 |

Counts are per field; overlap of missing fields is not established. Non-null
means present, not correctly typed or independently verified. This bounded
retained-creation sample says nothing conclusive about the paid trade-stream
schema. It does not establish token arrival rate or the cost of a 21-day stream.

Decision: accept the offline transport-controller validation and metadata-probe
operation. Keep source completeness, real network adapter, provider coexistence,
billing, off-machine preservation and full R1 gate closure open. No funded
operation or PR/CI consolidation is authorized by these reports.

Next engineering target: a narrowly bounded RPC feasibility/reconciliation probe
using retained creation signatures, subject to confirming existing provider access
and quota. Determine whether transaction slot and program/mint initialization
facts can be recovered and verified; do not substitute reported trader for
creator or hard-code decimals. RPC facts would still need separate event-order,
fee-version and initial-state verification before simulation. No RPC call was
made during this report review. Connection coexistence remains a parallel
provider-policy question; another API key alone is not evidence of permission.

Acceptance is based on uploaded runner evidence and exact matching source hashes;
the reviewer did not independently connect to Kali or replay its private database.

## Third increment: bounded public RPC probe — Kali pending

Implemented `r1-data/rpc_probe.py` to answer the narrow missing-slot and
mint-initialization/decimals question. Existing Helius quota and credential access
have not been established. This increment instead uses the credential-free public
mainnet endpoint currently documented by Solana, `https://api.mainnet.solana.com`.
Public access is a feasibility path, not a production-capacity commitment.

The host probe reads up to three distinct creation identities from the existing
registry and issues at most nine read-only RPC calls within a 30-second network
budget. Read age is two minutes to 24 hours. No wallet/API key is loaded, no paid
stream is opened, and no simulation, signing or transaction submission occurs.
Redirects, proxies, retries and fallback providers are disabled. An endpoint
failure remains unavailable evidence, with no automatic spending escalation.

Required facts are finalized successful status, transaction signature/slot
agreement, mint membership, unique parsed standard SPL initialization, and matching
mint account program/decimals/initialized state at a sufficiently recent finalized
context. Mainnet genesis is checked before and after. The probe deliberately makes
no Pump creator identity, curve reconstruction, fee-version, event-order or
profitability claim. A latest finalized mint account is not a historical curve
snapshot. Matching provider responses are not independent cryptographic proof.

The private evidence bundle preserves selected source identities and successful
public responses. Errors are sanitized; failed provider bodies are discarded.
The summary includes code hashes, request counts, selected-case results and
compressed/decoded evidence hashes. The saved bundle is read back, checked and
replayed offline before reporting a replay pass. Unexpected failure preserves
actual request accounting and cannot produce a source pass. Local retention is
not acceptance of off-machine preservation.

Development validation: **101 tests**, zero failures/errors/skips, plus the
standalone capture/restart/limit/export/restore rehearsal passed on Python 3.12.14,
SQLite 3.53.1, with ResourceWarning treated as an error. The acceptance runner
completed in 0.566061 seconds using only synthetic fixtures. Its 11 source hashes
cover the two new RPC files. This duration is an offline test measurement, not a
public-RPC timing claim. The previously accepted capture, transport and metadata
probe implementations are unchanged. No live RPC request was made during this
development validation. Kali validation and actual source feasibility are pending.

Next host action: run the pinned offline runner, then the separate CLI with
`--read-public-rpc`. Upload the offline report and RPC `report.json`; retain
`evidence.json.gz` locally. A partial/unavailable report must be reviewed before
retrying or adding providers. A three-case pass only closes this narrow lookup
question; it does not close R1 or enable paid collection. Provider coexistence,
early-event recovery, complete ordering/initial-state evidence, the live adapter,
preservation and the explicit pilot budget remain open. No ML fitting is needed
for this increment, and no confirmation study is being started.

Primary protocol references used for this increment:

- https://solana.com/docs/references/clusters
- https://solana.com/docs/rpc/http/gettransaction
- https://solana.com/docs/rpc/http/getaccountinfo
- https://solana.com/docs/tokens/basics/create-mint

Development-branch publication is for Kali review only. There is no open PR for
this branch; the current workflows trigger pushes on main, PRs, or manual
dispatch. No PR, CI dispatch, merge, deployment or container restart accompanies
this increment.

## Third increment: Kali evidence accepted, 2026-11-11

Reviewed the three uploaded artifacts against implementation commit
`d880134cbd1ac184def442d78da7baf0b1a6f0fd`, tree
`562b568de9f751c41556632602b60f2ef317c1e5`. This acceptance supersedes the
Kali-pending status above for this narrow increment only.

| Artifact | SHA-256 |
| --- | --- |
| `radar-r1-rpc-offline-20261111T080728Z-226403.json` | `d1123fd68ac5b6d0222d98faf8fd2eca3f47478354886d5d40aeaa7f5276a0ca` |
| RPC `report.json` | `dcaf55dece8e1e53455b291340912bb03aec32d0093ce803f0f8ed1ac9434e66` |
| `evidence.json.gz` | `29ffa7dff87dc6d9ba29c81878d4540a943d4b9f8e993612d39cfba37a60e7ef` |
| Decoded RPC evidence | `ede0a9787d9adb0fa1d5ad238a6b76e3705d3e6321560dfbc83a178b81248a46` |

The Kali offline runner reports **101 tests, zero failures/errors/skips**, Python
3.14.6 and SQLite 3.53.4, in 1.289095 seconds. Capture preservation and local
restore/replay passed. All 11 source hashes exactly match the reviewed source;
the RPC report's three source hashes also match. No implementation change is
required by this evidence review.

The host selected three distinct records, with zero rejected records. Their
receipt ages at the selection cutoff were 122.114, 138.908 and 163.369 seconds,
within the required window. Nine requests were received successfully; their
individual reported durations sum to 2039 ms. That sum excludes deliberate
spacing, Docker discovery, SQL reads and file writes, so it is not end-to-end
runtime or deadline headroom.

| Case | Finalized transaction slot | Mint initialization | Decimals | Account context slot |
| --- | ---: | --- | ---: | ---: |
| 1 | 468050019 | Token-2022 `initializeMint2` | 6 | 468050605 |
| 2 | 468049941 | Token-2022 `initializeMint2` | 6 | 468050611 |
| 3 | 468049828 | Token-2022 `initializeMint2` | 6 | 468050618 |

All three version-0 transactions passed the implemented signature, successful
finalized status, slot, mint membership and unique initialization checks. Each
mint account matched its initialization program and decimals at a later context.
Mainnet genesis matched before and after. Six decimals is observed for these
three cases, not a general constant for future assets.

Reviewer verification used the uploaded private bundle: both compressed and
decoded hashes match the report, all nine request records match its accounting,
and offline replay with socket creation forbidden reproduces the complete
reconciliation exactly. The reviewer made no additional RPC request and did not
connect directly to Kali. This verifies transfer and replay of this specific
artifact; scheduled off-machine backup/restore for live capture remains open.

Decision: accept the bounded public-RPC lookup/reconciliation increment on Kali.
The tested endpoint returned the required narrow facts for these three sampled
creations. Source completeness, archival coverage, capacity, Pump creator
identity, historical curve state, fees, event ordering and profitability remain
unestablished. Full R1 remains open; no paid activation, ML fitting, PR/CI
consolidation, merge or deployment follows from this acceptance.

Next engineering target: inspect the saved creation transactions offline for
initial-purchase and curve-state evidence, and establish the required program
schema/version basis before implementing a decoder. No fresh host lookup or
repeat of this successful probe is needed for that inspection. Resolve the
existing scanner/provider connection policy before any live paid adapter.
