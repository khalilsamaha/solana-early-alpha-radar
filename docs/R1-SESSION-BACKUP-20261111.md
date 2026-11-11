# R1 complete-session B2 round trip — Kali and independent replay accepted

Date: 2026-11-11. This checks remote preservation of the newly accepted complete
synthetic session. It uses the existing B2 configuration and bounded transfer
runner. It does not activate a provider feed or change scheduled production
backups, retention, funding, CI or the R1 engineering effort cap.

## Complete-session acceptance and independent replay

Reviewed `radar-r1-session-offline-20261111T152417Z-1190598.json` and its uploaded
`session.zip` against commit `324a32e4a3755309fb1c1974315a9ad5427ab94d`, tree
`d3da6267cfb0c00dfc445c8821b61ac2c322a23f`:

- All 37 source hashes match; 275 tests, zero failures/errors/skips.
- Python 3.14.6 / SQLite 3.53.4 / websockets 17.4; 8.374058 seconds overall.
- One synthetic worker completed and was reaped in 0.515105 seconds.
- Exact report SHA-256: `2fe0273ec7850d5ceec9091f76bd57d6e72adddb5355558b4ef300ee81ed3196`.
- Exact archive: 27,148 bytes, SHA-256
  `f055648fdd804d29c1dfb25087c32314667b27fddb3adbf48db27e6617eb023d`.

The uploaded archive was copied byte-for-byte to a new private location and
independently restored in the development environment using the runner's
externally supplied checksum. Original attachments were not modified. Replay
matched all measurement fields and these component hashes:

| Component | SHA-256 |
| --- | --- |
| Restored SQLite database | `f6d6e25e7021797f854acc04a4ddcdabd9fa23b0780eeaf9f42e34667cfb010a` |
| Restored measurement journal | `197b9a9582f38c0c2f8491110b5dbd221350a14e7231867b9a8c198580983dd2` |
| Inner capture ZIP | `d30fb2d6dd261684f6931966d8663302243905af07df33489ea96d7421bca176` |

The capture has four messages/rows and zero gaps. The journal has nine records,
three local send completions and one selected creation, with no unresolved,
abandoned or selected-but-unsent subscription. The one synthetic local delay
is 29,216,145 ns; it is not a provider latency or trading performance result.
Provider acknowledgement, external denominator, initial-trade coverage and
actual billing remain unknown. The later B2 acceptance below establishes one
round trip of this complete archive, not scheduled retention.

## Implemented check and boundaries

`session_backup.py` accepts **only** the exact archive and original acceptance
report identified above. File sizes, checksums, private-file checks and complete
capture/journal replay must pass before backup credential access is attempted.
A new private frozen `source.zip` is retained. Any regenerated session, other
archive, changed report or substituted measurement is refused.

The earlier transfer runner now stores its expected archive hash, byte count
and object label on each instance. Its default profile retains the original
capture-only artifact and `handoff-` naming. The new fixed `SessionTransfer`
profile selects the accepted complete session and `session-` naming. There are
no new CLI arguments for arbitrary destinations, configuration, payload scope
or retries. The existing capture-only regressions still pass.

At most three fixed subprocess operations occur:

1. Verify that `radar-b2` is configured as a B2 backend.
2. Upload the validated 27,148 bytes via stdin to a fresh random object under
   `radar-b2:solana-radar-backups-redeye-2026/r1-rehearsal/session-...zip`.
3. Read back that same object, require exact byte equality, and restore/replay
   both its capture and measurement journal.

The existing root-owned sudo/timeout/rclone checks, fixed configuration at
`/etc/solana-radar/rclone.conf`, minimal environment, 40-second operation bound,
two-second forced-kill window, outer subprocess timeout and 135-second transfer
budget remain unchanged. Rclone receives no user-controlled local file path;
upload bytes use stdin and downloaded bytes use stdout. Python does not read
the backup credentials. Output/errors are not printed as raw diagnostics.

No retry, delete, sync, purge, alternate remote, automatic top-up or live feed
operation is available. An uncertain upload may have created an object: retain
it and the report instead of rerunning or deleting. Existing B2 storage/API
accounting can apply; this does not claim a cost-free operation.

## Development validation and completed Kali action

The suite now has **287 tests**, zero failures/errors/skips, including 12 new
complete-session backup tests. Those tests simulate the subprocess boundary;
they do not contact B2. Cases cover successful paired replay, exact fixed
commands/environment, checksum gates before credential access, mismatched
measurements, backend ambiguity, failure at each stage, altered/truncated/
oversized downloads, replay failure, profile separation, existing/unsafe paths,
missing executables, nonzero exits, required CLI flag and sanitized diagnostics.

