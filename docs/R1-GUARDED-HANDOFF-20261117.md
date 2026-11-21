# R1 cooperating ownership, budgets and portable evidence — 17 November 2026

## Disposition

This is a new offline engineering increment under the continuing authorization.
The user requested a four-hour engineering window while unavailable for tests;
that request is not evidence of four hours elapsed, native acceptance or production
authority. One consolidated new Kali batch is prepared for the user's return.
No unchanged accepted batch is requested.

The previous application handoff remains accepted at its supplied **November 17,
06:48:00–06:48:20 CET** observation and source `56647b5`. Its review is recorded in
[the application handoff evidence](R1-APPLICATION-HANDOFF-20261117.md). This increment
adds stronger contracts; it does not retroactively assign them to that archive.
There was no fresh Kali, Docker, RPC, wallet or provider observation during this
engineering session. Local Docker is unavailable and Unix listener creation is
denied in the development environment.

## What changed

### One pinned service contract across different run directories

The guarded adapter accepts only an `IsolatedBoundDocker` fixture, not a production
target. A private service registry binds the exact original ID, image, name,
configuration, stop timeout, directory identity, lock identity and source. Its
digest is explicit in the manifest. A nonblocking kernel lock excludes another
cooperating coordinator even if it chooses a different run/output directory.

Before control opens, an exclusive durable claim consumes the service attempt.
Process death releases the kernel descriptor but does not erase that claim.
Re-entry, lock replacement, forked ownership, changed claims and a new output path
cannot rearm it. Completion is recorded only after explicit original restoration;
no context-manager exit or historical reader starts anything. There is no reset,
delete, adopt-old-receipt or production provisioning CLI.

This is cooperation under one externally pinned contract. A user selecting a new
contract, a privileged writer, an unrelated Docker controller or another host is
not fenced. Global owner exclusivity remains unproved.

### Separate original and shared-session budgets

Original disable-restart, stop, start-original and restore-restart have individual
budgets. The shared session has its own budget, and all phases share an aggregate
deadline that includes time between phases. Minimum allowances account for
bounded inspections, mutation clients, the worker wall limit and owned cleanup.
The fixture uses 30/30/60/30/30 seconds, an aggregate ceiling of 180 seconds; these
are ceilings, not waits. Deadline faults inject clock offsets and do not sleep
through repeated timing rehearsals.

The recorded production original's 35-second stop configuration is represented
separately from the manifest's shared shutdown ceiling. A unit test requires at
least 56 seconds for that original stop phase including call allowances; it does
not approve a production profile or measure the effective signal/shutdown time.
The manifest's 30-second ceiling and production settings are unchanged.

Checks immediately before dispatch and after calls prevent a late operation or
confirmation from progressing. An operation already performed can remain a
pending journal intent after expiry; timeout does not prove cancellation.
Application create/inspect/attach readiness uses the parent's remaining deadline.
Owned disposal remains available after expiry. Filesystem and kernel scheduling
stalls prevent any hard real-time guarantee.

### Full handoff preservation and independent replay

The portable archive includes manifest, preparation/admission gates, control
journal, bridge, supervision, synthetic credential receipt, fixed service
contract/claim/completion, phase receipt, nested capture and all bounded application
files. Each application file is hashed, including caches and sidecars. SQLite is
replayed read-only/immutable from a private disposable copy. Same counts, same
primary database or same aggregate byte count cannot hide an auxiliary-file change.

The reader verifies an external digest, canonical bounded ZIP, source map, member
hashes, exact bindings, admission order, timing, original restoration, application
closure and owned disposal. Recorded UID/GID is used explicitly; the reader's UID
does not become a purported observation of the original host. Original host paths
are identities, never restore destinations. Unknown, missing or inconsistent
evidence is quarantined, while valid component facts remain visible.

`closed-restored-offline-handoff-evidence` means this offline handoff reconciles.
It grants no automatic resume, production activation, global ownership, current
process status, provider truth, remote preservation, retention or E0 closure.
Hashes establish byte consistency, not independent attestation of a trustworthy
source host or protection against a writer able to replace all evidence.
A clean capture alone cannot promote a missing bridge/service confirmation.

