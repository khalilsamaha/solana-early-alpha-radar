# Production deployment planning manifest

This library prepares immutable inputs for the next production integration. It
does not launch a service, query Docker, read credentials, observe storage or
open a provider. It does not relax the accepted offline coordinators.

`build(config, policy)` takes strictly named inputs. Unknown values are null and
remain named blockers. Configuration binds the image digest, scanner and rollback
configuration hashes, owner source hash, stable registry/socket, capture path,
remote-destination hash and sealed-descriptor credential method. Do not put raw
secrets, command lines or environment values into this record. Hash inputs are
references to separately reviewed artifacts, not proof those artifacts exist.

Policy binds finite research/service/setup/shutdown durations, CPU/memory/file
descriptor bounds, raw/database/journal/receipt byte limits, retained and
quarantined run counts, retention duration, free-space headroom, funding/data-fee/
exposed-balance ceilings and remaining engineering minutes. No defaults silently
fill missing decisions. Existing draft duration/raw ceilings cannot be raised.
Zero financial ceilings are explicit constraints, not missing values. At least
one retained and one quarantined run must be budgeted.

Capacity is a conservative planning calculation for one filesystem containing
capture, export, upload/download staging and isolated restore. It includes DB
rollback bytes, retained sources plus envelopes, failed/quarantined runs and
simultaneous new-source/export/staging/restore copies. The 64 KiB envelope overhead
is a proposed exporter bound, not measured filesystem consumption. Future writer
integration must enforce limits and check actual filesystem identity/free space;
this calculation neither reserves space nor verifies retention or cloud policy.
It is deliberately separate from the historical fixed 512 MiB preflight.

`freeze(new_directory, manifest)` writes a private, canonical, fsynced record and
returns its SHA-256. The parent must be private. A failed attempt retains its
directory and cannot be reused. `inspect(directory, expected_sha256)` requires an
external retained digest, validates source bindings and never changes evidence.
Hashing is integrity relative to the retained digest, not authenticated owner
approval. No method accepts an activation flag or turns complete inputs into live
authority. Production adapters, ownership, live profile, credentials, preservation,
delivery and exact pilot/rollout approval remain explicit blockers in every output.

This is an admission-input implementation, not a production admission executor.
The live worker, real scanner deployment, provisioning and variable-session remote
adapter still need integration. Do not deploy the inert native fixtures or call a
complete manifest a passed rollout gate. There is no new Kali command for this
pure offline component; include its eventual consumers in one integrated check.

Run `python3 -B -W error::ResourceWarning -m unittest discover -s r1-deployment -v`.
