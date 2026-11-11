# R1 complete-session handoff — Kali and independent replay accepted

Date: 2026-11-11. This closes the local packaging gap between the capture and
its measurement journal. It continues the existing R1 phase and effort cap;
it does not authorize live collection, establish remote retention or close R1.

## Complete-session acceptance

The 275-test Kali report for `324a32e4a3755309fb1c1974315a9ad5427ab94d`
passed review, with all 37 source hashes matched. Report SHA-256:
`2fe0273ec7850d5ceec9091f76bd57d6e72adddb5355558b4ef300ee81ed3196`.
The uploaded 27,148-byte `session.zip`, SHA-256
`f055648fdd804d29c1dfb25087c32314667b27fddb3adbf48db27e6617eb023d`,
was independently restored. Database, journal, inner archive and all measurement
results match the Kali receipt. This accepts the transferred synthetic complete
session; its B2 round trip is next, documented in `R1-SESSION-BACKUP-20261111.md`.
The following records the completed handoff increment.

## Accepted measurement evidence

Reviewed `radar-r1-measurement-offline-20261111T150933Z-1157551.json` against
commit `ccf8085860deb3fc0a508f540e5ff41cf447c921`, tree
`fe81771ea531e233c4a14b71e7cbcb9bf48b94b2`:

- Exact report SHA-256: `81a3135241cf1f3f39d37155193f04659e098d4af581cfd2cfb78e5c7855be2c`.
- All 35 source hashes match; 259 tests with zero failures/errors/skips.
- Python 3.14.6 / SQLite 3.53.4 / websockets 17.4; 9.625006 seconds overall.
- One worker completed and was reaped in 0.466565 seconds. Capture preservation,
  local restore, journal copy and measurement replay all passed.
- Three local send completions; one selected creation; no unresolved/abandoned
  sends or selected-but-unsent creation. The nine-record synthetic journal
  measured 2,112,470 ns for its one local receive-to-send-return delay.
- That synthetic local delay is not a live-provider latency benchmark. Provider
  acknowledgement, external denominator, initial-trade coverage and actual
  charges remain null; finality and ledger-order verification remain false.

Acceptance is for the uploaded report and matching sources. The temporary
fixture was removed as documented, so these bytes were not independently
replayed here. The new retained complete-session artifact enables that review.

## Complete archive and binding

`session_bundle.py` exports one `session.zip` containing exactly three members:

| Member | Purpose | Maximum uncompressed bytes |
| --- | --- | ---: |
| `capture.zip` | Existing accepted two-member database/manifest package | 33,574,912 |
| `session.jsonl` | Complete local measurement journal | 8,388,608 |
| `binding.json` | Version, producer source pins, both hashes and both replay results | 65,536 |

The outer package adds a bounded 4,096-byte envelope allowance. Both ZIP levels
use stored members without compression. This leaves the accepted capture-only
handoff and fixed B2 probe unchanged. The complete session is a new artifact;
the older B2 receipt does not cover it.

The producer creates a closed capture package, verifies the journal against
that capture, builds the binding and restores the complete archive locally
before reporting success. Export rechecks the original database and journal
bytes. The worker separately restores its retained archive; capture and
measurement reports must match. Its supervisor receipt includes the complete
archive checksum, size and replay result.

Restore requires an **externally supplied original archive SHA-256**, obtained
from the trusted runner receipt. An embedded self-consistent checksum alone is
insufficient. Restore checks the ordinary ZIP directory count/size before
parsing, member allowlist, regular/private file metadata, stored method, byte
caps, CRC and canonical package encoding. It rejects extra/missing members,
path traversal names, symlinks, ignored prefixes/trailers and noncanonical ZIP
metadata. Only fixed filenames are written into a new private directory.

The inner capture replay and measurement replay are independently recomputed
and compared with the binding. A substituted journal, forged acknowledgement
count, false capture report or truncated journal cannot pass by updating only
the outer checksum. Producer pins must match this reader's implementation;
future reader/source upgrades require an explicit compatibility review.

The source archive and existing output paths are never replaced or deleted.
A failed restore may retain a partial new output directory but has no successful
terminal report. Hashes bind reviewed bytes; they are not external signatures
or proof of feed completeness, timestamp truth, subscription acknowledgement
or billing correctness.

## Resource adjustment

The worker's per-file RLIMIT_FSIZE is now **44 MiB**, raised from 36 MiB so the
bounded combined archive can be written. The maximum outer package is below
that ceiling. This is not a total-directory quota. Capture DB/raw/message caps,
journal caps, 256 MiB address-space limit, five-second CPU cap, ten-second child
alarm, twelve-second parent wait and cleanup windows are unchanged. The real
child resource-limit test now checks 44 MiB. Maximum-size production-session
performance and scheduled retention are not established by a four-frame fixture.

## Kali validation and transferable evidence

Development suite: **275 tests**, zero failures/errors/skips. New cases cover
complete-pair export/restore, exact source preservation, deterministic packaging,
mandatory external checksum, missing/substituted/rebound journals, forged replay
claims, malformed ZIP metadata, directory/size caps before parsing, source-version
mismatch, unsafe/reused outputs, report-write failure, sanitized CLI failures,
retained artifact integrity and supervisor rejection of a changed complete bundle.

The final development runner passed in 5.453804 seconds on Python 3.12.14 /
SQLite 3.53.1 / websockets 17.4 with ResourceWarning treated as an error. Its
27,122-byte retained synthetic archive also passed a separate restore CLI
invocation with the externally supplied checksum and matching measurement result.
This is a separate local consumer check, not off-machine transfer acceptance.

The runner now pins **37 sources**. Its new optional argument
`--session-artifacts /absolute/new/directory` retains the private synthetic run
and writes a convenient `session.zip` at that directory's root. Without it,
existing temporary-fixture behavior remains unchanged. The option refuses an
existing path. All retained material comes from the fixed four-frame synthetic
worker; no production database or credential is read.

Run the supplied pinned Kali command and upload these **two files**:

1. The offline JSON report, status `offline-session-bundle-passed-live-blocked`,
   275 tests and `supervision.worker_receipt.complete_session_replayed: true`.
2. The retained directory's `session.zip`. Its bytes must match
   `supervision.worker_receipt.session_bundle_sha256` in that report.

Keep the private retained directory on Kali. Independent review will restore
both the capture and journal from the uploaded archive and compare the results.
Until that occurs, no independent-transfer acceptance is claimed. No cloud
round trip, provider connection, key input, funding or scanner restart is requested.

For later explicit offline restore, the interface is:

```sh
python3 -E -s -B -W error::ResourceWarning r1-data/session_bundle.py restore \
  --bundle /absolute/received/session.zip \
  --expected-sha256 ORIGINAL_RUNNER_SESSION_BUNDLE_SHA256 \
  --output-directory /absolute/new/restored-session
```

## Remaining critical path

Resolve the provider's permitted connection model before any live collector
connection. Complete private credential/exposure controls and the registered
measurement terms, validate actual host TLS/session behavior under that model,
and cover complete-session artifacts in off-machine preservation and retention.
The owner's numeric funding decision is still required before paid activation.
The earlier capture-only B2 check must not be rerun as proof of complete-session
coverage. No ML fitting, production change, PR/CI consolidation or merge is
performed here. Full-gate Kali acceptance and the owner's merge decision remain
separate. The original five-working-day build/validation effort cap is unchanged;
unresolved blockers at that cap require reassessment, not automatic extension.
