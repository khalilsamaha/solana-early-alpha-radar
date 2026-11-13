# R1 production integration specification — draft, not executable

This follows the accepted November 13 identity/resource inventory. It defines
one combined implementation and acceptance boundary. No implementation or live
authority is claimed by this document. Existing accepted modules and historical
artifacts stay pinned to their source revisions.

## Source-grounded gaps

| Existing component | Verified limitation | Required change |
| --- | --- | --- |
| r1-session/session.py and README | A terminal capture closes the whole upstream/discovery session | Separate research retirement from discovery lifetime in a new production coordinator |
| r1-admission/worker.py and README | Synthetic credential only; networking denied; 10-second alarm and 12-second parent bound | Separate reviewed live supervisor profile and worker entry point; preserve offline profile unchanged |
| r1-service/lifecycle.py and README | Coordinator accepts explicit synthetic receipts | Distinct production receipt contract and adapters; never relabel fixture receipts |
| r1-session/archive.py | Completed candidate archives only; live authority deliberately false | Generation-bound production evidence format including interrupted attempts |
| r1-remote/README.md | Three fixed historical packages, 128 KiB ceiling | Separate bounded delivery profile for new production envelopes; keep historical verifier intact |
| scanner/compose.yaml | No broker IPC mount or explicit shared source | Reviewed deployment artifact with image digest, socket mount and shared startup configuration |

The current container image matching an earlier image is not proof it contains
the accepted shared adapter: the isolated rehearsal used a reviewed source
overlay. Production needs a verified image build and source mapping. Do not use
that testing overlay as a deployment mechanism.

## Combined implementation boundary

### 1. Immutable deployment and admission manifest

Bind source/tree and dependency hashes, new image digest, stable registry and
endpoint, service identity, registered limits, supervision profile, credential
provisioning method and evidence destinations. Keep secrets out of manifests,
argv, environment exports, logs and output archives. Bind approval to exact
manifest bytes; a draft or changed manifest cannot authorize launch.

The inventory is planning input only. Before any separately authorized mutation,
re-observe container/image/start identity and expected service configuration. A
mismatch stops before changing restart policy. Do not select by old PID or container
name alone. The registry must be a fixed configuration identity shared by the
production coordinator and admission process, not an operator-selected fresh output.
A local lock does not prove exclusivity across the whole host/IP.

### 2. Two lifetimes under one connection owner

The production coordinator owns the upstream for discovery. Research receives
one bounded, non-renewable lease with the original registered capture limits.
Normal research completion revokes new trade admission and retires all possibly
active watches, including uncertain sends. Successful local unsubscribe completion
may leave creation/migration discovery running; it does not prove billing cutoff.
Uncertain cleanup, overflow or owner failure closes upstream, records the gap,
and forbids automatic reconnect or direct fallback.

After research completes, its registry remains consumed. Discovery survival must
not recreate research authority. A production service restart cannot renew the
lease or silently resubscribe. Define discovery shutdown and explicit return to
direct mode separately; do not infer them from research archive completion.
The current short-session runner remains valid for its existing offline scope.

### 3. Production handoff and rollback receipts

| Order | Confirmation required before next step | Uncertain result |
| --- | --- | --- |
| Disable direct restart | Exact target and prior/new policy bound to durable intent | Stop; preserve intent; no shared startup |
| Stop direct owner | Exact process/container termination and supported local connection-closure evidence | Stop; no second owner |
| Bind shared endpoint | Registered endpoint and registry identity; no stale reuse | Stop; no provider attempt |
| Start shared scanner | Verified image/source mode and actual Unix peer; no direct fallback | Stop; no provider attempt |
| Start sole shared owner | Manifest/approval/credential admission validated; one attempt recorded first | Preserve consumed claim; no retry |
| Retire research | New subscription authority revoked; all possible watches handled or upstream aborted | Preserve failure and discovery gap |
| Stop shared deployment | Both actors terminated and supported local connection closure confirmed | Block direct restoration |
| Restore direct deployment | Explicit authority, prior reviewed config/image/policy restored and observed | Remain unresolved; no automatic loop |

