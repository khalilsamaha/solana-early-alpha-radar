# R1 isolated service integration

This is the next development increment after the Kali lifecycle acceptance at
`c0143106c1a3c3643bdc07907ba4659bcdfe8476`. It joins the durable eight-step
coordinator to the actual shared owner, wire validator, capture/journal thread,
sealed-descriptor delivery, Unix discovery server and Node scanner adapters.
The upstream WebSocket peer remains synthetic. There is no live mode, real-key
input, provider connection, funded subscription, signing or trading path.

## Acceptance and scope

The prior uploaded lifecycle report passes 314 core tests, 21 lifecycle tests,
127 matching source hashes and 18 scenarios. Every uploaded journal independently
replays exactly; every fixture process was reaped. Full runner: 22.48334 seconds.
Exact report and journal bytes are retained under `../docs/evidence/`:

- `r1-lifecycle-kali-20261112.json`, SHA-256
  `65027ccc0232dcdcb36fc122e7d8d0a955a193de852f3976f4d6ae1f5d0160fb`.
- `r1-lifecycle-kali-journals-20261112.json`, SHA-256
  `bb00c3ad04e988104ecbd402869448b250f20500b9952aef242a8a69a8f7ba59`.

Those results accepted the coordinator policy and native fixture lifetimes;
their endpoint and restart policies were simulated. This checker adds the
component integration. Its default mode **requires real Docker and Unix IPC**;
it never falls back. The explicit development flag `--host-pipe-only` instead
uses local Node and a pipe, reports simulated restart policies, and cannot pass
Docker/Unix acceptance. Development tests of daemon command guards use a stub,
not a real daemon. The unchanged 226 scanner checks and credential/Docker suites
retain their prior Kali evidence; they are not presented as newly rerun here.

## What runs on Kali

The runner performs read-only production identity observation against the prior
accepted image/UID/namespace baseline. It does not stop, exec into, alter policy
on, or restart the production scanner. All mutations use fresh generated names,
matching ownership labels, the fixed image digest and exact verified disposable
container IDs. No user-supplied target/image/command is accepted, and no image is
pulled. Containers have network `none`, read-only root/mounts, dropped capabilities,
no-new-privileges, UID/GID 1000, no logs, and CPU/memory/process limits.

Each of two scenarios (normal and failed unsubscribe) consumes a new durable
claim before creating the baseline direct fixture. The baseline runs the actual
direct scanner adapter with an in-memory WebSocket peer; its restart policy is
set to `unless-stopped`. The coordinator then:

1. Sets the disposable direct container's restart policy to `no`, verifying
   ownership, running state and the before/after policies.
2. Stops it, checks its adapter's connection-closed result, confirms container
   exit and reaps the attached CLI process.
3. Starts a separate Python broker and binds a private Unix socket, with zero
   upstream attempts. An anonymous sealed descriptor carries a generated
   synthetic credential; no key enters argv, environment or persisted evidence.
4. Starts the actual shared scanner adapter in a disposable container and waits
   for the broker's same-UID peer handshake before allowing upstream startup.
5. Opens one in-memory upstream peer and attaches the actual research capture.
6. Retires research. Normal unsubscribe keeps discovery running for a post-stop
   creation. Deliberate send failure aborts upstream. Neither outcome claims a
   provider acknowledgement or verified billing cutoff.
7. Closes/reaps the broker and scanner, verifies complete capture/journal export
   and restore, and requires successful termination before confirming shutdown.
8. Starts a new disposable direct fixture and restores `unless-stopped`.
   This is the explicit successful rehearsal rollback, never automatic recovery
   from a pending/failed operation.

Finally all owned fixtures are stopped/reaped and all six disposable containers
are removed. A failed/uncertain operation cannot retry or restore direct mode.
The report retains generated cleanup identities if cleanup cannot be confirmed.
Repeated TERM/INT signals are ignored only during the bounded cleanup unwind.
A hard kill, host crash or Docker outage can still leave disposable containers;
retain the failed output for identity-specific reconciliation. Never infer removal
from an unavailable daemon, and never rerun a consumed registry to resume it.

## Bounds and evidence

Each Docker command has the existing four-second/16 KiB bound. Broker control
replies are capped at 4 KiB, with four-second waits (nine for retirement), and
reaping is bounded. The separate offline broker profile allows 45 wall seconds,
10 CPU seconds, 256 MiB address space, 44 MiB/file, 32 descriptors and no core
dumps. It has parent-death SIGKILL, blocks Internet/DNS and child creation, and
accepts only `peer`, `start`, `retire`, `stop` in order. The earlier accepted
10-second runtime fixture and all existing research/cleanup deadlines are
unchanged. Local Node development fixtures have their existing finite timers;
Docker mode adds the enforced container resource/network boundary.

Run `check_integrated.py --output-directory NEW_PRIVATE_PATH` in the pinned
checkout with the hash-pinned wire dependency. Its report includes 314 core,
21 lifecycle and 16 integration tests, plus the two complete service scenarios.
Upload all four output files:

- `report.json`
- `journals.json`
- `normal-session.zip`
- `cleanup-failure-session.zip`

Both packages must independently replay against their report hashes. This closes
the previous limitation where only the normal package was uploaded. Expected
Kali status is `offline-service-integration-passed-live-blocked`; expected
explicit development status is
`offline-service-integration-development-passed-docker-unix-pending`.

This remains isolated synthetic integration, **not production handoff or provider
TLS/session acceptance**. Pending work: review the Kali integration evidence,
finish live measurement registration/exposure terms and real-session preservation
coverage, then obtain the specific production/live authorization needed for that
phase. No further synthetic backup round trip or ML fitting is requested. The
five-working-day total R1 engineering effort cap is unchanged. Full-gate Kali
validation precedes PR/CI consolidation; merge remains the owner's decision.
