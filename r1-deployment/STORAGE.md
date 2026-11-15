# Read-only storage preparation

`storage.observe(manifest_directory, expected_sha256, paths)` connects the frozen
deployment manifest to actual filesystem metadata. It never invokes Docker,
starts a worker, reads credentials, opens provider/B2 connections or creates files.
All six explicit directories must already exist: capture, export, upload staging,
download staging, isolated restore and quarantine. It does not create them or
change permissions to make a check pass. There is no operational CLI in this
increment and no additional standalone Kali batch.

The capture path must match the externally hash-bound manifest. All directories
must be private, owned by the current user, distinct, nonoverlapping with each
other or the configured control registry, and on the same writable filesystem.
Every path component is opened with no-follow semantics. File descriptors bind
the initial identities; a second namespace traversal detects replacement. Two
space samples use blocks available to the current user, taking their minimum.
Free space is compared to the manifest's full retained/quarantined and staging
budget. Insufficient space produces an explicit blocked result. Invalid identities,
links, cross-filesystem layouts, changed source/manifest or inaccessible paths
raise a fixed failure; nothing is automatically repaired or retried.

The returned report binds manifest digest, preparation sources, exact proposed
paths, device/inode/owner/mode, both samples and timestamps. It is historical
metadata, not an allocation or a reservation against concurrent writes. It does
not prove write access through ACLs, quotas, inode availability, filesystem
health, ongoing retention, remote policy or future free space. User namespace and
mount namespace are those of the executing process, not an attested host identity.
An adversary with control over paths/metadata is outside this cooperating-process
check; sequential reads are not an atomic system snapshot.

Do not clear the manifest's production blockers from this result. The eventual
admission executor must enforce write limits and disk-pressure stop behavior,
recheck identities/resources immediately before separately authorized mutation,
and retain a failed/uncertain attempt. This module supplies the missing specific
filesystem observation mechanism, not the production admission executor itself.

Local tests use private temporary directories, real read-only descriptor queries
and injected failures for full/read-only/multiple/replaced filesystem states.
They are not production capacity measurements. Run both suites with
`python3 -B -W error::ResourceWarning -m unittest discover -s r1-deployment -v`.