Each production receipt binds generation, intent, exact actor identity, evidence
method, start/end timestamps and outcome. Process exit, TCP closure, provider
acknowledgement and billing cutoff are different claims. Never manufacture remote
claims from local ones. A return code alone is insufficient. Intent precedes
mutation; confirmation follows observation; lost responses remain uncertain.
Read-only recovery must explain the last confirmed step and possible effects
without invoking Docker, opening a provider, altering journals or resuming work.

### 4. Live supervision and evidence preservation

Design a separate finite live profile using the registered duration and bounded
shutdown, with resource/queue limits, parent-death handling, no core dumps,
credential redaction, STOP and no-rearm semantics. Do not simply raise the offline
alarm and call it live-ready. CPU/address-space/disk allowances require justified
worst-case budgets and validation; the current memory sample supplies none.

The portable envelope must bind admission/approval identity, exact producer
sources, handoff journal, worker and supervisor terminal evidence, capture,
measurement journal, manifest and original outcomes. Completed failed sessions
remain failed. Interrupted/active evidence is quarantined and cannot become a
complete archive by adding a receipt. Snapshot acquisition must establish a
stopped/quiescent boundary or preserve an explicit uncertain classification.

Validate size/format/source bindings before any remote operation. Persist a
transfer intent first; exact downloaded bytes plus independent restore and
receipt checks precede completion. Missing/ambiguous results consume the attempt
and preserve all local/remote evidence. No delete, automatic retry, mutable
retention claim or fallback to the historical fixed-package adapter.

Define capacity on the actual capture filesystem: maximum simultaneous source,
quarantine, envelope, transfer staging and restore bytes, plus minimum free-space
headroom. Enforce the accepted stop behavior under disk pressure without rotating
away evidence. The 512 MiB existing preflight is a sample, not an allocation.
Retention duration, number of retained runs, remote lifecycle/access policy,
interrupted evidence coverage and capacity approval remain required. One B2 round
trip establishes neither ongoing retention nor future recoverability.

## One consolidated validation round after implementation

Reuse accepted offline modules at their pinned versions; test the changed combined
boundary and its interactions. The test matrix must cover:

- Normal research retirement while discovery continues, then explicit shared stop
  and direct restoration in an isolated deployment.
- Lost/failed unsubscribe, send uncertainty, queue overflow, peer loss and owner
  death: no overlapping owner, no fallback, original failure outcome retained.
- Interruption before/after each production operation, lost confirmation and
  restart: registry remains consumed and recovery remains read-only.
- PID reuse, image/config change, foreign peer, replaced endpoint and different
  output path: reject stale binding before a dependent mutation.
- Credential load/redaction failure and parent death: no secret persisted, no
  success receipt from clean exit alone, owned processes bounded and reaped.
- Completed and interrupted envelopes, corrupt/mixed receipts, disk exhaustion,
  failed upload/download/restore/completion: no false success or evidence loss.

Local tests use injected transports and disposable state. The single later Kali
batch must exercise the actual new image, Unix/Node path, service-control adapters
on uniquely owned disposable targets and offline preservation/restore together.
The batch cannot access the production service or provider by default. Each
fault must prove it reached the intended stage. A skipped path is not acceptance.
Only after that gate, reviewed rollout and approved terms can a separate actual
production/provider validation be proposed. Do not hide a paid/live operation
inside the offline acceptance command.

## Outstanding decisions and stop rules

The existing proposal remains draft-unapproved: 20000 messages, 8 MiB raw payload,
172800 seconds maximum, sampling modulus 64, two simultaneous watches, 24 daily
watches and 600-second watch duration. These are draft ceilings, not guaranteed
24–48-hour coverage; any earlier limit ends collection. Do not increase them to
reach a sample target or call the draft profitability-study registration.
Funding ceiling, intended data-fee ceiling and approved exposed balance remain
null. Earlier 0.05/0.02 SOL suggestions are not approvals. No spending amount,
retention duration, live runtime profile or production activation is selected by
this specification.

The five-working-day engineering cap has not reset. Remaining allowance is unknown
without an effort ledger. This document scopes the combined remaining work; it
makes no claim that it fits the remaining allowance or warrants an extension.
November 19 remains at risk; no confirmation clock has started. E0's November 20
checkpoint and held-state restrictions are independent. December 31 remains a
scope/verdict decision deadline.
