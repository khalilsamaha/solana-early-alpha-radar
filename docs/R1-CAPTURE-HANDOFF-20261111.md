# R1 capture handoff — Kali accepted and independently restored

Date: 2026-11-11. This is the next independent engineering increment after
the [partial source-feasibility verdict](R1-SOURCE-VERDICT-20261111.md).
It packages an accepted closed capture for transfer and restores returned
bytes against a separately retained expected checksum. It does not contact a
storage provider or change the running scanner's backup configuration.

## Interface and evidence

`r1-data/handoff.py` has three explicit operations:

| Operation | Inputs | New outputs |
| --- | --- | --- |
| export | Closed R1 capture directory | Private directory with capture.zip and report.json |
| restore | Private package, expected SHA-256 from original trusted receipt | Private directory with restored capture and report.json |
| rehearse | New output directory only | Four synthetic events with a restart gap, export package, local restored copy and summary report |

Export uses the existing accepted capture verifier/exporter, then validates a
full restore before writing the package receipt. The source database must remain
byte-identical. The package uses ZIP_STORED (no compression), fixed timestamps,
exactly `ticks.db` and `manifest.json`, and fixed private regular-file metadata.
It is deterministic for a fixed capture snapshot. No file path supplied inside
an archive is extracted with `extractall` or used as an arbitrary destination.

Restore requires a lower-case 64-character expected SHA-256. It hashes the full
returned package before parsing; calculating a new hash from the returned file
and using that as the expectation would defeat the transfer check. Obtain the
expected value from the original retained export report. The package is bounded
to 32 MiB plus a 16-KiB manifest and 4-KiB container allowance. The ordinary ZIP
end record must describe two entries and at most 512 bytes of central-directory
metadata before the ZIP parser allocates member objects. ZIP64, multiple disks,
comments, extra fields, compression, encryption flags and symbolic links are
unsupported. CRC and full-package checksum failures reject the restore.

Manifest JSON is strict, with exactly version, database hash and capture report.
The database hash must agree. The restored SQLite database then passes the same
integrity, row-chain, mint-decision and gap checks as the original capture, and
the report must match its manifest. Database bytes are checked after restore;
the input package must remain unchanged. A new report is written only after all
checks and before/after code hashes pass. Interrupted work can leave a partial
new directory without a report; this is not acceptance and is never overwritten.

Files must be private regular files owned by the current user, with one link;
symlink paths and aliased parents are refused. File identity/size/modification
metadata are checked across bounded reads. New directories use mode 0700 and
files mode 0600. Original captures, packages and existing output paths are
preserved. Errors use fixed messages without echoing paths, arguments or raw
exceptions. Neither report nor standard output includes raw provider frames.
The package itself contains capture records, so real packages remain private.

## Accepted scope versus remote preservation

`capture-export-ready-live-blocked` means the package was produced and locally
restored successfully. `capture-restore-replayed-live-blocked` means returned
bytes matched the expected package hash and replayed. The synthetic rehearsal
returns `offline-handoff-rehearsal-passed-live-blocked`, retaining its four
messages, one restart and one gap through the package round trip.

All modes set network/credentials/paid-collection/profitability flags false.
They also leave `off_machine_restore_verified`, `remote_upload_performed` and
`remote_download_verified` false. A caller choosing a filename called returned
is not evidence of remote transfer. Hash agreement is not independent source
authenticity if both a package and its receipt can be replaced together.

For Kali acceptance, run the full offline suite and `handoff.py rehearse` in a
new directory. Upload the offline report, rehearsal `report.json` and its
`export/capture.zip`. The package is entirely synthetic and contains no real
wallet credentials. It enables a subsequent independent-host replay. An actual
storage-provider round trip still requires a separate upload/download receipt,
the original expected hash and the downloaded object. No B2 destination is
guessed or automatically written by this implementation.

## Validation

The new tests cover deterministic private packaging, exact copied-byte restore,
original-input preservation, wrong/missing/malformed expected hashes, swapped
valid captures, manifest/report/database tampering, duplicate JSON keys, invalid
version types, traversal/extra/duplicate archive members, compressed payloads,
input/member/directory-allocation caps, CRC corruption, symbolic-link members,
unsafe permissions/hardlinks/alias parents, active-writer export refusal,
source changes, preservation of existing outputs, synthetic restart gaps and
sanitized CLI failure. Existing accepted capture/transport/RPC/inspection code
is unchanged. Nested export destinations inside the source capture are rejected
before any directory creation, preserving source usability.

**198 tests passed**, zero failures/errors/skips: 181 existing and 17 new checks.
The final runner used Python 3.12.14, SQLite 3.53.1, ResourceWarning as an error
and an audit hook forbidding IPv4/IPv6 socket creation. It completed in
1.091616 seconds and pins 25 source files. The separate CLI rehearsal also
passed, producing a 21,328-byte synthetic package with four events and its
restart gap intact. This is local development validation, not Kali acceptance
or evidence of a storage-provider round trip.

This is a development-branch increment, not full R1 closure. No PR, CI release,
main merge, production restart, paid activation, signing or ML fit is authorized
by a successful handoff. The original five-working-day effort cap continues.

## Kali acceptance and independent restore — 2026-11-11

Implementation `be8fcfe09a0b865629591bebe95427ee219fc743`, tree
`9b5e4ec5fd762c5d7822d0cb42d1aa98b3faf63b`. All **198 tests** passed on Kali,
zero failures/errors/skips, Python 3.14.6 and SQLite 3.53.4, in 2.723781 seconds.
All 25 runner source hashes and both handoff source hashes match reviewed code.
Both uploaded reports identify the same 21,328-byte package and capture state.

The uploaded package was copied into a new private temporary location and
restored in the development environment with socket creation forbidden. Its
expected hash matched; its restored database bytes matched the ZIP member;
semantic replay matched both Kali reports. Four messages, four rows, one restart
and one explicit gap were preserved. The database SHA-256 is
`83a22052b74b3db7067de8efb951759139ea5d9cd6614babc994d998e3555e5e`.

| Uploaded artifact | SHA-256 |
| --- | --- |
| radar-r1-handoff-offline-20261111T132727Z-930958.json | 03d9c57b63760b840966d71fb85c047632bb5fd94c3baa687c645709e6db829c |
| report(3).json — rehearsal | 68d7ef0a660bfb3e0a38400c7dd44c83f6512e87fb9877c4675defe66ba0528e |
| report(4).json — export | 6646c6c37d68b9093e2436a4f4d1ba9cf7ba56c095875287e6b11abc6eb56117 |
| capture.zip | 461fb7ad53f77879bbc6cf5554002e5578b5a75fc40de418f7c8216b03ab0ff4 |

This establishes independent-environment portability of the synthetic package.
It does not establish a B2 upload/download, storage retention or backup coverage
of an actual R1 live capture. Original evidence flags remain unchanged; this
acceptance record adds the independently observed restore result. The next
increment is the scoped [synthetic B2 round trip](R1-BACKUP-ROUNDTRIP-20261111.md).
