# Successor private snapshot and isolated restore rehearsal

The preceding completion rehearsal validates lifecycle and recovery projections.
This increment checks the full existing private snapshot capture/verify path with
successor signing, transport and accounting present. It changes no application
recovery contract and adds no operational backup or restore command.

The real-clock 1 MiB completion fixture is reused. After the one synthetic send
loses its response, the disposable key is removed and STOP is present. The
existing recovery capture creates a private snapshot of both source directories.
Both original directories are temporarily renamed inside the owned disposable
fixture while verification replays an isolated copy. The unknown send must
remain unknown, with its signer markers and held accounting preserved.

The normal synthetic receipt/accounting/balance path then completes. A second
full snapshot must restore the exact successor accounting identity and held
amounts without either original directory. Source and snapshot bytes must remain
unchanged; isolated restored copies must be stopped, contain no signing key and
leave no temporary restore directory. Neither operation releases commitments.

Two negative cases modify only the disposable snapshot. One changes the retired
fee exposure to zero and updates the accounting row hash and file inventory.
The other substitutes the successor identity in its signer marker and updates
the inventory. Semantic replay must reject both, despite valid file checksums,
without repairing or rewriting the altered evidence. This does not authenticate
against malicious replacement of the entire original history.

## Offline Kali acceptance

Run the pinned development source with:

```bash
python3 -B -E -s -W error::ResourceWarning position-book/successor_recovery_cli.py --output NEW.json.gz
```

Expected: `offline-integration-passed`, seven successor-load snapshot checks and
all 17 connected checks (the prior 12 completion checks plus five snapshot/recovery checks), both positive deadline
headrooms, every phase complete and private snapshot fixtures removed. The
snapshot operations happen after submission and do not extend its original
deadline. Balance freshness is independently measured after accounting.

The CLI accepts only a new report output path. Its reports omit private manifests,
raw receipts, signatures, wallet identities and source paths. All snapshots are
temporary and removed. Upload only the generated sanitized report and console
log, never an operational private snapshot or signing material.

This is another offline E0 acceptance boundary, not full E0 closure. It neither
refreshes operational state nor reconciles retired exposure. Operational action
requires separate scope; a full phase must pass Kali before PR/CI/merge clearance.

## Same-snapshot successor load

`successor_signing_handoff.load` now pins its full read in the existing query-only
SQLite snapshot. Lifecycle replay supplies the already-validated original
preparation, signed generation and not-attempted transport state to retirement
context construction. This removes one duplicate preparation replay per load
(three become two), without retaining evidence after the call. The successor
binding still performs its own original-preparation check.

Original backend attempt and acknowledgment files are reread, the clock is checked,
and retirement, successor and successor-signing records are fully validated.
New loads, writes, signer calls and RPC boundaries do not inherit this evidence.
The helper refuses a missing or writable transaction. Caller transaction and
query-only ownership are preserved even on failure. No deadline, freshness limit,
reservation, transport state or retired exposure rule changes.

The seven checks compare context and hashes with the previous load, count replay
calls, reject concurrent writes and later tampering, verify clock/backend checks
and STOP history, preserve transaction ownership, require a pinned snapshot and
reject orphan transport evidence before publishing reusable inputs. They run
with network connections denied before the connected recovery rehearsal; any
failure or skip blocks that rehearsal. The report records `loadSnapshotChecks`
and `successorLoadReplayVersion=successor-load-snapshot-1`.

Timing diagnostics identify repeated replay as a cost; they are not acceptance.
The full Kali rehearsal must pass with positive send and balance headroom on the
pinned source before accepting this increment. Local timing does not predict
Kali performance or establish operational readiness.
