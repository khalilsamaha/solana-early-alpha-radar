# R1 source feasibility — documentation and bounded host probe

Date: 2026-11-11. Status: **source feasibility not established; live blocked**.
The 44-test offline core is accepted on Kali. The second implementation increment
adds a transport controller exercised with fake wires and a read-only host probe.
Neither opens PumpPortal or spends money. No scanner/runtime/frozen-study changes.
Local validation: 72 tests and the standalone acceptance runner passed on Python
3.12.14 with ResourceWarning treated as an error. The previously Kali-accepted
`capture.py` is byte-identical; the new controller/probe still need Kali review.

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
