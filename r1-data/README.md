# R1 offline capture, transport controller and source metadata probe

The capture core is Kali-accepted at `f92e4d1`. This second increment adds an
offline-tested subscription controller and a read-only source metadata probe.
It has **no real network adapter, credential-file reader, network client, trading operation,
profitability evaluator or curve reconstruction**. It cannot activate paid data.
No change to the production scanner, frozen studies, E0 or CI is required.

## Kali acceptance

From a pinned isolated checkout, run:

```sh
python3 -E -s -B -W error::ResourceWarning r1-data/check.py --output /absolute/new/report.json
```

No third-party dependencies are needed. Linux/Python 3.11+ is required (flock,
private POSIX files and SQLite). The report must be a new path in an existing
directory. The runner executes all `test_*.py` checks and then a synthetic
capture/restart/budget-stop/export/restore/replay exercise. Tests use private
temporary directories and remove them afterwards. No scanner database, existing
capture, environment credential or wallet is read. Report contents include code
hashes and runtime versions, not raw provider payloads or credentials.

Expected status: `offline-transport-passed-live-blocked`, zero failed/errored/skipped
tests, `local_restore_replay_passed: true`. This is not acceptance of feed quality,
an off-machine backup, reconstruction, billing, profitability or the full R1 gate.
Use `python3 -E -s -B -W error::ResourceWarning -m unittest discover -s r1-data -v`
for detailed local synthetic-test diagnostics if the runner stops.

The current suite contains 72 tests. The earlier 44-test report remains accepted
for its original pinned source; it does not validate the added code.

## Source metadata probe on Kali

After offline checks, run the separate probe with the application project path:

```sh
sudo python3 -E -s -B -W error::ResourceWarning r1-data/source_probe.py \
  --project "$HOME/apps/solana-early-alpha-radar" --output /absolute/new/source-report.json
```

The project folder need not contain Git metadata. The probe uses only local
Docker socket inspection, filtered by the Compose working-directory and radar
service labels, to locate `/app/data`. It does not load `.env`, inspect container
environment values, restart containers or open a provider connection. Sudo is
needed to read Docker's named volume; only the probe needs it. Under sudo, the
private output is assigned back to the invoking user.

The database is opened `mode=ro` / `query_only`. The read transaction is bounded
to three seconds, 128 recent creation records and 4096 bytes per record using the
existing receipt index; no fallback table scan is allowed. Docker discovery has
two five-second command timeouts. The report exports non-null/absent field counts
and timing only, not source payloads, signatures, wallet addresses or outcomes.
Field presence is not field validity or chain verification. SQLite may use its
normal WAL read coordination; the tool performs no row/schema changes.

`creation-metadata-observed` means some existing creation metadata was read.
`creation-metadata-insufficient` and `source-metadata-unavailable` remain explicit
non-passes. All three states retain `source_complete: false` and
`live_activation_allowed: false`. Upload the source report even if unavailable;
do not substitute a guessed database path. `--database` exists for explicit
verified paths and synthetic tests, not automatic discovery fallback.

## Transport controller boundary

`transport.run_session` accepts an injected asynchronous wire. It opens at most
one session, serializes and rate-limits the four permitted subscription methods,
expires watches even during silence, unsubscribes on migration, stops on gaps,
and aborts before bounded cleanup when a capture limit is reached. It never
reconnects or treats a control message as proof of subscription acknowledgement.
Tests use only synthetic in-memory wires. There is no live launcher and no
WebSocket dependency to install for this increment. Real TLS/handshake/buffering,
provider compatibility, credentials and billing have not been exercised.

## Contracts

- The input interface accepts **bytes from an offline fixture/injected source**.
  A future transport must honor `tick()` during silence, stop consuming when the
  core stops, and invoke `gap()` on disconnect. No unattended live timing or
  network-buffer behavior is claimed by these offline tests.
- Default limits: 20,000 received messages (including discarded controls), 8 MiB
  raw payload, 64 KiB per frame, 48 hours, ten-minute planned watches, at most two
  concurrent and 24 daily planned watches, deterministic SHA-256 mint sampling
  at 1/64. These are conservative feasibility defaults, not a registered study.
- The SQLite main file is limited to 32 MiB; allow up to another 32 MiB plus
  journal headers during a transaction. Export and restore each need a separate
  additional bounded database copy. Future launch preflight must reserve this
  space and implement retention; this core installs no scheduled cleanup/backup.
- `ticks.db` is separate and private. A process lock prevents concurrent writers
  or exporting an active session. Counters, absolute deadline and terminal stop
  state persist. A clean restart records a gap and ends all prior planned watches.
  An unclean process exit stops the capture permanently when reopened. A transport
  disconnect also stops rather than pretending historical recovery exists.
- No automatic retry, top-up or new capture is performed on budget exhaustion.
  An explicit new directory is a new capture, not an authorized new spending
  allowance. These counters are not a provider billing enforcement mechanism.
- Creation sampling and capacity exclusions are recorded for every valid observed
  creation event. This describes the observed input stream, not all on-chain
  launches. Duplicate creation events are retained without creating a new watch.
  A signature is not used to collapse trades: one transaction may contain several
  events. Receive ordering is not asserted to be chain ordering or finality.
- Raw accepted event bytes, local receive timestamps and decisions have per-row
  SHA-256 and a chained digest. Replay also checks the materialized mint state
  against the event/gap history. Export uses a closed capture and a whole-file
  checksum manifest. Restore refuses replacement, altered bytes and extra members.
  Digests detect corruption relative to retained pins; they are not signatures
  authenticating a provider or protection against rewriting all local evidence.
- Unknown/malformed events, missing mint/signature identity, oversized frames,
  explicit provider errors, sensitive field names and known credential echoes
  stop capture. Provider error and acknowledgement text is discarded. A future
  transport **must supply its credential and relevant secret variants** through
  the in-memory `redactions` argument; no generic detector recognizes every secret.
  Never persist URLs containing an API key. No real credentials are needed here.
- Reports explicitly leave ledger order, initial state, subscription installation,
  billing-limit verification and profitability false. `watch-planned` is a plan,
  not an acknowledged provider subscription or proof of complete observations.

## Remaining before paid activation

Review the new Kali evidence; resolve the existing scanner/PumpPortal connection policy;
establish a viable verification path for required source fields, early-event
capture, ordering, finality and recovery; implement and validate the network adapter; agree the
explicit deposit and fee exposure; demonstrate off-machine preservation/restore.
Reuse the existing dedicated PumpPortal-linked wallet if suitable. Do not fund it
for this offline acceptance. A separate devnet rehearsal wallet is not the
provider-linked data wallet.

The paid pilot is intended to measure source quality, not to assume it is already
proven. Its limited discovery purpose and explicit budget require approval before
activation. Full evidence quality and reconstruction acceptance are prerequisites
for a confirmation study, not claims made by the metadata probe.

Development branch publication is allowed for Kali review. PR/CI consolidation
waits for the complete agreed gate and applicable Kali acceptance.
