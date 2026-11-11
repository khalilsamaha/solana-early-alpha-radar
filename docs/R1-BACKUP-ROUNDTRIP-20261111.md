# R1 synthetic B2 round trip — development tested, Kali pending

Date: 2026-11-11. The handoff passed 198 Kali tests and its uploaded package
restored independently with identical database bytes and gap records. See the
[acceptance record](R1-CAPTURE-HANDOFF-20261111.md). This increment checks the
remaining storage-provider leg for that exact synthetic package only.

## Fixed scope

`r1-data/backup_roundtrip.py` accepts only the original 21,328-byte package with
SHA-256 `461fb7ad53f77879bbc6cf5554002e5578b5a75fc40de418f7c8216b03ab0ff4`
and the original top-level rehearsal report with SHA-256
`68d7ef0a660bfb3e0a38400c7dd44c83f6512e87fb9877c4675defe66ba0528e`.
Both files must satisfy the existing private-file rules. No real production
capture can be substituted by changing CLI arguments. Input validation and a
full local restore happen before any privileged subprocess.

The existing backup implementation, `operations-tools/quote_backup.py`, identifies
`radar-b2:solana-radar-backups-redeye-2026/quote-ledger/` and
`/etc/solana-radar/rclone.conf`. This check uses the same configured bucket with
a separate `r1-rehearsal/` prefix. Each invocation creates a 128-bit UUID object
name ending in the accepted package digest prefix. There is no user-supplied
remote/config argument, no bucket listing, synchronization, deletion or retention
change. No automatic repeat of a failed upload is performed. An uncertain upload
may have created an object and is retained as such in the diagnostic.

The upload primitive can overwrite an exact existing object name; fresh random
names make accidental collision negligible, but this is not a storage-provider
conditional-create guarantee or an immutable retention policy. The local receipt
records the chosen object so it can be audited later. The small object is left
in B2. Normal storage/API accounting may apply; no zero-cost guarantee is made.

## Privilege and command boundary

Python runs as the owner, not root. `sudo -v` establishes a credential cache for
the existing root-managed rclone configuration. Only the fixed sudo/timeout/
rclone command runs privileged. Executables and resolved parent paths must be
root-owned and not writable by group/others. The wrapper never reads or prints
the rclone config and supplies a minimal environment without inherited proxy,
rclone or credential overrides. It does not install/update software or services.

At most three subprocess operations are allowed, in order:

1. `listremotes --long`: require exactly one `radar-b2:` entry with type `b2`.
   Other metadata/descriptions are discarded and are never copied to the report.
2. `rcat`: upload only the already-validated bytes through stdin, with exact size.
3. `cat --count 21329`: read the same object through stdout. One extra byte is
   requested so an oversized object cannot be accepted merely by matching its prefix.

Privileged rclone never receives a user-controlled local input/output filename.
The owner writes the downloaded bytes privately and performs the restore.
Each invocation has a privileged GNU timeout of at most 40 seconds, TERM then
KILL after two more seconds, with an outer subprocess timeout. The transfer
session has a 135-second monotonic budget. Fixed rclone settings include one
worker/checker, bounded buffers, 64-KiB transfer ceiling, ten-second connection
and twenty-second I/O timeouts, and one attempt at each retry level. This limits
the workflow; it does not equate one subprocess with one B2 HTTP/API request.
Backend metadata output exceeding 4,096 bytes is rejected; downloaded output
is limited by `cat --count`. Raw stderr and exceptions are not retained.

Official command references reviewed on 2026-11-11:
[rcat](https://rclone.org/commands/rclone_rcat/),
[cat](https://rclone.org/commands/rclone_cat/), and
[listremotes](https://rclone.org/commands/rclone_listremotes/).

## Report meaning and host action

Run the 210-test offline suite from the pinned checkout. Then run the explicit
`--round-trip-b2` command against the original handoff directory
`radar-r1-handoff-20261111T132727Z-930958`. Do not create a replacement rehearsal.
The [README](../r1-data/README.md) documents the interface.

`synthetic-backup-roundtrip-passed-live-blocked` requires exact downloaded bytes,
matching original digest, restored database and semantic replay agreement.
`remote_download_verified` and `downloaded_capture_replayed` are then true.
The report pins three implementation sources and the original receipt. It
records operation states and the remote object, without credential contents.
Original input bytes and implementation hashes are rechecked before the report.

`synthetic-backup-roundtrip-unavailable` is a diagnostic with no acceptance.
It preserves completed-stage flags and whether an object may exist. Exit zero
means a diagnostic was retained; it does not mean the storage check passed.
Upload that report once rather than retrying or switching endpoints. No report
is a pass if input validation, source consistency or report creation failed.

Upload the offline report, new round-trip `report.json`, and `downloaded.zip`
when present. A successful check establishes one synthetic storage round trip.
It does not establish ongoing retention, automatic scheduling or protection of
future real R1 captures; those flags remain false. Original backup services,
production scanner and paid provider subscriptions are untouched.

## Development validation and continuation

**210 tests passed**, zero failures/errors/skips: 198 existing and 12 new tests.
The final runner used Python 3.12.14 and SQLite 3.53.1, ResourceWarning as an
error and an audit hook forbidding IPv4/IPv6 socket creation. It completed in
1.262185 seconds and pins 27 source files. Tests cover fixed inputs, preflight,
exact method order, stdin/stdout isolation, environment/timeout restrictions,
wrong or duplicate backend type, size/digest mismatch, process failures at every
stage, no retries/deletes, existing-output preservation and sanitized reports.

Integration with the actual uploaded package and **mocked** subprocess responses
passed all three steps, restored the original database hash and preserved the
source files. No real sudo/rclone process or cloud traffic was performed during
development. Actual B2 availability, privileges and configuration await Kali.

Once reviewed, proceed to the real collector adapter and connection-policy
decision, then the fixed pilot measurement contract and owner funding decision.
The original five-working-day engineering effort cap continues. Full R1 is
open; no PR/CI consolidation, merge, deployment, trading or ML fitting follows
automatically from a synthetic backup pass.
