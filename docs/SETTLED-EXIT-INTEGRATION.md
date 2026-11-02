# Collected entry settlement and delayed exit integration — November 2, 2026

The fresh entry sender host gate passed all 21 cases at 06:58:18 UTC on November 2.
The uploaded report exactly matched the portable check contract. This increment
connects its durable entry state to collected receipt accounting and a separately
collected unsigned exit. It does not run the live sender or change the radar.

## Connected behavior

`position-book/settled_exit.py` adds an internal coordinator and a read-only
combined status. The public CLI only runs synthetic checks.

`advance` first observes the already-recorded entry signature, using the existing
bounded receipt collector. It never calls the entry signer or sender. It then
applies entry accounting in the same admission ledger. RPC acknowledgment alone
cannot create a position: supported collected finalized receipt effects must
establish the exact token delta and paid native fee. Failed entries retain their
unspent principal; missing and conflicting evidence cannot be treated as a zero
return or as permission to exit.

By default the coordinator stops after reconciliation. The internal caller must
explicitly pass `prepare_exit=True` to request the separate unsigned exit
observation. That step requires usable open-entry accounting, no STOP and no
existing exit preparation. It collects new pool/account/blockhash/fee/simulation
evidence and atomically records the prepared exit and its provenance.

The exit quantity is exactly the acquired delta. Existing tokens and surplus
inventory are protected, and the next exit's fee cap is separated from all other
held fees. Entry evidence and the entry's expired deadline are never reused as
fresh exit evidence. The exit has its own existing ten-second collection deadline;
this does not refresh or authorize the earlier entry.

The composition allows at most four receipt requests plus twenty exit observation
requests per call. There is no polling loop, artificial waiting period, automatic
retry, exit signing or transaction submission. A caller can reconcile now and
explicitly request a fresh exit observation later. This mechanism does not choose
a trading horizon, take-profit rule or stop-loss policy.

## Durable state and recovery

Receipt capture, entry settlement and exit preparation are separate durable
stages. They are deliberately not presented as one cross-network transaction.

| Interruption or result | Retained state and next behavior |
| --- | --- |
| Entry outcome unknown | Reservations remain held; no exit collection |
| Entry failed | Actual fee recorded, unspent principal held, no acquired position |
| Accounting write fails | Collected receipt remains; later reconciliation replays it without another send |
| Exit RPC, freshness or inventory check fails | Settlement remains; no exit preparation is created |
| Exit record write fails | Exit transaction rolls back; earlier settlement remains |
| STOP appears | Receipt/fee reconciliation remains possible; new exit collection/preparation is blocked |
| Exit preparation already exists | Replayed without RPC; expiry cannot trigger replacement or refreshed evidence |
| Terminal repeated reconciliation | No duplicate fee accounting and no additional receipt requests |

A final read-only projection opens accounting and exit preparation under one
cooperating source lock. It verifies their accounting hash, receipt identity,
acquired quantity and remaining fees match. Source journals and original admission
commitments remain historical. No budget is released for another entry.

The two small integration seams expose only internal progress: the receipt
collector makes its request counter available, and the exit coordinator exposes
its sanitized observation before the persistence step. These preserve accurate
request counts when a later write fails. Standalone behavior and existing caps
are unchanged.

On a caught error, `inspection-required` does not imply earlier work rolled back.
Use the internal read-only `status` to replay durable facts. Reports are evidence,
not importable signing capabilities. Local locks do not prevent unrelated external
wallet activity and do not establish wallet-wide solvency.

## Validation

Local validation passed 59 targeted tests: 12 coordinator tests, 17 accounting
tests, seven collected-exit tests and 23 submission tests. Two CI partition
checks also passed.

The new portable gate has 18 cases using public signed fixtures, temporary ledgers,
actual parsers and fake HTTP responses. It connects the preceding fresh-entry
coordinator to receipt settlement and actual delayed-exit collection. No wallet
key is read and no signature or network transaction is created.

Local tests also cover the combined 24-request path, accounting/receipt/exit commit
failures, STOP between stages, a mismatched accounting identity, repeated recovery,
private exclusive CLI output and rejection of operational CLI flags. The existing
accounting, submission and collected-exit suites are regression gates.

Run the pinned `position-book/settled_exit_cli.py --output ...` command supplied in
chat. Expect `offline-checks-passed` and 18 cases. Upload only the compressed public
report. No wallet arguments, rebuild, restart or runtime installation is needed.

## Remaining acceptance sequence

The November 2 host report at 07:13:54 UTC passed all 18 cases and exactly matched
the portable contract. The three-increment consolidation is now prepared.

1. Accept this synthetic host report, then consolidate the three development
   increments since PR #70 with the agreed grouped CI checks.
2. Connect this fresh exit preparation to the restricted exit signer and one-send
   transport, preserving its own original deadline and recovery boundaries.
3. Exercise final receipt accounting, post-exit balances and scoped closure across
   the connected lifecycle before exposing a narrowly scoped devnet command.
4. Measure host/provider latency and run the explicitly scoped devnet acceptance.
   Mainnet route validation, pilot controls and economic qualification remain
   separate work; engineering success alone establishes no profitable strategy.

The November 3, 5 and 6 study captures and November 6 00:05 UTC review are unchanged.
