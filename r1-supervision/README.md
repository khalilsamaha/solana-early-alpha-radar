# Manifest-bound resource supervision candidate

This connects a completed durable preparation to a fixed synthetic worker with
resource limits derived from the exact deployment manifest. It is not a live
owner launcher. There is no credential argument, provider mode, arbitrary command
or production service action. Existing accepted runtime sources are unchanged.

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

`supervisor.inspect(registry, manifest_sha256)` replays retained evidence only,
without worker queries, signals, fresh capacity samples or writes. Missing terminal
evidence reports `supervision-unresolved`, with worker count/reaping unknown; it
cannot determine current process state. A valid result found after a lost return
is historical evidence, not proof the caller saw it or of power-loss durability.
Torn, copied, changed-source, inconsistent and authority-changing records refuse.

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

Run `python3 -B -W error::ResourceWarning -m unittest discover -s r1-supervision -v`.
No new standalone Kali command; combine the completed runtime integration later.