Archive limits: 256 payload members, 2 MiB per member, 16 MiB total plus bounded
manifest/envelope overhead. Application storage is additionally limited to 32
files, 64 nodes, 256 KiB per file and 2 MiB total. The outer acceptance archive is
capped at 32 MiB of members. Failed export never repairs or retries a partial
handoff directory; retain originals if a bounded archive cannot be produced.

## One new Kali batch, after the user returns

Use a clean checkout of the published commit named `source`, beneath a fresh
private review directory. From that checkout run once:

```bash
bash scripts/r1-guarded-handoff-kali.sh
```

The runner has no production selector, credential input, provider endpoint, image
override or remote destination. It uses the same two accepted image IDs documented
in the application handoff record. **No build or pull is needed.** Every actual
container has network none and is newly owned; existing production containers,
volumes, credentials and services are not controlled.

| New case | Required outcome |
| --- | --- |
| Normal with service exclusion | Active second coordinator rejected; full shared closure and exact original restoration; later different-output attempt remains consumed; portable evidence complete |
| Deadline before shared entry | Original stopped, no shared actor starts, restoration withheld; portable evidence quarantined |
| Deadline after actual shared shutdown | Actors really close, injected expiry prevents bridge confirmation/restoration; quarantine |
| Service lock replaced | Refusal before first mutation; owned original later disposed; quarantine |
| Lost service completion | Actual original restoration remains visible, but missing service completion leaves attempt consumed and package quarantined |
| Nonprimary storage changed | Change one byte without changing file size or primary SQLite; original start refused with pending intent; quarantine |

The six cases create at most **ten containers**: six inert originals and four
application consumers, never more than two concurrently. Every owned original
and every started application must have disposal/client-reaping evidence. The
runner stops on unexpected failure and retains partial artifacts. Expected batch
status is `combined-control-offline-passed-live-blocked`, with one complete and
five quarantined handoff packages. Fault cases passing means their refusal worked;
it does not mean their handoff completed. Keep `results/acceptance.zip` and the
original directories on failure; do not rerun or change permissions.

Independent read-only review of a nested `handoff/evidence.zip`, using the same
source revision and its separately recorded SHA-256:

```bash
python3 -E -s -B r1-production-control/check_handoff_evidence.py \
  --archive /absolute/private/path/evidence.zip --sha256 RECORDED_SHA256
```

Exit 0 means verified complete offline evidence; exit 2 means verified quarantine;
exit 1 means invalid or unavailable input. The reader writes only disposable
scratch replay files and never contacts the source host or changes the input.

## Validation and remaining gates

The completed local suites passed: **169 control tests, 52 deployment tests,
73 supervision tests and 38 image/runtime tests**. These are executed suite
counts, including composed regression coverage, not unique native cases. Source
hygiene/package manifests, patch whitespace and shell syntax checks also passed.
The six Unix-listener tests were not invoked in this environment; the five
metadata/admission tests from that module are included in the supervision suite.

Local tests exercise actual Python/Node pipe workers, kernel flock and child
process death, with Docker modeled. They cover consumed-attempt exclusion,
last-gate expiry, expiry after an actual effect, lost durable completion, bounded
application startup/cleanup, auxiliary-file hashing, missing/reordered storage
gates, cross-UID metadata replay, malicious archive formats and independent
complete/quarantine replay. The new native application/Unix/Docker composition
remains untested here; local model results are not native acceptance.

Global ownership still needs evidence about competing controllers/processes,
socket authority and other hosts. Existing container names/images alone do not
settle it. Production resource adequacy, effective stop behavior, real credential
integration, remote preservation/retention and exact bounded pilot terms remain
open. No existing host observation needs repeating merely because time passed.

E0 stays **blocked with holds preserved**. Its last accepted operational/RPC
observation remains **November 9, 2026, 18:50:41 CET**. This work obtains no new
balances, finalized receipts, historical chain coverage or operational journal
evidence. The November 20 checkpoint is complete only if the required closure
evidence exists; otherwise retain the blocked disposition. Reopen for an exact
finalized receipt, credible complete historical coverage under reviewed policy,
or a concrete journal discrepancy enabling bounded reconciliation. Repeated RPC
absence, expired blockhashes and matching balances do not prove non-execution.
