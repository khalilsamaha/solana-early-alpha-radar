# Manifest-bound resource supervision candidate

## Current full application integration

The separate `session-application-normal` mode binds the accepted full application
image to this supervisor and the existing retained-original restoration gate.
[The combined handoff record](../docs/R1-APPLICATION-HANDOFF-20261117.md) describes
the fixed image, fixture storage, read-only SQLite validation and accepted native
evidence from November 17, 06:48:00–06:48:20 CET. No unchanged rerun is needed.
The new [guarded handoff](../docs/R1-GUARDED-HANDOFF-20261117.md) adds separate
control/session budgets and hashes of every bounded application file, including
nonprimary caches. Application creation and inspection calls use the parent's
remaining deadline; owned disposal remains available after expiry. Portable replay
uses recorded UID/GID bindings without querying the original host. These additions
await their own consolidated native batch; they do not reinterpret the earlier
archive as evidence for the stronger contract. Neither mode is a production
launcher or live-provider mode.

## Current credential integration

Session modes now receive a generated synthetic credential through the existing
sealed anonymous descriptor implementation. Only the worker inherits it, consumes
and closes it before capture, and records a claim-bound consumption/refusal receipt.
The parent closes its descriptor after spawn, including spawn failure. Success and
historical verification require the consumption receipt. No real credential file,
provider/network mode or production permission is added. Inspect older evidence
with its original source revision; the receipt schema/source map has changed.

The [combined native acceptance](../docs/R1-COMBINED-ACCEPTANCE-20261116.md) now
connects this mechanism to retained-original shutdown/restoration and local evidence
export/restore. Earlier references below to no credential handoff describe the
previous fixture version; there is still no user-supplied credential input.

This connects a completed durable preparation to a fixed synthetic worker with
resource limits derived from the exact deployment manifest. It is not a live
owner launcher. There is no credential argument, provider mode, arbitrary command
or production service action. Existing capture/session, deployment and native
handoff runtime sources are unchanged.

The profile requires explicit service/setup/shutdown, address-space, CPU and
descriptor limits, plus complete capacity inputs. Core files are disabled. The
per-file maximum is the manifest's envelope bound. Linux prctl installs parent-
death SIGKILL and rechecks the parent; setrlimit applies and verifies hard/soft
limits. The child enforces its own wall alarm and denies DNS, Internet sockets
and child-process creation. These are cooperating Python-worker guards, not a
security sandbox for arbitrary/native code. Address-space limit is not an RSS or
whole-container limit; file-size limit is per file, not total disk usage.

The parent consumes an exclusive registry claim before spawning and imposes an
independent wall deadline. Service/setup/shutdown seconds form one aggregate wall
budget; this probe does not enforce separate phase deadlines. Cleanup allows up to
0.25 seconds for TERM and two seconds for KILL/reaping after that deadline. A child
disabling its alarm and ignoring TERM still times out and is killed/reaped.
A zero exit code alone is insufficient: exact manifest, profile,
source, mode and terminal fields must match. Raw child diagnostic/output bytes are
not retained on failure. All results keep activation and restart authority false.
Failure or interrupted publication consumes the attempt; no automatic retry.
Retained timestamps identify the attempted run and terminal receipt. Claim and
result bind the same private registry inode, source map and preparation receipt.

`manifest_supervisor.inspect(registry, manifest_sha256)` replays retained evidence only,
without worker queries, signals, fresh capacity samples or writes. Missing terminal
evidence reports `supervision-unresolved`, with worker count/reaping unknown; it
cannot determine current process state. A valid result found after a lost return
is historical evidence, not proof the caller saw it or of power-loss durability.
Torn, copied, changed-source, inconsistent and authority-changing records refuse.

## Capture/session integration

The parent module is now `manifest_supervisor.py`. Its old name, `supervisor.py`,
collided with the existing capture library's supervisor import. No compatibility
shim is provided: it would reintroduce that ambiguity. The expanded source map
binds all capture/session dependencies and refuses earlier source-map receipts.
Inspect older receipts with their exact recorded source revision.

