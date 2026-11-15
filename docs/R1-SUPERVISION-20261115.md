# Manifest-bound supervision candidate — 15 November 2026

**Subsequent disposition:** the approved package is published at
`d7077b50f55ac657ba7e0b4271b5e3774e988e16`, with the exact tested tree.
[Capture/session integration](R1-CAPTURE-SUPERVISION-20261115.md) is the next
local candidate. The publication request below records the earlier stage.

## Change and validation

An additive `r1-supervision` package connects completed durable preparation and
an exact deployment manifest to a fixed synthetic Python worker. The accepted
manifest, preparation, native handoff and provider sources are unchanged.

The worker installs and verifies hard/soft limits for address space, CPU, open
files, per-file bytes and core dumps. A parent-death signal and child wall alarm
are configured. The parent independently enforces the aggregate configured wall
budget, bounds output to 32 KiB and terminates/reaps its owned child. No arbitrary
command, provider, credential or production target is accepted. Cooperating Python
guards reject DNS, Internet sockets and subprocess creation; this is not a native
code security sandbox or a production cgroup implementation.

The supervisor durably consumes a private registry claim before spawn. Exact
manifest/source/preparation/profile/terminal bindings are required for success;
zero exit alone is insufficient. Read-only recovery never launches, signals,
samples capacity or writes. Missing terminal evidence retains unknown worker
count/reaping and remains unresolved; it grants no retry or activation authority.

The retained [validation report](evidence/r1-supervision-development-20261115.json)
records 26 tests, zero failures/errors/skips and no captured diagnostics, with
21 source hashes. Local Linux run: 2026-11-15 15:07:08.484225–15:07:12.964748 UTC
(16:07:08–16:07:12 CET). Actual subprocess tests exercise completion, rejected
network/process operations, excess/malformed output, independent deadline and
SIGKILL after ignored TERM. Fault tests cover durability, interrupted/lost terminal
publication, changed/copied registries, source/claim/receipt changes and uncertain
reaping. No Docker, production host, provider or credentials are involved.

## Limits and next intervention

Status: `supervision-development-passed-live-blocked`. This is local development
validation, not Kali acceptance or proof of production resource sufficiency.
Parent-death behavior is configured but not independently fault-tested. The probe
uses one aggregate service/setup/shutdown deadline, with up to 0.25 seconds TERM
and two seconds KILL/reaping cleanup; it does not implement phase-specific owner
shutdown. Address-space and per-file limits are not whole-container RSS or total
storage limits. Receipt recovery is historical and cannot determine current
process life, caller acknowledgment or power-loss durability.

The reviewable publication package contains the five new supervision files, this
report, its validation JSON, the prepared-handoff acceptance and three status/
scope updates. Base: `85b07532d3917c435a9978d657a595f62da0890c` on
`research/r1-offline-capture-20261111`. Publication requires the next explicit
approval; no new GitHub publication is claimed. There is no standalone host test
request for this probe. Combine changed-boundary host validation when actual
owner/scanner integration is ready; do not repeat accepted unchanged rehearsals.

Remaining work includes actual production configuration/identity and executor,
owner/scanner runtime integration, phase shutdown and credentials, real evidence
delivery/retention, resource adequacy and exact pilot approval. The five-day cap
has not reset; remaining effort is still unknown. No production/main/E0 action or
measurement start is authorized by this candidate. E0 holds remain preserved.
