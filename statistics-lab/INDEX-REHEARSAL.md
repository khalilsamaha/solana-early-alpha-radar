# Index rehearsal on a completed backup

Use this rehearsal before considering another live index migration when the
30-second build deadline is insufficient. It measures the same index builder on
a disposable copy of the latest completed **local scanner backup**. It does not
open the live database, stop or restart Docker, access Backblaze, change the
compact cache, or evaluate the frozen experiment.

Run once from the live project directory, using the pinned development commit
supplied in chat:

```bash
umask 077
radar_report="$PWD/radar-index-rehearsal-$(date -u +%Y%m%dT%H%M%SZ).json"
printf 'Report: %s\n' "$radar_report"
sudo python3 -E -s ~/apps/solana-radar-dev/statistics-lab/rehearse-index.py \
  | tee "$radar_report"
```

Upload the JSON even if the state is `stopped`. Do not automatically retry the
live installer. A completed rehearsal does not install anything on the scanner or
restore its statistics endpoint.

## Sequence and limits

1. Read `/var/backups/solana-radar/last-run.json`. Require a completed successful
   `host-snapshot-v1` backup, at most 36 hours old, with matching size and valid
   row counts. Refuse symlinks, hardlinks, external paths, and SQLite sidecars.
2. Require free space of at least twice the backup size plus 1 GiB on `/var/tmp`.
   The backup must be no larger than 16 GiB.
3. Copy in 1 MiB chunks into a private temporary directory. Open the original
   read-only and check its identity, size and modification metadata before and
   after copying. Verify SQLite integrity and manifest counts on the copy.
4. Enable WAL on the copy and use the same partial index builder, with a
   **180-second cooperative deadline for this disposable copy only**. The public
   live installer still has its 30-second deadline and 45-second process timeout;
   there is no public deadline override. Existing row, schema and WAL-growth
   checks remain enforced.
5. Verify integrity and counts again. Remove only the rehearsal's temporary
   directory, including after a child timeout. Preserve the original backup.

Copying and each integrity/count verification have 120-second cooperative bounds.
The parent limits the whole child process to 540 seconds, then removes its own
copy. Native I/O may delay cooperative checks; abrupt host failure or SIGKILL can
leave the private temporary directory behind. The worker uses lower CPU priority
and a 4 MiB SQLite cache. It still shares the host disk, so temporary I/O contention
is possible. Phase names are printed on stderr; stdout contains only public JSON.

## Interpreting evidence

`completed` requires successful index installation (or an already correct index),
matching row counts, passing integrity checks and unchanged original-backup file
metadata. Tests additionally compare original bytes; the host report's
`backupMetadataUnchanged` is a metadata check, not a cryptographic hash assertion.

The report separates copy, verification and index-build timings. Advisory cache
eviction applies only to the private copy, never global caches, and cannot
establish a truly cold disk benchmark. A backup's file layout and the live
workload can differ. Use timing to plan maintenance with margin; it is not proof
of live runtime performance. Production worker integration still needs its own
freshness, timeout and recovery verification.
