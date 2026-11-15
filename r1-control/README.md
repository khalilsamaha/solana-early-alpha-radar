# Exact-target service control and retained recovery

This increment implements the first service-control operations required before
shared-owner handoff: disable restart, then stop the exact bound actor. It is an
additive contract; the accepted synthetic lifecycle is not relabelled production.
No production CLI, startup of a shared owner or rollback permission is introduced.

The target binds container ID, image, immutable actor command, configuration,
PID and engine start timestamp. Inspection immediately before durable intent and
again immediately before mutation must match exactly. Each intent is appended
and fsynced before the Docker command; the exact returned ID and subsequent
inspection must both pass before a confirmation is durable. Reused PID, new start,
changed image/configuration, wrong order, foreign label or replaced journal fails
closed. Failed operations poison the writer; the registry claim is never removed.

Recovery reads bounded private claim/log bytes, validates the hash chain, exact
before/after bindings, UTC chronology and local-only claim scope, then checks that
read bytes did not change. It never invokes Docker, writes, repairs or resumes.
A copied registry fails its original absolute-path binding. A consumed registry
cannot be rearmed. This is local generation protection, not proof of host/IP-wide
connection exclusivity or security against a privileged operator rewriting data.

`locally-stopped` means the Docker engine reported stopped, PID zero and clean
exit for the exact container after a confirmed stop command. It does not prove
provider TCP closure, provider acknowledgment, billing cutoff or authority to
start another owner. Those flags remain false even after a successful local stop.
A lost command response stays pending even if later fixture cleanup removes the
container. Cleanup is not retroactively written as successful control evidence.

## One isolated host batch

`scripts/r1-control-kali.sh` requires the already accepted local image
`sha256:8c6e3458333f587cb1a5110dbfdc2d6c98f2bdcc6892eb589ee08cf8b9b66140`.
There is no build, pull, pip, credential access, sudo, production selector or
provider operation. A missing image/access stops the batch without fallback.

Three owned disposable containers run a source-bound inert Node command in that
image, verify its manifest and emit a readiness marker. They do not start scanner
loops. No source mount is used. Network none, read-only root, no capabilities,
no new privileges, user 1000, init, no logging/healthcheck and fixed resources are
verified. Restart initially uses unless-stopped specifically to test disabling it.
The three cases are normal stop, deliberately lost update response and deliberately
lost stop response. Fault markers prove the real Docker operation returned before
the response was withheld from the control writer. Recovery must preserve pending
states, and cleanup removes only containers whose exact ID/image/label/isolation
remain verified. Any uncertain ownership/removal stops without retry or repair.

Return results/acceptance.zip, including on failure. Expected success is
`service-control-offline-passed-live-blocked`, with three removed test containers.
The ZIP includes each generation's claim and full journal for independent replay.
This tests service-control mechanics on inert actors, not provider-connection
closure, complete production handoff, restoration, or long-duration operation.

Remaining integration: deployment/admission approval and fixed production registry,
actual connection-closure evidence, shared owner/consumer transitions and rollback,
live supervision and credential provisioning, variable real evidence delivery,
capacity/retention, measurement/exposure terms and separately scoped activation.
