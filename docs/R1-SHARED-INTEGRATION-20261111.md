# R1 shared connection integration — offline integration accepted on Kali

Date: November 11, 2026. This implements the selected single-connection design
as one combined offline increment. It continues the existing five-working-day
R1 build/validation cap; it does not close the full gate or authorize live use.

## Implemented behavior

`r1-data/shared_owner.py` owns one upstream factory attempt, one receive loop and
one serialized command path. Creation/migration subscriptions are sent once by
the owner. One non-renewable research lease can attach; stopping or expiring it
does not create a new upstream or a fresh research allowance.

Discovery and research use separate bounded channels, each limited to 64 frames
and 1 MiB. Incoming messages are capped at 65,536 bytes. Discovery projection
contains the allowlisted fields used by the existing candidate and launch
callbacks. Trades and provider acknowledgement text do not go to the scanner.
Sequence gaps, malformed input, stream termination and prolonged silence are
reported as unavailable discovery; none activates a direct-provider fallback.

Capture/journal work runs in a separate thread in the rehearsal. Its synchronous
SQLite and fsync calls do not run on the owner's dispatch loop. A two-second
worker heartbeat timeout independently revokes the research lease. Heartbeats
cannot extend the original lease deadline. A stalled thread is not forcibly
killed by this library; the offline command has an external whole-process bound.
The existing production supervisor still needs a separately validated live mode.

Research sends require active admission both before queueing and immediately
before upstream send. Attempted subscriptions are tracked before awaiting send
completion, so an uncertain send is not mistaken for an absent watch. Research
commands are limited to token-trade subscribe/unsubscribe; no account, trading,
signing or arbitrary methods are exposed.

Normal retirement immediately revokes new subscriptions, discards the research
queue and sends unsubscribe for remaining watches. This cleanup remains allowed
after the capture limit, has a one-second deadline and reserved command capacity.
The total owner ceiling is 1,024 commands, with at least 10 ms between completed
sends and the next attempt. Cleanup allows unsubscribe only. Successful local
transmission leaves discovery active. Failed/uncertain cleanup aborts the upstream
and exposes a discovery gap. Neither path proves a provider billing cutoff.

`shared_session.py` preserves the capture and measurement journal invariants.
Its journal records actual research send attempts/completions; owner-level free
subscriptions and cleanup are separately receipted, not misreported as research
or provider acknowledgements. The measurement receive clock starts at capture-
thread queue consumption. It excludes upstream-to-queue delay; the send-return
clock includes scheduling back to the capture thread. These local measurements
are not end-to-end provider latency or acknowledged subscription installation.

## Scanner and local transport

`shared_discovery.py` supplies a private, same-UID Unix-domain socket with one
accepted consumer, bounded writes and peer-credential checking. Existing or
symlink endpoints are refused. A private directory lock covers cooperating runs
using that directory; it is not a machine/IP-wide exclusivity guarantee. Client
death aborts the owner. No automatic local or upstream reconnection is added.

The scanner now selects its source once at startup. The default `direct` mode
retains the existing adapter. The explicit `shared` mode consumes only the private
local socket and never invokes the direct adapter or its reconnect loop. Callback
dispatch was extracted into a common helper so launch-registry and candidate
behavior stay aligned. No production environment variable, Compose mount or
container was changed. **Do not enable shared mode on the running scanner yet.**

The compact-statistics source manifest was updated for the changed scanner files
and three new adapter modules. Its store and statistics calculations are unchanged.
Prior provenance `b0058b0fb4eb5a3d13b6b3672aca4731ce2aefd981abc8a0a05b5a607a0dfc3f`
is retained as compatible; existing compatibility entries remain. This preserves
previously validated cache rows rather than bypassing source verification.

## Combined validation and limits

The new `check_shared.py` runs the R1 Python suite and the full scanner JavaScript
suite, then two integrated scenarios with the real capture/journal code and a
separate Node process using the actual scanner discovery adapter and an in-memory
launch registry:

1. Four synthetic research frames reach the capture limit; the paid watch is
   unsubscribed; a later creation still reaches scanner discovery. Exactly one
   upstream factory attempt and zero scanner upstream attempts are required.
2. A synthetic unsubscribe failure aborts upstream, the scanner reports a gap,
   and the capture/journal replay retains `transport-cleanup-failed`.

Both scenarios export and restore the complete session. Their owner command and
cleanup receipts remain separate evidence in the report. Each synthetic upstream
is injected; no provider socket, credential, paid feed or real trade is used.
The original accepted B2 archive and receipt are unchanged and are not rerun.

