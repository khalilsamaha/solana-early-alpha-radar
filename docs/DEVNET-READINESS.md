# Local devnet readiness inspection

This release consolidates the fixed two-cycle rehearsal into one read-only
operational evidence report. It replays the four retained entry/exit journals,
checks the cycle-two cumulative spending guard, validates receipt continuity,
and compares the separate two-cycle historical ledger with that evidence.

It does not assess scanner health, current wallet balances, profitability or
strategy qualification. The frozen forward study remains a separate review.
`closed-evidence-consistent` means only that the retained local evidence agrees.
`tradingReady`, `executionApproved` and `nextCycleAuthorized` remain false.

## Run

Use the development checkout; no installer, service restart or container rebuild
is needed. Run as the owner of the private rehearsal directory, without sudo.
First run the disposable synthetic self-check:

```bash
python3 -E -s position-book/readiness_cli.py --output /path/outside-rehearsal/check.json.gz
```

Then inspect using the already established directory, wallet and pool:

```bash
python3 -E -s position-book/readiness_cli.py \
  --action inspect \
  --directory /path/to/private-rehearsal \
  --wallet YOUR_EXISTING_DEVNET_WALLET \
  --pool YOUR_EXISTING_DEVNET_POOL \
  --output /path/outside-rehearsal/readiness.json.gz
```

Outputs must be new files outside the rehearsal directory. The self-check runs
16 synthetic cases; it does not access an existing wallet or public RPC.

## Interpretation

| Finding | Meaning and next action |
| --- | --- |
| `closed-evidence-consistent` | Four successful finalized receipt replays, closed and clear spending reservations, verified continuity, matching historical ledger, no STOP. No execution permission is granted. |
| `review-required` | One or more explicit `blockingReasons`; exit status 2 after publishing the report. Preserve source files and review `nextActions`. |
| Unresolved submission | If a recorded signature or submission boundary supports it, recommend the existing read-only recovery path. Never repeat execution to retry. |
| Missing historical ledger | If source receipts validate, recommend the separate accounting sync. This checker never creates the ledger. |
| Missing or invalid evidence | No inferred transaction failure or synthetic balance. Preserve the journals for investigation. |
| STOP, quarantined book, mismatched accounting | Report and retain the state. No automatic clearing, reset or quarantine mutation. |
| SQLite recovery files | Refuse database access without removing or recovering those files. Preserve them for investigation. |

The report omits wallet/pool addresses, transaction signatures, balances, signed
wire data and raw exception text. A failed check is not a reason to delete state.

## Read-only guarantee and scope

The shared wallet lock excludes cooperating execution processes. Connections in
the inspection scope use SQLite `mode=ro` and `query_only=ON`; missing databases
cannot be created, and inspection cannot change schema or journal mode. Existing
`-journal`, `-wal` or `-shm` files cause refusal. The checker deliberately avoids
`immutable=1`, which could hide recovery evidence and bypass normal locking.

This mode is scoped to new journal connections in the current context. Existing
execution tools retain their normal durable write transactions. The inspection
uses local recorded receipts only: no signing key access, RPC, submission,
automatic recovery, current balance query, third-cycle preparation, notification
or source-state repair. It is not a defense against a malicious concurrent
process that ignores the shared lock.

Tests cover unchanged source bytes, idempotent inspection, unavailable evidence,
unknown outcomes, STOP, accounting quarantine, recovery files, explicit identity,
lock contention and sanitized reports. Separate journal tests verify that even
disabling `query_only` cannot write through the underlying read-only connection.
