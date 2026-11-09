# Exact local scanner backup preservation

Use a reviewed backup's device/inode identity from its retention inventory to
select that exact file, rather than guessing a filename or selecting a newer
backup. `operations-tools/preserve_scanner_backup.py` searches only the supplied
backup directory, capped at 512 entries. It refuses ambiguous identity, symlinks,
recent/future-dated sources and SQLite sidecars.

The source is copied into a new private directory outside routine backup rotation.
The source hash is computed during copying; a separate reread verifies the copy.
Source device/inode, size, modification time and change time must remain stable.
Original file permissions and contents are preserved. Destination creation never
replaces an existing file or directory. An interrupted or failed run leaves its
incomplete copy for inspection and does not emit a successful preservation report.

This offline copy operation has an 8 GiB source limit, a 180-second combined
copy/verification budget and a free-space check. It uses bounded streaming reads
and explicitly closes its files. These are separate limits for copying a backup;
the launch audit's ten-second database-read deadline remains unchanged.

`preservation.json` records the SHA-256, bytes and source identity after successful
verification. This proves byte equality with the selected local backup, not with
the running database. It does not establish SQLite integrity, payload validity,
cloud recoverability or uninterrupted collection. No pruning, installation,
restart, cloud call or service change is performed.

Run the existing launch feature audit against the preserved `scanner.sqlite` with
`--database`, keeping the full requested window. If that audit times out or fails,
the byte-preserved copy remains available and the feature audit remains incomplete.
Keep both the preservation result and any subsequent failure evidence. Upload only
the small reports and validation log, not the database itself.

Regression checks cover independent copy survival after original removal, hash
verification, mutation/corruption detection, limits, deadlines, sidecars, symlinks
and refusal to overwrite. Kali acceptance is required before this increment is
accepted; it does not by itself close the baseline engineering phase.
