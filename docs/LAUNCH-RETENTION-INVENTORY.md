# Bounded receipt-index inventory

The launch feature audit decodes retained payloads to count field availability
and actor repetition. A full retention window can exceed its read deadline.
Such a failure remains incomplete evidence; do not extend the deadline or accept
partial field counts to clear the baseline gate.

`operations-tools/run-launch-audit.sh --hours 720 --retention-only` instead
reports receipt-index counts, the oldest and newest retained receipt timestamps,
and counts and endpoints inside the requested window. It requires the existing
`launch_registry_received` index and does not fall back to reading payload rows.

The output format is `launch-retention-audit-1`, distinct from the full feature
audit. Payload validation and feature availability are explicitly false. A
successful inventory does not complete the full audit, establish uninterrupted
capture, verify a preservation copy, or authorize deletion.

The connection remains read-only, within one transaction, with a ten-second
deadline, a 100,000-row cap, and a 64 MiB WAL-growth limit. The query examines at
most 100,001 index entries and refuses an over-cap result. Invalid or future
receipt timestamps also fail the entire report. Connections close explicitly
on success and failure, including the original feature audit path.

Regression coverage includes a full-capacity synthetic registry, over-cap refusal,
window boundaries, empty state, invalid clocks, missing index, deadline and WAL
failures, source preservation, and an SQLite authorizer that denies payload reads.
Existing launch-feature audit behavior is checked separately. The operations
package manifest is updated to `radar-operations-1.0.2`; this development increment
requires no installation, backup job, service change, restart, or transaction.

Run the new tests and both existing launch-audit tests on Kali before acceptance.
Preserve failed full-audit logs alongside the separate retention inventory.
Raw host evidence remains outside the repository. The baseline phase stays open
until its remaining evidence and retention decisions are resolved.
