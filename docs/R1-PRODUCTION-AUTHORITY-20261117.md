# R1 Docker access-path evidence — 17 November 2026

## Purpose and current disposition

The six guarded offline handoff cases are accepted. They establish cooperating
coordinator exclusion under one pinned service contract, not global production
ownership. The accepted November 16, 11:23:54 CET workload inventory identifies
nineteen running containers by name/image/Compose metadata. It did not inspect
their mount access, added capabilities or host namespace declarations. Names and
images cannot settle whether another workload can control Docker or write the
scanner's data.

`r1-production-review/authority.py` extends the existing read-only metadata
review to supply that missing input. It has **local validation only**. Docker is
unavailable in the engineering environment; the new template and actual access
paths have not been observed on Kali. No current host state or global exclusivity
is claimed. The prior readiness, inventory and guarded handoff acceptance remain
valid at their recorded revisions and need no unchanged rerun.

## Exact observation scope

The collector reads the already accepted private readiness report, anchored by
SHA-256 `5a6c1064aa4cfc43a18a2f589e88e7476de8636306a343af41c801483303df90`.
It looks only under the existing `radar-r1-readiness-*/results/report.json` paths
in the supplied baseline root, at most 64 candidates. Missing, unsafe or changed
baseline evidence prevents Docker observation. The historical report remains
untouched; its binding was rechecked offline during development.

One invocation uses only the fixed trusted local Docker binary and socket with a
new empty client configuration. There is no arbitrary endpoint, context, command,
container selector, provider, credential or executable argument. Requests are:

1. One `docker ps --all --no-trunc` ID census, including stopped containers.
2. Two bounded metadata snapshots of those exact IDs, in batches of two.
3. One closing ID census, with source hashes checked before and after collection.

The target ID, image, PID/start generation and `/app/data` source/type/writability
must still match the accepted baseline. A changed target or volume produces a
specific unavailable result; it is not silently rebound. All snapshot fields
must match across the pass. Only mount-array and capability-list ordering are
normalized; a changed mount value, generation, census or source stops the pass
without retry or export of a successful partial inventory.

At most **64 containers, 32 mounts per container and 66 Docker requests** are
permitted. Nineteen containers require 22 requests. Each request retains the
existing four-second/16 KiB stdout limit; stderr is discarded and only the owned
CLI child can be reaped. A 90-second monotonic guard is checked before/after each
request and before completion. Filesystem/kernel stalls are not a hard real-time
guarantee. No adaptive widening, retry, monitoring loop or timing rehearsal exists.

The collector creates no containers and performs no start, stop, restart, update,
exec, build, pull, deployment, funding, signing, sending or trading operation.
Writes are confined to the new review output and temporary empty client config.
It never reads environment/command values, mounted contents, host process lists,
credentials, wallet journals, RPC, provider usage or Backblaze.

## Findings and redaction

| Recorded relationship | Meaning for review |
| --- | --- |
| Known local Docker socket source, or an ancestor directory | Declared path exposure needing ownership review, including read-only binds |
| Other engine socket filename, or an engine-socket destination with a renamed source | Possible additional control path; effective API access is untested |
| Source overlapping the scanner data directory | Declared read or write path, distinguished by mount RW; lexical paths only |
| Privileged mode, added capabilities, host/nondefault PID namespace or host networking | Broader configuration requiring workload-specific review |
| Shared/slave propagation or unavailable propagation metadata | Additional uncertainty about the visible mount tree |
| No matching findings | Unclassified workload; never approved, harmless or globally excluded |

The `/var/run` and `/run` spelling alias is handled lexically. Arbitrary aliases,
symlinks, permission/ACL checks and socket API calls are not resolved or tested.
A mount's read-only flag is not treated as proof that socket API control is
unavailable. The findings describe configuration paths, not demonstrated misuse.

Raw source/destination paths, namespace strings and capability names stay in
memory. Output contains IDs, image hashes, running/PID/start metadata, fixed
finding categories, declared RW/propagation, counts and fingerprints. Optional
missing propagation stays explicitly unavailable. No environment or command
values are requested. Unknown exceptions and Docker diagnostics are reduced to
fixed error categories; their raw text is never exported. Hashes bind metadata
relative to trusted evidence and producer pins, not an independent host attestation.

Every report keeps production mutation, provider access, global exclusivity,
effective-access verification, activation and automatic resume false. Host users,
groups, ACLs and processes; other daemons/machines; remote APIs; custom aliases;
device/kernel access; provider ownership; and changes between or after samples
remain explicitly outside scope. This report cannot release E0 holds or approve
production rollout.

## One new bounded Kali input

From a fresh clean checkout of the exact bundled source named `source`, beneath
a private review directory, run once:

```bash
bash scripts/r1-production-authority-kali.sh \
  5a6c1064aa4cfc43a18a2f589e88e7476de8636306a343af41c801483303df90
```

This invokes no unit suites or disposable-container rehearsals. Return
`results/production-authority.zip` whether it reports
`docker-authority-observed-review-pending` (exit 0) or unavailable (exit 1).
Exit 0 means the bounded observation completed, not that the configurations are
acceptable. On failure preserve the output; do not change permissions, replace
the baseline, retry, or rerun the older readiness/inventory tests unchanged.
An unexpected local cleanup failure retains whether observation occurred and
the known request count; it cannot claim that no host check was attempted.

After reviewing this input, identify the specific container/control/data paths
that still need an ownership decision. An empty finding list cannot close the
excluded host/account/other-machine scope. Further work must name a concrete
remaining dependency; no repeated census or automatic production mutation follows.

## Validation

**79 production-review tests** pass, including 20 new authority tests; the
**52 deployment tests** also pass. They use modeled command responses and
temporary private output, not Docker. Coverage includes socket/ancestor/renamed
paths, read-only socket declarations, lexical boundary false positives, target
data overlap, stopped containers, array order, changed generations/mounts/census,
redaction, source drift, bounded request sets, malformed output, deadline/clock
failures, missing baseline and local cleanup failure after an observation.

The actual Docker template and current host metadata remain the new Kali
dependency. Previously accepted handoff tests are not part of this request.

Primary Docker documentation reviewed November 17, 2026:

- [Docker Engine security](https://docs.docker.com/engine/security/)
- [Bind mounts](https://docs.docker.com/engine/storage/bind-mounts/)

E0 remains blocked with holds preserved. Its last accepted operational/RPC
observation is November 9, 2026, 18:50:41 CET. No new closure evidence or balances
were obtained here. Production resources/stop behavior, credential integration,
remote preservation/retention and explicit pilot terms remain separate gates.
