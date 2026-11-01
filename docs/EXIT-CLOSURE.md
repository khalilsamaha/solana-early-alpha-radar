# Durable scoped exit closure — November 1, 2026

The prior fresh balance collector passed all 18 Kali cases at
2026-11-01 07:43:01 UTC. The public report and source replay matched exactly.
This increment connects that internal collector to an atomic closure record in
the existing private admission ledger. It exposes only an offline self-check CLI.

## What closes

The recorded exit must have spent exactly the allocation's acquired quantity,
left zero owned residual, and preserved protected acquired inventory. A fresh
finalized five-account snapshot must still match the exact receipt-derived state.

One new SQLite row stores both the private balance capture and the scoped
settlement arithmetic. It records release of actual source-token proceeds and
unused fee commitments. Paid fees remain spent. The original input principal is
not credited again. Protected inventory is never released by this allocation.
All original admission, entry, exit and receipt records remain immutable history.

For example, the public synthetic fixture spends 100 source units and returns 96.
The close records 96 released proceeds, not a refund of 100 plus 96. Its original
26,000-lamport fee commitment partitions into 10,002 paid and 15,998 released.
Its 902 protected acquired-token units remain outside the released allocation.

This is a scoped accounting record, not a spendable portfolio balance. Existing
reservation readers remain conservative; no allocator consumes the new release
record. `fundsAvailableForNewEntry`, `nextCycleAuthorized`, wallet-wide knowledge
and execution approval remain false. No admission is reset for another trade.

## Atomicity and timing

1. A prior valid close is replayed without network requests or further release.
2. Otherwise, the internal collector performs at most four read-only devnet RPC
   requests. It never accepts a public report or external capture file.
3. After collection, the cooperating wallet lock and a SQLite `BEGIN IMMEDIATE`
   exclude other cooperating writers. An independent read-only connection replays
   the accounting, source identity and expected account state.
4. The private capture is checked again against that state and the current clock.
   Collection and commit preparation share a ten-second monotonic budget. This
   includes initial collector context work and is stricter than the collector's
   RPC-only start. It cannot extend the original wall-clock capture expiry.
5. The record, capture and release arithmetic are written in one transaction.
   STOP, wall-clock and monotonic checks run again immediately before COMMIT.
   Failed checks or storage exceptions roll back the whole transaction.

SQLite COMMIT itself can take time: this gate bounds the decision before commit,
not an unconditional disk-durability latency. No subsequent spending is permitted
from the capture. Actual host/RPC timing acceptance remains a separate gate.

Unexpected deposits, withdrawals, changed token controls, closed accounts,
failed exits, incomplete receipts, changed source identity or expired evidence
cannot close the allocation. A historical record remains readable after STOP
or expiry; this does not make its old balances current. Later conflicting source
evidence blocks semantic replay and preserves the stored row for investigation.

## Recovery

A caller that loses the response after a successful commit can use the read-only
status path; repeated close calls find the same record and make no RPC requests.
The combined private snapshot now includes the closure projection and replays its
raw capture and arithmetic in an isolated stopped restore. Rehashing a false
release amount or false account balance cannot bypass semantic comparison.
Checksums do not protect against malicious replacement of all trusted evidence.
The November 1 durable-STOP correction replays the captured admission identity
against its verified historical prefix. Every later admission event must be a
STOP-only change after closure; changed funding, request, signature or other
fields cannot be ignored. Current receipt/accounting evidence is still replayed,
so a later conflict remains blocking. The original closure row is never rewritten.
Local locks cannot prevent outside wallet activity or prove no net-zero activity
occurred between the receipt and the as-of snapshot.

## Local validation

55 targeted tests passed across closure (8), full-source stopped restore (1),
balance collection (8), existing admission recovery (19), and reservation views
(19). The closure CLI exercised all 21 portable cases. The final pre-commit clock
check was rerun after ensuring time spent checking STOP counts against expiry.

The full-source restore test exposed STOP rejection in the normal reservation
reader. A private closed-history mode now permits only a closed, zero-commitment
source; ordinary inspection and binding still reject STOP. Both paths are tested.
Historical semantic tests use a controlled clock; existing deadline/error checks
remain in place. These tests are not host performance or live RPC acceptance.

## Host check

Use the exact published commit, then from the running project directory:

```bash
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/exit_closure_cli.py" \
  --output "$PWD/radar-exit-closure-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, 21 cases. Public pre-signed fixtures and
synthetic RPC responses are used in temporary ledgers only. No existing wallet
key, actual network request, signature, transaction or production release occurs.
The public host report passed all 21 cases at 2026-11-01 08:04:24 UTC.
Exact source replay matched all expected cases and action flags.

The scanner, quote observer, signals, notifications and availability-study
registration are unchanged. No rebuild or service restart is required. Continue
captures on November 1, 3, 5 and 6. The November 6 final capture/review opens at
00:05 UTC / 01:05 Amsterdam.

## Next gate

After host acceptance, integrate one read-only end-to-end lifecycle projection
that reconciles admission, entry, exit and closure without contradictory current
reservation claims. Then test the complete delayed lifecycle against actual
bounded devnet timing before considering any new allocation or execution mode.
Strategy evidence and real-money readiness remain independent requirements.
