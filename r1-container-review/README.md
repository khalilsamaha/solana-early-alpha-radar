# R1 isolated Docker boundary rehearsal

The November 11 host report at `35b89c5e` passes 21 checks and all three source
hashes. Scanner and review user are UID/GID 1000 in the same user namespace;
container health and hardening have no findings. Report SHA-256:
`b7244838004a7305a0466099f5a4060f9eb945ca641f32a683ac60a61e83189d`.
This is accepted identity evidence, not a production socket handshake.

This next combined rehearsal tests the actual shared adapter inside the exact
already-present image observed on Kali. No image is built or pulled. The current
production identity/image is checked again before creating disposable containers.
The production container is never stopped, restarted, executed into or modified.

Each disposable consumer is UID/GID 1000, network `none`, read-only root, no added
capabilities, no-new-privileges, no healthcheck, no restart or Docker log retention,
128 MiB memory, one CPU and at most 32 processes. Its two read-only bind mounts
contain only seven staged reviewed source files and a private synthetic IPC
endpoint. No production environment file, data volume, Docker socket, credential
or wallet is mounted. `/usr/bin/env -i` clears inherited image environment before
Node runs. There is no full scanner service or external RPC; the fixture uses an
in-memory launch registry. Creation options and mounts are inspected before start.

The host broker is the real shared owner with a synthetic injected wire. Python
Internet/DNS access is blocked by the acceptance runner. The container has no
external network interface; its WebSocket/fetch functions also refuse use.

Three cases run sequentially:

1. Bind the private endpoint; connect the container consumer and verify the
   server's same-UID peer check; only then start the synthetic upstream. Normal
   research retirement unsubscribes, discovery continues, and the session exports
   and restores exactly.
2. Deliberately fail cleanup; upstream aborts, discovery reports a gap, and the
   capture/journal replay preserves the failure outcome.
3. Start a disposable consumer without an endpoint: startup must fail locally
   with no upstream attempt or direct fallback.

Every disposable container has a fresh random name and ownership label. Cleanup
checks its exact ID, label and image before removing it (including any anonymous volumes created for that disposable
container); it never selects by the
production name or removes all containers. A successful matching Docker removal
response is required. A daemon timeout/failure is not interpreted as absence.
A dispatched create is awaited before cancellation reconciliation. TERM/INT during
Docker scenarios unwind cleanup. SIGKILL, host failure or daemon unavailability
can still leave a stopped/running disposable container; the fixture self-exits
within 12 seconds, and a failed report records only its generated cleanup identity.
Preserve the report for review; do not run broad Docker cleanup commands.

Run the supplied pinned command. Upload `report.json` and `session.zip`. Expected:
`offline-container-boundary-passed-live-blocked`, all tests, three removed disposable
containers, and replayed sessions. A failure report does not grant acceptance.
`--offline-only` is a development fallback that runs subprocess-pipe integration
and mocked Docker controls; it produces `offline-container-controls-passed-docker-pending`
and cannot establish a real Docker or Unix-socket boundary.

## Production handoff plan — not executed

The observed UID match permits the proposed broker to run as the normal host user
with a mode-0700 IPC directory and mode-0600 socket. Mount that directory read-only
at `/r1-ipc` in the future scanner configuration, with explicit shared source and
`/r1-ipc/discovery.sock`. This rehearsal tests that boundary only; it does not
activate those settings on production. Use a separately reviewed production image
containing the accepted adapter; the disposable test's source overlay is not a
production deployment mechanism.

Before activation, finish private credential delivery, live process supervision,
measurement registration, numeric exposure approval and preservation/retention
controls. At handoff, prevent the old scanner from automatically restarting,
stop it and verify its direct owner has ended. Bind the broker endpoint, start the
shared scanner, verify its actual peer, then attempt the sole authenticated
upstream. The directory lock alone cannot prove host/IP-wide ownership. No paid
research subscription begins before the registered bounded admission permits it.

Rollback must first revoke research, terminate the shared owner and confirm its
process/connection closure before restoring the previous direct scanner and its
restart policy. Record the discovery gap. Do not automatically fall back to direct
mode or reconnect after uncertain cleanup. If closure cannot be confirmed, stop
and reconcile; do not create a second upstream. Actual production startup,
restart/recovery and rollback remain untested by this disposable rehearsal.

Full-gate Kali acceptance still precedes PR/CI consolidation and a merge decision.
The existing five-working-day R1 effort cap is unchanged; this does not restart it.
No funding, live activation, trading or ML fitting is enabled.

References: [Docker create](https://docs.docker.com/reference/cli/docker/container/create/),
[network none](https://docs.docker.com/engine/network/drivers/none/),
[read-only bind mounts](https://docs.docker.com/engine/storage/bind-mounts/).