`session-normal`, `session-cleanup-failure` and `session-operator-stop` execute the
existing separated-session library in the bounded child. They use an in-memory
upstream and an in-process discovery peer, never the production Node scanner or
Unix endpoint. Real artifacts are written beneath the manifest capture directory:
`supervised-session` contains a closed SQLite capture, measurement journal and
admission/retirement/shutdown receipts. Research duration, service duration and raw
byte limit come from the manifest. The synthetic fixture has a four-message cap
and modulus one; it is not a pilot configuration. Memory must be at least 256 MiB
and the descriptor limit at least 32. These are fixture admission minima, not
evidence of adequate production resources.

Before spawn the parent retains one new storage observation, bound to preparation
paths, filesystem identities and attempt time. Insufficient space or failed gate
publication consumes the claim without starting capture. The child never resumes
an existing capture directory. The per-file kernel bound still applies; terminal
validation additionally checks database, journal and receipt byte budgets. Each
artifact read is capped at 256 KiB for this fixture.

Child and parent independently verify the closed capture and replay the journal
before success. Historical inspection checks the same bound artifact bytes and
receipts without invoking replay helpers that could recreate a missing lock.
It therefore makes no new current-process, filesystem-lock or semantic-replay
observation. Normal retirement records unsubscribe and discovery continuation;
cleanup failure and operator STOP record upstream abort and no continuation.
Successful validation of an adverse case is not a claim of clean unsubscribe.
All retain one synthetic upstream attempt and one research attachment.

The capture harness bounds its event waits using manifest timings, while the
parent enforces one aggregate wall budget. Existing internal library timeouts are
unchanged; this is not a complete production phase-deadline implementation. No
live credential, remote delivery, retention enforcement or production admission
is added. Child stderr is discarded rather than retained; a clean parent test
log does not establish a comprehensive child-diagnostics scan.

## Separate scanner consumer

`session-scanner-normal` and `session-scanner-cleanup-failure` replace the
in-process discovery peer with the existing fixed Node scanner-adapter fixture
(`r1-data/shared_scanner_fixture.mjs`) over an inherited pipe. They still use an
in-memory upstream. No production scanner loops, Docker commands, Unix socket,
credential or provider are involved. The exact adapter sources are pinned.

The parent consumes the claim and storage gate before starting Node. It verifies
readiness, rechecks inputs, then starts the capture worker with only the pipe's
write descriptor. It closes its own descriptor copies. Both subprocesses share
one parent wall deadline; startup uses the setup bound, and cleanup retains the
existing bounded TERM/KILL/reaping rules. Node also has its existing fixed
12-second fixture timer. This mode requires research at most three seconds,
service at most five seconds and an aggregate wall budget at most twelve seconds.
These are fixture limits, not proposed production/pilot limits.

The manifest kernel limits apply to the Python capture child only. The Node
fixture has no verified image, kernel-resource profile or independently tested
parent-death containment. Its receipt explicitly records `image_verified=false`
and `manifest_kernel_limits_applied=false`. Do not promote development pipe tests
to container, host-wide ownership, memory adequacy or live-provider evidence.

After normal research retirement, a synthetic creation is sent and the worker
waits for the delivery counter. The actual Node adapter must report creation,
migration and the later creation, with one terminal discovery gap. Cleanup failure
must report only creation and migration. Both exact scanner output and capture/
journal replay must pass before the parent records success. An absent or malformed
scanner result cannot be replaced by exit code zero or a cleanup receipt.

The retained supervisor result now includes a scanner receipt, or null when no
scanner mode was selected. It records start/reaping/exit and the validated result.
Lost readiness, failed capture spawn, lost scanner confirmation and uncertain
reaping remain failed or unresolved. Read-only recovery never starts a scanner;
an absent supervisor terminal leaves both process histories unconfirmed. Existing
published source receipts must still be inspected with their exact source revision.

