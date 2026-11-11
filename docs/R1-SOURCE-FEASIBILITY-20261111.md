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
