# Read-only production-context package — 15 November 2026

The accepted native fixture has completed its bounded test. It does not identify
the currently running production scanner. Production adapter work therefore needs
fresh exact-target context rather than assuming an older container/PID/image is
still current. The new `r1-production-review` package obtains only that bounded
metadata and leaves every activation/rollout decision blocked.

It reuses the existing host-identity observer unchanged. One pass makes six
bounded read-only Docker inspect/ps requests around its bounded /proc identity
checks. The target and Compose project/service are fixed. Selected image/state,
resource, user/working-directory, network-mode and mount metadata are retained;
unknown, changed, inaccessible or malformed observations return an unavailable
report. No retries, container exec, production writes, source edits, permission
changes, provider/RPC calls or paid services are part of the host check.

Environment, argv/command, mounted contents, executable bytes and credentials are
not read. The metadata fingerprint covers only the allowlisted projection, not the
full scanner configuration. A single project-labelled running container cannot
prove global sole ownership. Full configuration and owner exclusivity remain
explicitly unverified even when all snapshots agree. Available capacity/retention
is not inferred from mount metadata.

The [local development report](evidence/r1-production-context-development-20261115.json)
records 16 passing tests with no failures/errors/skips. Tests cover snapshot and
process disagreement, changing/missing project membership, strict resource/types,
mount/path bounds, unknown fields, scoped read-only request construction, diagnostic
suppression, source drift, offline non-observation, false authority flags and
exclusive private reports. Its status is `production-context-offline-tests-only`;
no actual production observation was attempted in this workspace.

Run the new pinned `scripts/r1-production-context-kali.sh` from a fresh clean
checkout named `source`. Return `results/production-context.zip` whether observed
or unavailable. The archive contains the bounded report and test results. Keep
all directories; do not retry or alter permissions on a failure. This check
creates no test containers and does not repeat the accepted native rehearsal.

The supplied context will inform exact-target production adapter design. It
cannot authorize handoff, provide missing credential/resource/retention/pilot
approval, prove absence of another upstream owner or release E0 holds. Standing
R1-branch publication authorization remains in effect; main/production rollout
and the unchanged engineering cap are not extended by this package.
