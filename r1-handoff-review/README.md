# Read-only handoff inventory and blocked prerequisites

This prepares the production binding evidence needed after offline admission
acceptance. It never changes the scanner, service policy, permissions, credentials,
provider connections, holds or retention. It does not perform a production handoff.

The fixed target is `solana-early-alpha-radar-radar-1`, through the trusted local
`/usr/bin/docker` and `/run/docker.sock`, with an empty temporary Docker config and
a minimal environment. No target, executable, remote daemon or arbitrary command
argument is accepted. There is no Docker exec, service restart/stop, network probe,
RPC call, key lookup, environment dump, command-line read or mount/label listing.

## Single bounded observation

At most four allowlisted Docker inspections run: resource settings before and
after the existing two-inspection host identity observer. Each command has the
existing four-second/16 KiB bound; stderr is discarded. Identity uses bounded
proc UID/GID, start-time, namespace, child and cgroup evidence. It rejects PID reuse,
ambiguous process selection and changing container/resource identities rather than
combining observations from different processes. These consistency reads are one
bounded observation, not a repeating monitor or timing rehearsal.
These checks cannot prevent state changing after observation or make the reads an
atomic host snapshot. Test diagnostics are rejected before any host observation.

The new metadata is container memory/swap/PID/CPU settings. Zero, null and minus-one
values retain Docker's raw meaning; no safe operating or financial ceiling is
inferred. Two allowlisted `/proc/meminfo` counters give a point-in-time memory sample.
`statvfs` samples only the review output filesystem. It does not identify production
mounts, measure live capture storage, reserve capacity or prove a retention budget.
The initial and final host wall timestamps are recorded in UTC; neither is externally
attested. The prior accepted image is comparison context, not an assumed current image.

Output is exactly three new private files:

- `report.json`: source fingerprints, offline test results, bounded observation or
  explicit unavailability, timestamps, authority-denial fields and prerequisite hash.
- `prerequisites.json`: observed candidate identity/resource binding (or null),
  findings and the fixed unresolved production gates. It is always blocked.
- `validation.log`: only the offline test log; never raw daemon stderr or credentials.

Missing access or a changed identity produces an unavailable report and leaves every
gate open. It does not request elevated permissions, guess a PID or try another host.
Existing output is never replaced. Temporary empty Docker configuration is removed;
observed services and all returned evidence remain unchanged.

## Remaining gates

This metadata cannot prove the unique global connection owner, an upstream socket's
closure, the stable future registry/endpoint, production IPC peer identity, credential
provisioning, actual rollback, or provider/session historical completeness. Those
fields remain false or unresolved. The observation does not approve funding, live
activation, long-running supervision, measurement terms or retention allocation.

The accepted admission implementation is referenced as
`685d6359551c2eb69f4ccb37c06bf6424176cedf`. It remains offline; all its source pins
are unchanged by this separate package. The eight-step production lifecycle still
requires concrete reviewed adapters/receipts and specific rollout authority.

## Kali command

Run `scripts/r1-handoff-inventory-kali.sh` once from a fresh pinned checkout named
`source` under a private review directory. It uses Python's standard library only,
runs the new offline tests and makes one bounded read-only observation. No dependency
installation or provider connection is needed. Its enclosing limit is 45 seconds
plus five seconds to terminate the observer if needed; the production service is
never a signal target. No repeated session, Docker fixture or backup batch runs.

Return all three output files. Either `handoff-inventory-observed-rollout-blocked`
or `handoff-inventory-unavailable-rollout-blocked` is an honest observation result;
neither grants rollout. If unavailable, preserve the report for review instead of
changing permissions or retrying automatically. There is no schedule, polling loop
or automatic next action. E0 remains independent and held.