The final development runner passed in 5.69843 seconds on Python
3.12.14 / SQLite 3.53.1 / websockets 17.4 with ResourceWarning treated as an error.

The actual uploaded archive/report also passed the new local preflight with a
deliberate offline stop before `trusted_programs`/credential access; no subprocess
or cloud request was made by that development check.

The following is the completed acceptance procedure, retained for audit. Do not
repeat the upload or regenerate evidence after the acceptance below.

Run the supplied pinned checkout command. First run the **287-test offline
suite**, expected `offline-session-backup-passed-live-blocked` and 39 source
hashes. Then run `session_backup.py --round-trip-b2` with the **existing**
accepted session/report paths. Do not regenerate a new bundle. `sudo -v`
authenticates for the existing rclone configuration; it is not an installation
or permission change. The original archive/report remain untouched.

Expected cloud result: `synthetic-session-backup-passed-live-blocked`, with
`remote_download_verified`, `downloaded_capture_replayed` and
`downloaded_measurement_replayed` all true. Upload:

- the 287-test offline JSON report;
- the new round-trip directory's `report.json`;
- its `downloaded.zip`, when present.

`synthetic-session-backup-unavailable` is a retained failure/uncertainty report,
not a pass. CLI exit zero only means a diagnostic was written. If unavailable,
upload the report once; do not automatically retry or change configuration.
Independent review will replay the returned archive against the original
checksum. Keep the resulting local evidence and any remote object.

## Kali and downloaded-archive acceptance — November 11

Reviewed implementation commit `58805ae660e8a62676e186a0d27b2eaa131e8b3b`,
tree `68b056c1ebffd41992c3477329d6793e41b80d3d`. Acceptance is based on the
uploaded Kali reports and independently replayed bytes; this review did not
access Kali or B2 directly.

| Evidence | Result |
| --- | --- |
| Offline report | `radar-r1-session-backup-offline-20261111T162204Z-1319631.json` |
| Offline report SHA-256 | `aef54ed7943c934929679029f44cb9fe4a4691456bb5f0634d7cd0c03c45948b` |
| Offline status | `offline-session-backup-passed-live-blocked` |
| Source identity | All 39 source hashes match the reviewed implementation |
| Tests | 287; zero failures, errors or skips |
| Runtime | Python 3.14.6 / SQLite 3.53.4 / websockets 17.4 |
| Whole-run duration | 12.934487 seconds |
| Supervised worker | Exited and reaped in 0.415909 seconds; one worker, no forced kill |
| B2 report attachment | `report(6).json` |
| B2 report SHA-256 | `fe380cabf65e0ab9bb905d1d788ea6dd9fbc71e07f344ef5fe665c4be8e92c66` |
| B2 status | `synthetic-session-backup-passed-live-blocked` |
| Operations | Backend check, upload, download: exactly three, all completed |

The whole-run duration covers the suite and rehearsals. It is not the worker's
12-second execution deadline; the worker completed in 0.415909 seconds.
The temporary offline session has a different checksum from the fixed B2
archive, as expected. It is not substituted for the original accepted session.

The B2 report's source hashes and original acceptance-report checksum match.
Uploaded `source(1).zip`, `downloaded(1).zip` and the previously accepted
`session.zip` are byte-identical: 27,148 bytes with the `f055648f...` checksum
recorded in full above. A new private byte-for-byte copy of the downloaded
archive was independently restored with that externally pinned checksum.
Capture and measurement replay exactly match the B2 report, including the
restored database hash in the component table above. The originals were not
modified. No provider or backup credentials were used for this independent replay.

Kali reports the retained remote object as:
`radar-b2:solana-radar-backups-redeye-2026/r1-rehearsal/session-e46e2e5bc47c4ea890111cecd5693168-f055648fdd80.zip`.
No deletion is requested. Keep the local evidence and remote object.

This accepts **one synthetic complete-session B2 round trip**. Actual live
capture backup coverage and ongoing retention remain unverified, as the report
correctly records. No additional synthetic backup test is needed now. The next
work is the connection/readiness decision in `R1-LIVE-READINESS-20261111.md`.

## Remaining decision

This successful result covers one accepted synthetic complete session only.
Actual live-capture scheduling, preservation coverage and retention remain
unverified and are explicitly false in the report. The provider connection
model, private credential/exposure controls, fixed measurement registration,
real host TLS/session validation and owner's numeric funding decision remain
prerequisites for live activation. No provider clarification was sent by this
work. Full-gate Kali acceptance still precedes PR/CI consolidation and the
owner's merge decision. The original five-working-day effort cap is unchanged;
blockers at that cap require scope reassessment, not automatic extension.