Development supports subprocess pipes but Python Unix-socket creation is denied
in this environment. Therefore development uses explicit `--pipe-only` and must
report `offline-shared-pipe-passed-host-ipc-pending`. This proves the combined
protocol/controller path, not Unix socket bind, permissions or peer identity.
The **default Kali run requires actual private Unix IPC**; it cannot silently
fall back to pipes or skip that check. Expected host status is
`offline-shared-integration-passed-live-blocked`, with
`real_local_socket_tested: true` referring to the shared IPC path.

Final development validation passed **314 Python tests and 226 scanner tests**,
with zero failures/errors/skips. The complete runner took 10.268734 seconds on
Python 3.12.14, SQLite 3.53.1, Node 24.22.1 and websockets 17.4. It pins 115 source
files. The exact synthetic development receipt is retained in
`evidence/r1-shared-development-20261111.json`, SHA-256
`0b2329e02c0d35ea21e7ed2d8780068df6a121aa3c8a7c6c4c00d5a6bab0103d`.
It explicitly reports Unix IPC as untested. Source hygiene and immutable package
manifest checks passed. One pre-existing supervisor-test environment sentinel
was shortened to an unambiguously synthetic value and its non-inheritance
assertion retained, resolving a credential-pattern false positive without
weakening the source checker or changing production credential handling.

The ordinary `check.py` status is now
`offline-shared-core-passed-host-ipc-pending`; its source list includes the shared
implementation and scanner dependencies exercised by its tests. Use the new
combined runner for this increment's Kali evidence.

Use the supplied isolated checkout command with its exact commit/tree and pinned
websockets wheel. It requires Node 24.10+ and Python 3.11+ on Linux. An external
180-second timeout bounds the whole command, with a five-second forced-kill
window. This avoids competing with the existing RPC tests' own SIGALRM guards.
The Node fixture also has a 12-second timeout and receives a minimal environment.

Upload the resulting directory's **report.json and session.zip**. Preserve the
directory on failure; do not reinterpret a failure or a pipe-only result as host
acceptance. A successful host report still needs independent source/hash and
archive review. No source directory under the production application is used
as a Git checkout, and no Docker restart is part of this command.

## Kali acceptance — November 11

Accepted implementation: `df6cbfa442943fd83f96ac9910103403cd8dbffc`.
The supplied report passes **314 Python tests and 226 scanner tests**, with no
failures, errors or skips. All 115 recorded source hashes match that implementation.
The default real Unix IPC run completed both normal and deliberately failed
cleanup scenarios on Python 3.14.6, SQLite 3.53.4, Node 24.19.0 and websockets 17.4.
The full runner took 22.221897 seconds; this is not a provider latency measurement.

The exact report is retained at `evidence/r1-shared-kali-20261111.json`, SHA-256
`bcc873501e48da9d17f7410de47353d0f36b410a5ccc1d530a9f1ec42be847e9`.
The uploaded normal session is 25,861 bytes, SHA-256
`739bd43b91dc2257b2c155a51fc7e8f6e64545fe10239a064c20ddbe9398bc70`.
It was independently restored in development; capture and measurement results
match the report exactly. Originals were preserved. Its four research rows and
five journal records retain one selected creation and one local research send.
Normal cleanup unsubscribed and discovery continued before explicit owner shutdown.

The deliberately failed cleanup correctly aborted upstream and preserved
`transport-cleanup-failed`. Kali reports complete-session replay for that scenario;
its separate ZIP was not supplied, so independent replay is claimed only for the
uploaded normal session. Both scenarios used one synthetic upstream attempt and
zero scanner upstream connections. No provider connection or paid activation occurred.

This accepts the combined **offline integration**, not production rollout or the
full R1 gate. The next dependency is the read-only
[`r1-host-review`](../r1-host-review/README.md) observation of Docker process UID,
namespace and container binding. Its 21 regression tests pass in development;
the development host observation correctly reports Docker unavailable. Kali host
observation remains pending. No accepted collector/scanner executable is changed
by that separate reviewer. The existing five-working-day effort cap is unchanged.

## Remaining live prerequisites

The owner and scanner path are library/configuration implementations, not a
live launcher. Kali's same-user fixture does not prove Docker's `node` UID,
mount permissions, startup ordering or rollback. A production handoff must stop
the existing direct socket before starting the shared owner, establish sole
ownership and make any discovery gap explicit. The current cooperating-directory
lock cannot prove that no unrelated process has opened a provider connection.

Private credential delivery, live process supervision, absolute exposure controls,
the fixed measurement registration, owner's numeric funding approval, actual
provider TLS/subscription behavior and real-session preservation/retention remain
open. The two-second heartbeat and one-second cleanup deadlines are operational
guards, not guarantees of a hard provider charge cap. No funding, live activation,
PR/CI consolidation, merge, production restart or ML fitting occurs in this step.
