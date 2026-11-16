# Retained-container control adapter — R1.B

This adds an actual Docker command adapter for disable-restart, stop,
start-the-original-container and restore-restart-policy. It retains the exact
container ID rather than reconstructing it from partial Compose metadata. No
production launcher is implemented. `admission.Prepared` is the direct-only
round trip; `shared_session.SharedPrepared` adds the existing offline worker/scanner
session and gates restoration on its confirmed shutdown.

## Current acceptance and admission integration

The supplied 11:50:08–11:50:18 CET run on `a858024b` passed the isolated boundary:
29 tests, 13 producer hashes, four matching journal replays and four cleanup
receipts. Do not repeat that unchanged native check.

`admission.py` connects the reviewed readiness target to a single exact-ID Docker
inspection and connects the retained controller to manifest/storage preparation.
The separate `check_binding.py` entry point is read-only: one production inspect,
no control construction/mutation, unit suite or disposable actors. It supplies the
full fingerprint needed for deployment-specific binding while retaining activation
and ownership blockers. Raw configuration stays in memory. See
[the accepted evidence and remaining scope](../docs/R1-TARGET-ADMISSION-20261116.md).
The supplied 12:01:22 CET binding report matches all 32 producer fingerprints;
no unchanged binding check is needed.

## Shared-session restoration gate

`SharedPrepared` returns the existing retained controller. The caller explicitly
performs disable-restart and stop, calls `run_shared()` within the open controller,
then requests start-original and restore-restart. The session method runs the
existing concrete finite supervisor with an owned scanner, never a caller-provided
shutdown boolean. Its mutex excludes controller operations during the session.
All bridge files are exclusive and durable; source, admission, manifest,
preparation, stopped target and supervision bytes are bound to that attempt.

Both restoration actions require the successful same-process completion witness,
unchanged shutdown evidence and existing storage/target gates. Failed or lost
results poison the controller, including after the children have actually exited.
Recovery reads do not restore, rerun, repair or reconstruct a completion witness.
No context-manager cleanup starts the original. Local abort is recorded as abort,
never promoted to a provider acknowledgment or clean unsubscribe.

The supported sessions are the existing offline pipe/native scanner fixtures.
Local integration tests execute the actual Python worker and Node pipe scanner,
with Docker modeled. Native mode retains its existing fixed image requirement;
production-image compatibility is not established. This library has no new host
entry point and confers no authority to stop or restore a production container.

## Evidence and persistence

The existing `r1-control.Control` journal writer now exposes contract hooks;
its default isolated target/receipt/replay contract remains unchanged. This
adapter subclasses it with a separate four-action claim scope and independent
replay validator. The isolated reader rejects this scope. Intent is durable before
any command; the target is checked before intent and again before dispatch.
Missing acknowledgments or failed postconditions leave the attempt pending and
poisoned, even if Docker performed the operation. Neither context-manager exit
nor recovery starts or restores anything. Consumed registries cannot be reused.

The private inspection projects complete Config, HostConfig and Mounts into a
hash, excluding only the explicitly controlled restart policy name. Retry count
must remain zero. Raw commands, environment values and mount paths are not written
into receipts. The projection also binds exact container/image/name, engine start
time, PID, configured stop timeout and state. Resource, environment, command,
volume or other configuration drift blocks continuation. It does not hash volume
contents, certify the Docker daemon, detect a privileged writer rewriting all
records, or prove that no other process uses the provider.

Only `unless-stopped` -> `no` -> `unless-stopped` is supported. The configured
stop timeout must be explicitly available (1–60 seconds); the command timeout
allows another five seconds. Unknown/non-TERM custom stop signals are rejected;
an omitted signal is accepted as configuration input without claiming that this
observes the effective production signal or shutdown behavior. The observed Kali
35-second setting is supported by the adapter and unit test. The synthetic native
fixture explicitly uses TERM and two seconds. Changing the manifest's separate
30-second shutdown ceiling or approving a production duration is **not** done here.

A clean local stop requires engine stopped/PID-zero/exit-zero state at the same
container and configuration. Restoration requires a later engine start generation
and the same ID/image/configuration. These are engine observations, not application
health, provider TCP/billing closure or globally exclusive ownership. Docker offers
no compare-and-swap transaction across inspect/update/start: an external controller
can race these checks. Production admission must exclude competing controllers;
this adapter alone does not establish that condition.

## CLI diagnostics repair after first native failure

The first supplied host run passed 21 unit tests but stopped with a pending stop
intent in its first case. It did not pass native acceptance. See the dated evidence
record for exact timestamps and limits. The adapter now uses `--timeout`; command
stdout/stderr are separately bounded and drained. Only stdout can acknowledge the
operation. Zero exit and exact ID plus independent postconditions remain required;
a warning never becomes part of the ID. Only stderr presence and constant failure
categories are reported, along with phase and last valid sanitized projection.
No raw diagnostic or environment value is retained. Client termination does not
prove that a Docker mutation was cancelled. Pending operations remain pending.

## Native changed-boundary check

Run `scripts/r1-retained-control-kali.sh` from a clean pinned checkout named
`source`. It accepts only an output location, never a production selector. It uses
the already accepted image and inert manifest-checking actor, with network none,
read-only root, dropped capabilities, no new privileges, no mounts, fixed resource
limits and a fresh random ownership label. It does not pull/build images, connect
to a provider, read production credentials or control any existing container.

Four cases each create and dispose of one owned container:

1. Stop and explicitly restart the same original ID; restore restart policy.
2. Perform stop but withhold its response; recovery stays pending, no restart.
3. Perform start but withhold its response; recovery stays pending, no policy restore.
4. Change the stopped fixture's memory limit; restoration refuses configuration drift.

The last case deliberately changes a disposable test container only. Cleanup
checks exact ID/image/label/isolation and the one expected memory change, and is
not treated as a control confirmation. All four journals and claims are retained
for independent replay. On failure keep the directory/archive; do not retry or
change permissions. Expected status: `retained-control-offline-passed-live-blocked`,
with four removal/client-reaping receipts. A passing isolated check does not
validate the running scanner's volume contents, real provider behavior, production
rollback or global ownership. No unchanged prior host suite is requested.

Primary command semantics consulted 16 November 2026:
- https://docs.docker.com/reference/cli/docker/container/create/
- https://docs.docker.com/reference/cli/docker/container/stop/
- https://docs.docker.com/reference/cli/docker/container/run/

## Remaining before production

The observed-target binding is accepted. Complete production ownership/admission
and apply the integrated shutdown gate to the actual shared scanner/worker/credentials,
preservation/remote retention and explicit pilot terms. Original-container
retention is the candidate restoration mechanism, not a claim those gates passed.
R1.A global ownership and R1.B as a whole remain open. E0 is unchanged.