The probe supports completion, attempted DNS/socket/process operations, suppressed
child alarm, ignored TERM, invalid terminal output and excess output. It uses no
real credential or provider. Output collection is capped at 32 KiB.
Local tests use temporary manifests, completed storage preparation and actual
subprocesses; their deliberately short profile is not a recommended production
profile. Duration support does not establish 24–48-hour adequacy or CPU/memory
sufficiency. Parent-death signaling is configured, not claimed independently
fault-tested by this increment. Docker/production cgroup enforcement, actual
owner/scanner integration, secret provisioning and phase-specific shutdown still
require work. Do not treat the probe as the production executor. The receipts are
locally bound evidence, not signed attestations against a hostile file owner.

## Native Unix and accepted image integration

`session-native-normal` and `session-native-cleanup-failure` start the owned
capture child first. It binds a private Unix socket and retains inode/device/owner
metadata. The parent then rechecks the attempt, manifest and preparation, records
a durable exact name/token intent, and creates only a new disposable consumer of
the accepted image `sha256:8c6e3458333f587cb1a5110dbfdc2d6c98f2bdcc6892eb589ee08cf8b9b66140`.
There is no production target, direct scanner stop/start, provider, pull or build.

The accepted native adapter verifies network none, read-only root and mount,
UID/GID 1000, no capabilities, no-new-privileges, no restart, memory/swap 128 MiB,
one CPU and 32 PIDs. This is the fixed accepted fixture profile, not a profile
derived from the Python memory limit or evidence of production adequacy. The
image verifies its own recorded scanner source manifest before readiness.

Before admitting the upstream fixture, a verified Unix-server subclass checks
SO_PEERCRED and `/proc` process identity against the parent's retained consumer
identity. For the image path, the peer's parent must be the inspected container
init PID. It retains the identity/endpoint hashes, peer PID, UID/GID and start ticks.
The older stopped receipt's exact-base-class flag remains false for this subclass;
the additional `native_peer` proof records the independently checked kernel peer.
Historical recovery validates retained evidence without fresh `/proc` or Docker
queries. Native container identity, result, disposal and client reaping must agree.

Every attempted consumer is disposed through its exact scoped adapter; the
disposal snapshot is retained even if cleanup raises. Uncertain cleanup cannot
publish a supervisor success. The native mode has research at most three seconds,
service at most five and an aggregate Python worker budget at most thirty seconds.
Docker transitions retain their own existing bounded commands and read deadlines;
the aggregate deadline is checked between them, not an interruptible transaction
deadline for the Docker daemon. Parent loss leaves a retained exact intent and
the fixed consumer timer, not proof of container removal or production containment.

`native_development=True` is an explicit local Node/real-Unix test path. It verifies
the peer's exact local process generation and reports no container or image
verification. The default native path never falls back to it. This workspace
rejects AF_UNIX socket creation and has no Docker; native Unix tests must run on
Kali. Pipe tests and metadata tests are not relabelled as native acceptance.

Run `bash scripts/r1-native-supervision-kali.sh` from a clean pinned checkout named
`source` in a fresh review directory. It runs ten native/admission tests plus four
retained cases: normal, cleanup failure, lost scanner confirmation and space
rejection before start. A complete batch creates/removes three disposable scanner
containers; the last case starts no actor. `results/acceptance.zip` is retained on
pass or failure. Keep all directories and do not retry an attempt. No unchanged
image/control/handoff standalone batch is requested.

For development without Unix access, run `check_native_supervision.py --development`
with a fresh `--output-directory`. That explicitly selects 55 pipe/core/metadata
tests and four pipe cases, marks the six Unix tests unrun and leaves native
acceptance pending. On a Linux host permitting Unix sockets, the complete unit
suite remains `python3 -B -W error::ResourceWarning -m unittest discover -s r1-supervision -v`.
