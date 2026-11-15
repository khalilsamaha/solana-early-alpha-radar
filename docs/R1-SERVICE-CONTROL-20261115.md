# R1 service-control increment — 15 November 2026

Following accepted scanner image evidence, implement the first exact-target
service-control operations and their retained recovery together. Source is
additive under r1-control; accepted image and runtime sources are unchanged.

The writer binds container/image/configuration/PID/start identity, durably records
intent, rechecks before mutation, and requires both exact command acknowledgment
and after-state inspection. Disable-restart precedes stop. Uncertain or failed
operations consume their attempt, and read-only recovery preserves pending state.
Confirmed local stop does not assert provider closure or authorize another owner.

Development: 17 tests passed without detected diagnostics. Coverage includes
identity change before and after intent, changed image/config/PID/start, lost
responses, refusal of retries, registry and journal substitution, torn log,
hardlinks/symlinks, fsync failure, clock regression, concurrent writers, nonzero
stop exit, read-only recovery and forbidden remote claims. Docker is unavailable
here; the three-case native host check remains pending.

The one consolidated host command reuses the accepted local image (no rebuild),
creates three isolated inert actors and verifies normal, lost-update and lost-stop
outcomes with complete journals and owned cleanup. It neither stops production
nor activates scanner/provider loops. The inert command verifies the accepted
image manifest and emits readiness before testing control. See
[r1-control scope and limitations](../r1-control/README.md).

This increment closes neither complete handoff nor rollback. Missing production
registry/approval, actual connection-owner proof, shared-owner/consumer transitions,
restoration, live supervision/provisioning and preservation remain required.
The next integration must use these exact-target receipts without relabelling
local engine evidence as remote connection or billing evidence.

Agenda: collector/preservation prerequisites remain in progress. November 19 is
unconfirmed; no source pilot or 21-day confirmation clock has started. The total
five-working-day cap has not reset and its remaining allowance remains unknown.
November 20 E0 disposition and December 31 scope/verdict checkpoint are unchanged.
