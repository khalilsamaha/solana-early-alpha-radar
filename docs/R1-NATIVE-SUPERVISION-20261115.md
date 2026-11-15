# Native supervised scanner acceptance package — 15 November 2026

**Subsequent disposition:** [the supplied Kali batch is accepted](R1-NATIVE-SUPERVISION-KALI-ACCEPTANCE-20261115.md)
at source `cd28cb085948caea0cd785f2c20bd5cd6b49534b`. The instructions below record
the completed native test and do not request another run.

## Publication and authority

The previously approved separate-scanner package is published at
`a175782c94f6b4ae4699c6817ac837ee88534269`, tree
`207267be040b962ff96e60a775402d457bd630ed`, exactly matching local `5f4cbe5`.
The owner has now authorized continued publication to the existing R1 research
branch without another approval checkpoint. This does not authorize main merges,
production rollout, providers, trades, funding or changes to E0 holds.

This next package implements the native test boundary and is published under that
standing authorization after local checks. Native acceptance itself remains
pending the single pinned Kali batch below. No native host check is claimed here.

## New integration

The supervised capture child binds a private Unix socket before a consumer starts.
The parent rechecks the attempt, manifest, preparation and socket identity, then
records an exact name/token intent before creating a disposable consumer of the
already accepted image:
`sha256:8c6e3458333f587cb1a5110dbfdc2d6c98f2bdcc6892eb589ee08cf8b9b66140`.
Only the consumer role is used. There is no production target or direct-service
mutation, no image pull/build, credential load or provider operation.

The existing native adapter verifies image, command, UID/GID 1000, network none,
read-only root/mount, dropped capabilities, no-new-privileges, restart=no, fixed
128 MiB memory/swap, one CPU and 32 PIDs. The image verifies its scanner-source
manifest. The Unix server checks SO_PEERCRED plus process start identity against
the retained consumer identity; the image path also requires the peer's parent to
be the inspected container init PID. These hashes and observations are retained.

Historical recovery reads that evidence without fresh process/Docker queries.
The older stopped receipt's exact-base-class peer flag remains false for the new
subclass; the separate native-peer proof records the additional kernel checks.
Scanner terminal output, capture/journal replay, exact container cleanup and client
reaping must agree. A durable disposal snapshot is retained even on cleanup error;
uncertainty cannot become a supervisor success or authorize automatic reuse.

## Available validation and explicit gap

The workspace denies AF_UNIX socket creation with `PermissionError`, errno 1,
and Docker is unavailable. Initial Unix tests therefore failed at endpoint setup;
no scanner was started in those failed cases. No permission changes, alternate host
or fallback native acceptance was attempted. Six Unix integration tests remain
unrun on a capable host. Their absence is explicit, not hidden as passing coverage.

The final [development report](evidence/r1-native-supervision-development-20261115.json)
records 55 selected pipe/core/metadata tests, zero failures/errors/skips and four
retained pipe cases. Run: 2026-11-15 18:21:46.956994–18:22:15.022966 UTC
(19:21:46–19:22:15 CET). All 209 source hashes match. The 48-member bundle has
unique entries; separate case results equal aggregate entries, and all four
supervisor recovery states independently match retained evidence.

| Development case | Retained supervisor outcome |
| --- | --- |
| Normal | synthetic-worker-complete-live-blocked |
| Cleanup failure | synthetic-worker-complete-live-blocked; upstream-aborted |
| Lost scanner confirmation | worker-failed, despite cleanup |
| Space loss before scanner | supervision-unresolved; no actor started |

Development bundle SHA-256:
`6f393d500d944688899097c1ea2384d7830b2c6f4b8eda92f817ce5f73999147`.
Original aggregate report SHA-256:
`2fc40c38a27042c00cd26b5edf94983a1e6f302a184867a1e65a05abd2c8b038`.
These are local development artifacts, not Kali/native observations. No full child
stderr scan or production resource adequacy claim is made.

## Required Kali batch

Use a fresh review directory with a clean checkout named `source`, pinned to the
published revision supplied in the task reply. Run:

```bash
bash scripts/r1-native-supervision-kali.sh
```

The script runs four admission/metadata tests plus six real-Unix tests with owned
local Node fixtures. It then runs normal, cleanup-failure, lost scanner-confirmation
and pre-start space-rejection cases through the native image path. A complete
batch creates/removes three disposable network-disabled consumer containers; the
space-rejection case creates none. No unchanged image/control/handoff standalone
batch is repeated. The accepted image must already exist, and the existing UID/
Docker prerequisites must pass without installation or permission changes.

Return `results/acceptance.zip` whether the batch passes or fails. Keep every
review/registry directory. Never rerun or rearm an attempt; a failed/uncertain
result requires review of retained evidence. The script retains the bundle on
failure after its fresh output directory has been created.

## Remaining boundary

The native container profile is a fixed accepted fixture profile, separate from
manifest limits on the Python child. Docker operations retain their existing
individual command/read bounds; the aggregate worker deadline is checked between
operations, not imposed as a transactional cancellation deadline on the daemon.
Parent loss does not prove container removal. Production target/sole-owner
configuration, live credentials, full phase shutdown/containment, variable-session
delivery and retention, production adequacy and exact pilot terms remain open.

The unchanged five-focused-working-day cap still has unquantified consumed/
remaining effort; no allowance extension, source pilot or confirmation clock is
asserted. E0 remains blocked with holds preserved. This package adds no closure
receipt, journal reconciliation, fresh E0 host/RPC observation or current balance.
Its November 20 evidence-based checkpoint remains unchanged.
