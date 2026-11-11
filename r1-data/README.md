# R1 offline capture core

This is the first implementation increment of the R1 feasibility work. It has
**no live transport, credential-file reader, network client, trading operation,
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

Expected status: `offline-core-passed-live-blocked`, zero failed/errored/skipped
tests, `local_restore_replay_passed: true`. This is not acceptance of feed quality,
an off-machine backup, reconstruction, billing, profitability or the full R1 gate.
Use `python3 -E -s -B -W error::ResourceWarning -m unittest discover -s r1-data -v`
for detailed local synthetic-test diagnostics if the runner stops.

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

Review Kali evidence; resolve the existing scanner/PumpPortal connection policy;
establish required source fields, early-event capture, ordering, finality and a
recovery source; implement and validate the isolated live transport; agree the
explicit deposit and fee exposure; demonstrate off-machine preservation/restore.
Reuse the existing dedicated PumpPortal-linked wallet if suitable. Do not fund it
for this offline acceptance. A separate devnet rehearsal wallet is not the
provider-linked data wallet.

Development branch publication is allowed for Kali review. PR/CI consolidation
waits for the complete agreed gate and applicable Kali acceptance.
