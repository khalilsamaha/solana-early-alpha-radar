# R1 read-only handoff inventory increment — 13 November 2026

Following independent acceptance of the uploaded admission batch, this round
implements the next missing evidence collection step. It adds a fixed-target,
read-only metadata collector and an explicit blocked prerequisite report. No
production adapter or launch authority is introduced.

## What changed

`r1-handoff-review/inventory.py` wraps the existing bounded production identity
observer with two allowlisted resource inspections, one before and one after.
At most four local Docker inspect commands occur, each limited to four seconds
and 16 KiB output. Target, executable, socket and fields are fixed. There is no
exec, stop/restart, policy update, credential/environment/mount/label dump, provider
connection, RPC, B2 action or permission change.

Identity checks bind container/image/PID/start-time/restart policy and the existing
UID/namespace/cgroup evidence across reads. Resource metadata is recorded without
turning unbounded Docker settings into approved limits. A bounded memory sample
and review-output filesystem sample are clearly marked as observations, not
allocated production capacity or retention assurance. State can still change
after observation; this is not an atomic host snapshot or exclusive-owner proof.

`prerequisites.json` retains the observed candidate identity, findings and all
remaining live handoff gates. It is always production-handoff-blocked. Missing
access or inconsistent identity yields an explicit unavailable report, null
binding and all gates still open. Untrusted error text is discarded.

`report.json` binds the prerequisite bytes by SHA-256, records source fingerprints,
host observation timestamps and false authority/action flags. The operator returns
that report, prerequisites.json and the offline validation.log. Existing output
is never replaced. Only isolated new evidence and temporary empty Docker config
are written; service state is read-only.

## Validation performed here

**15 offline tests passed**, zero failures/errors/skips. Coverage includes fixed
read-only commands and excluded sensitive fields, strict resource shapes, changing
container/resource identity, memory bounds, missing access and error redaction,
no production-capacity inference, blocked prerequisites, existing-output refusal,
source drift, and zero-failure tests containing an async diagnostic. End-to-end CLI
cases use mocked host observation; no live Docker/Kali access was performed here.

Seven inventory/host-observer source fingerprints are bound. The full accepted
163-file admission fingerprint set remains unchanged. Script syntax and source
hygiene checks pass; no unchanged integration or backup batch is requested.

Local validation status: `offline-inventory-tests-passed-host-observation-pending`.
Validation log SHA-256:
`02f5c10f8a4080330c66198a0e4be5e8786986135174d1a7560d000d9ead8c6c`.
Local validation receipt SHA-256:
`8771fa7ab76e3d432412e21863a52ac0ef6a86e1890b1ff409266e8532ea196a`.

## Required next observation

Run `scripts/r1-handoff-inventory-kali.sh` once from its new pinned isolated
checkout. It uses standard-library Python only and an enclosing 45-second budget
plus five seconds to terminate the observer. It does not install dependencies.
The existing scanner is never a signal or mutation target. Return report.json,
prerequisites.json and validation.log. If access is unavailable, preserve the
unavailable result; do not elevate permissions or automatically retry.

The observation is needed to bind the actual current production identity and
resource configuration before preparing concrete handoff/rollback work. It cannot
close global ownership, actual upstream closure, stable registry/endpoint choice,
live supervision/credential provisioning, retention/capacity allocation, measurement
terms or numeric exposure authority. Any real service transition remains separate.

R1 is still completing collector/preservation prerequisites. November 19 remains
at risk; no 21-day confirmation window has started. The five-working-day effort
cap is unchanged, with no new allowance inferred. December 31 stays the decision
checkpoint. E0 remains blocked with holds preserved; last accepted operational
observation is November 9, 18:50:41 CET. No E0 evidence is refreshed by this work.
