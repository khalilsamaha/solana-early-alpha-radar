# Combined R1 integration candidate — offline executable only

This package connects a separated research/discovery session, a consumed global
**configured registry**, isolated service handoff/rollback, a finite candidate
resource profile, complete/interrupted evidence, and injected transfer validation.
It does not deploy production or open a provider/B2 connection. A configured
registry coordinates its cooperating callers; it is not host/IP-wide ownership.

## What is implemented

- `separated_session.py` keeps one shared Owner alive after clean research
  retirement. It retains an immutable retirement receipt before signaling the
  parent; no second research attachment or upstream reconnect is permitted.
  Discovery continues until explicit shutdown, upstream failure or its independent
  finite service deadline. Cleanup failure closes upstream. Normal shutdown binds
  the retirement receipt and joined capture thread to the final session receipt.
- `pipeline.py` consumes a stable registry before credential or actor startup,
  freezes the existing unapproved draft and binds all candidate sources, runtime
  profile, output and attempt. `adapters.py` joins the existing durable eight-step
  lifecycle to the new broker, actual Node consumer and owned disposable services.
  Restart policy is disabled before direct shutdown; restoration requires shared
  termination. A lost confirmation poisons the sequence; it cannot retry or restore.
- `profile.py` validates finite durations up to the draft's 172800-second ceiling
  plus separately bounded setup/shutdown. Kernel CPU/address-space/file/descriptor
  limits, parent-death SIGKILL, independent alarm and offline network/process guards
  are enforced by the worker. CPU is capped at min(duration+30,3600) seconds; this
  is a candidate operating bound, not measured long-duration adequacy or approval.
  The executable broker currently binds a 15-second service profile (40-second
  alarm), a five-second research fixture and fixed synthetic credentials. There
  is no live worker entry point, no real credential path or approval bypass flag.
- `envelope.py` packages arbitrary identities and sizes within explicit caps,
  not three fixed hashes. It binds frozen admission, profile, lifecycle, cleanup,
  worker/session/retirement receipts, exact capture DB and measurement journal.
  Complete sessions independently replay on disposable copies and reproduce the
  inner session package hash. Missing terminal evidence and interrupted lifecycle
  stay quarantined; SQLite rollback bytes are preserved without opening/recovering
  the original database. Fault-ready markers prove an injected fault was reached.
- Transfer consumes its directory before invoking its injected backend. Upload
  return alone is insufficient: exact bounded downloaded bytes, independent restore,
  final source checks and durable completion are required. Failed attempts preserve
  evidence and cannot be retried by this API. The batch uses an in-memory remote;
  no real B2 adapter, billing, remote-origin attestation or retention is claimed.

All legacy runtime modules and their accepted source fingerprints are unchanged.
Existing lifecycle receipts explicitly retain their synthetic scope. The new
candidate does **not** promote these receipts into production attestations or
implement a successful production closure/rollout contract. Process/Docker
termination in these fixtures concerns owned isolated actors and a synthetic
upstream, not closure of a real provider connection or its billing.

## Preservation and recovery limits

The exporter acquires existing lifecycle/capture locks, checks all selected source
bytes again before publication and never opens the source SQLite database.
Retained source, manifest and receipt hashes detect inconsistency, not authenticity
against someone able to replace the entire history. Cleanup receipts establish the
parent's recorded reaping of owned actors; they are not independent host attestation.

Flat allowlisted archive entries are stored without compression; ZIP metadata,
member sizes and an independently supplied SHA-256 are checked before replay.
The capture DB cap is 32 MiB, rollback cap 32 MiB + 4096, journal cap 8 MiB,
and small receipt caps are explicit in CAPS. The 512 MiB output-filesystem
preflight is a point sample, not reserved space, production volume capacity or
retention allocation. No evidence deletion/rotation is implemented. The injected
backend must itself impose real transport bounds before any future remote use;
this library cannot forcibly interrupt arbitrary Python callbacks.

Read-only `pipeline.inspect` validates the consumed registry and current source,
replays lifecycle evidence and, when present, verifies completion and the complete
portable envelope against the retained run. Missing completion stays unresolved.
It never writes, launches, retries, restores a service or releases authority.
Concurrent reads are historical evidence inspection, not an atomic live snapshot.

## One consolidated Kali batch

`scripts/r1-integration-kali.sh` uses the hash-pinned existing wire dependency and
runs new tests, then three retained cases:

1. Normal: new creation reaches the actual Node consumer after clean research
   retirement; then explicit shared shutdown and isolated direct restoration.
2. Cleanup failure: upstream aborts, original failure remains visible, and direct
   restoration occurs only after shared shutdown/reaping.
3. Interrupted shutdown: the stop_shared intent and reached-fault marker remain
   unconfirmed; all owned fixtures are cleaned up, no direct restoration occurs,
   and the envelope remains quarantined through restore and simulated transfer.

Default mode requires actual Docker/Unix with the already present pinned image;
it never pulls/builds an image or accesses production environment/data/credentials.
Eight uniquely named, ownership-labelled disposable containers are expected to
be created and removed across the three cases. The accepted reviewed source
mount is a fixture mechanism, not a production image deployment. No production
service is selected for mutation. If Docker is unavailable, the batch fails and
retains diagnostics; it does not change permissions or fall back automatically.

Explicit `--development` runs native Node processes through pipes with simulated
restart policy and no Unix-peer claim. It cannot establish Docker/Unix acceptance.
The test suite also checks all eight lost-confirmation points with a pure model,
profile alarm/guards in real subprocesses, registry reuse, receipt alteration,
active source locks, missing finalization, corrupt transfers and completion failures.
The final three retained scenarios test the real new broker/process integration.

Return `acceptance.zip` (report, log and three evidence envelopes). Keep all
original directories and any failure output. On failure return report.json and
validation.log and preserve the directory; do not repeat automatically.

Success statuses: `combined-development-passed-docker-pending` or
`combined-offline-passed-live-blocked`. Neither is full R1 acceptance.

## Remaining before production

Production adapters/attestation contract, verified new scanner image, approved
long-running profile/credential provisioning, actual retention/capacity allocation,
real remote transfer adapter, approved measurement/exposure amounts and explicit
production/provider authority remain open. The supported long duration has not
been exercised as a 24–48-hour soak. The draft is not a profitability-study
registration. The five-working-day cap is unchanged and remaining allowance is
unknown. E0 remains separate with holds preserved.
