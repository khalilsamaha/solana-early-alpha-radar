# Durable preparation integration

`preparation.prepare(manifest_directory, expected_sha256, paths)` connects the
frozen planning manifest and actual read-only storage observation. It consumes
the manifest's configured registry before observation. There is no arbitrary
output-directory argument, production mutation, credential read, provider/B2
connection, callback for service startup or activation API.

The registry must already exist privately. Preparation acquires a nonblocking
cooperating-process lock and records an exclusive, canonical, fsynced claim
binding the manifest, source hashes, exact proposed capture/staging paths and
registry filesystem identity. It then observes storage and validates the full
returned record before writing an exclusive terminal receipt. Lock/registry/claim
replacement prevents confirmation. The journal files remain inside the original
directory handle even if its path is replaced. Failed publication is not retried.

Possible outcomes are complete-live-blocked, insufficient-live-blocked,
failed-reconciliation-required or, on recovery without a terminal receipt,
unresolved. Complete means the bounded preparation finished, not that production
admission succeeded. All original manifest blockers and false activation flags
remain. Observation failures retain a fixed failure state without exception text;
interruption or publication failure leaves consumed evidence. Changing the
manifest or its location cannot reuse the configured registry. Deleting evidence,
selecting another registry, or replacing the implementation is outside this
cooperating-process protection and does not confer authority.

`preparation.inspect(registry, expected_manifest_sha256)` reads the retained
claim/result, validates source and exact manifest bindings, and independently
recomputes the observed capacity verdict. It checks directory identities, modes,
timestamps, all storage roles and retained authority flags. It never invokes the
storage observer, changes files, resumes a worker or repairs an interrupted
attempt. Registry copies and changed sources refuse inspection. Sequential reads
detect observed changes but are not an atomic system snapshot. Hashes supply
integrity relative to retained inputs, not independent host or owner attestation.

A complete valid terminal record can be recovered even when its caller lost the
return value or its final fsync raised after writing the bytes. Recovery reports
the retained observation, not proof that the original caller received an
acknowledgment or that those bytes survived a power loss. Missing/torn/invalid
terminal data is not promoted to success. No external mutation exists in this
preparation phase, and neither recovered nor acknowledged results authorize one.
This is different from a lost Docker/provider response, which remains uncertain
under the existing control contracts.

No claim of global connection exclusivity, reserved storage, live runtime adequacy,
remote retention or pilot approval follows. The production mutation executor and
actual owner/scanner/credential/supervision integration remain unimplemented.
This is the connected preparation boundary required before those operations.
Existing manifest, storage and native control sources remain unchanged.

Tests execute the complete chain using private temporary directories and actual
filesystem observations, then independently recover its receipts. Faults cover
durability, interrupted publication, path replacement, concurrency, source changes,
insufficient capacity and forged or inconsistent observations. There is no new
standalone Kali command; include preparation in the eventual combined admission
validation. Run `python3 -B -W error::ResourceWarning -m unittest discover -s r1-deployment -v`.
