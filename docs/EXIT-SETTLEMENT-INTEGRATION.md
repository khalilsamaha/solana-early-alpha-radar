# Connected exit settlement and scoped closure — November 2, 2026

The fresh exit transport host report passed all 21 cases at 07:42:19 UTC on
November 2 and exactly matched the portable contract. This next increment
connects that recorded exit to receipt reconciliation, fresh balance checking
and durable closure. It does not deploy or activate a trading service.

## Operation

`position-book/exit_settlement.py` provides an internal coordinator and a pinned,
read-only status. It operates on existing private journals, never imported public
reports. The host CLI only runs synthetic checks and accepts no operational flags.

`advance` first reads a coherent historical projection. It cannot manufacture an
entry, preparation, signature or send boundary. A recorded closed allocation
returns immediately without RPC. An incomplete signing stage also cannot advance
to submission here.

For an existing exit transport, the coordinator observes only its recorded
signature, then applies validated receipt effects. The default stops at accounting,
with all proceeds and unused fees held. Only exact `close_exit=True` requests the
separate fresh-balance closure gate. That gate requires a usable successful exit,
zero owned residual and no STOP. It independently checks the wallet, both token
accounts and both mints against collected receipt effects, then commits the raw
balance capture and scoped release together under the existing freshness limits.

At most four receipt reads and four balance reads occur in one call. There is no
polling loop, signer, sender or transaction retry. Receipt/accounting/closure are
separate durable stages: an exception does not imply earlier commits rolled back.

| Evidence or interruption | Result |
| --- | --- |
| Unknown or missing receipt | No closure; commitments remain held |
| Finality headers without supported effects | No invented token or fee accounting |
| Failed exit | Actual fee recorded; acquired inventory remains held |
| Conflicting effects | Quarantined evidence; no fresh closure |
| Accounting committed but caller response lost | Later reconciliation replays it without fetching the receipt again |
| STOP before new closure | Receipt settlement remains possible; balance collection/closure is blocked |
| Unexplained wallet credit or token change | Fresh balance gate fails; commitments remain held |
| Balance read, closure storage or freshness failure | Existing accounting survives; no inferred release |
| Closure committed but caller response lost | Inspection recovers the exact historical close; no second release or RPC |
| STOP or expiry after successful closure | Historical closure remains inspectable; no new spending authority |

Partial request counts survive later persistence failures. If a write may have
committed before an exception, its per-run applied flag and the final closure
claim are unknown (`null`), not falsely reported as rolled back. `inspection-required`
clears the current aggregate projection; a separate read-only status replays the
facts. The original admission history, entry accounting, signature and send records
are not rewritten.

## Release meaning

A pinned final projection binds the closure record to exact exit accounting and
independently checks aggregate conservation. It releases only that allocation's
actual source-token proceeds and unused native-fee commitment. It does not invent
repayment of the original principal, release protected inventory, sum different
assets, or credit a wallet-wide allocator.

`closed-scoped-commitments-released` is historical scoped accounting. It does not
mean the wallet is currently solvent or that funds are available for a new entry.
No new cycle, mainnet execution or profitability approval is introduced.

## Validation and next gate

The portable contract has 21 cases using public signed fixtures, temporary
journals and synthetic HTTP. It starts with the actual fresh-exit coordinator,
then exercises receipt reconciliation, closure choices and failures. It reads no
wallet key and creates no new signature or real request.

Local integration tests additionally exercise the actual isolated signer with a
disposable test key, a lost send response, exact collected receipt effects, fresh
balances, closure, historical source preservation, STOP recovery and isolated
snapshot verification. Focused regressions cover the two existing modules whose
internal progress counters were exposed: exit receipt recovery and closure.

All 36 targeted local tests passed: 12 connected settlement tests, 12 exit
submission regressions and 12 closure regressions. The two CI partition checks
and tracked-source hygiene check also passed. Host acceptance remains pending.

Run the pinned `position-book/exit_settlement_cli.py --output ...` command from
chat. Expect `offline-checks-passed` and 21 cases, then upload only its compressed
public report. No radar rebuild, restart or live wallet arguments are needed.

Next: instrument and exercise the connected separate-transaction lifecycle's
latency and operator recovery before exposing a narrowly scoped devnet acceptance
command. Mainnet route/economics validation, wallet-wide budgeting, pilot limits
and strategy qualification remain separate work.

The availability-study captures on November 3, 5 and 6, and review on November 6
at 00:05 UTC (01:05 Amsterdam), remain unchanged. No study rules, provider limits,
notifications, scanner code or backup settings changed in this increment.
