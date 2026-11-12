# R1 complete and interrupted evidence preservation

Kali accepted the draft measurement evaluator at
`268c03ad259174a07df2090916cfd1988d54f282`: 314 core checks, 18 contract
checks, 147 matching source hashes and the exact frozen draft. Runner time:
19.501578 seconds. Both reported evaluator outcomes were independently recomputed.
The normal small fixture is insufficient; deliberate cleanup failure is fail.
This acceptance validates the evaluator, not its draft terms or live authority.

Exact accepted report SHA-256:
`9a951ba30fc79f6e5369bed9bfad85d965b0eabb7c9f5deb3018283d95296275`.
Exact contract SHA-256:
`c9468e251bd2ed9a6d51c19e907b5421b022eec5a93960ad3ae6726b81575202`.
Both original files are retained under `../docs/evidence/`.

## Scope

Existing session export requires a complete, replayable capture/journal pair.
A process killed during capture can leave an active database, unfinished send
intent, torn journal or SQLite rollback file. This increment adds a separate
local evidence archive which preserves those bytes without making an interrupted
capture look complete. It is a preservation primitive and offline checker, not
an installed production finalizer, remote backup service or retention schedule.

Only fixed evidence roles are read: frozen contract, lifecycle claim/journal,
SQLite database and optional rollback file, and measurement journal. No directory
recursion, environment files, key stores, arbitrary log files, live-provider access,
Docker operations or production paths are used by the checker. All its evidence
is synthetic. A future real-evidence integration must keep quarantine archives
private and review their handling; the local primitive performs no remote upload.

## Consistent source snapshot

The preserver acquires exclusive, nonblocking locks on the **existing** stable
lifecycle registry lock and capture lock. It never creates a missing source lock.
An active cooperating coordinator/writer causes refusal, not a forced snapshot.
Lock/file ownership, modes, link counts, identities, directory identities and
bounded file bytes are checked. Source contents are checked again before release;
lock identity validation completes before a successful output is published.

The source database is read as raw bytes, never opened through SQLite. Replays
use disposable copies. A present rollback file, including an empty one, is retained
exactly and skips SQLite replay entirely. No rollback recovery, journal truncation,
file repair, counter reset, automatic resume or restart is performed. Locks cover
cooperating processes using these exact locks; this is not protection against a
malicious same-user process or a stopped machine's disk failure. A failure before
required lock creation needs manual reconciliation and is refused by this primitive.

Symlinks, hardlinks, special files, unsafe permissions, unsupported capture members
(including WAL/SHM), oversized data, source mutation, source-path output nesting,
wrong external checksums and output replacement are rejected. Unrelated files in
other source folders are never included. Missing optional evidence is explicitly
listed as absent, not fabricated.

## Archive and classification

The archive is a canonical, uncompressed ZIP containing fixed flat members and
an integrity manifest. It binds the current implementation hashes, contract hash,
each member's exact size/hash, absent roles and a recomputed assessment. File caps:
32 MiB/database, 32 MiB + 4 KiB/rollback file, 8 MiB/measurement journal, and small
bounded contract/lifecycle/manifest metadata. Directory count and metadata are
bounded before ZIP entry allocation. Compressed entries, path traversal, duplicate
members, changed assessments, extra headers/trailers and incompatible source pins
are rejected. Restore requires an externally supplied archive SHA-256, writes only
fixed names and verifies the assessment again on disposable copies.

| Classification | Required evidence |
| --- | --- |
| `complete-replayed-evidence` | Valid current contract, matching lifecycle contract/source binding, complete lifecycle, no rollback file, and a terminal capture/journal pair that fully replays |
| `quarantined-incomplete-evidence` | Any missing, incomplete, mismatched, corrupt or unreplayable component, or any preserved rollback file |

A complete archive is not a local-quality, source-adequacy or profitability pass.
The frozen contract remains unapproved. All archives forbid automatic resume and
live activation. Restored files deliberately use flat evidence names rather than
a runnable capture directory. Hashes detect mismatches against retained bindings;
they do not authenticate an operator or establish trustworthy precollection time.

## Kali rehearsal

`check_preservation.py --output-directory NEW_PRIVATE_PATH` runs 314 core and
18 preservation checks, then three full preservation/restore scenarios:

1. A native writer completes four synthetic records and a complete measurement
   journal. Its evidence must fully replay.
2. A native writer is SIGKILLed after durable creation/selection/send intent,
   leaving an unfinished capture and lifecycle retirement intent. Both remain
   quarantined, byte-for-byte unchanged.
3. A native writer is SIGKILLed during an actual uncommitted SQLite transaction.
   Its real rollback file is retained exactly and never opened for recovery.

The writer has the accepted offline resource, parent-death and no-network/no-child
profile. All fixture processes must be reaped. Lifecycle service actors are the
previously tested native stand-ins: handoff/network/restart policy are simulated
in this preservation fixture. The accepted actual Docker/Unix handoff at
`a0003221` remains separate evidence and is not rerun or claimed anew.

Upload `report.json`, `complete-evidence.zip`, `interrupted-evidence.zip` and
`rollback-evidence.zip`. Expected runner status:
`offline-preservation-passed-live-blocked`. Expected case classifications are one
complete and two quarantined; quarantine in these deliberate crash cases is a
successful preservation result, not a successfully completed collection.

## Remaining integration

Kali acceptance of this increment is required. Next wire preservation into the
production admission/stop/reconciliation design, cover failed finalization and
remote-upload outcomes, and establish real-session retention and independent
restore. The previously accepted one-off synthetic B2 round trip does not prove
ongoing coverage. No new B2 transfer, funded provider session, production restart,
ML fitting or trading is requested here. Numeric exposure and the measurement
terms still require owner review before activation. Full-gate Kali acceptance
precedes PR/CI consolidation and an owner-approved merge. The existing total
five-working-day R1 engineering effort cap remains unchanged.
