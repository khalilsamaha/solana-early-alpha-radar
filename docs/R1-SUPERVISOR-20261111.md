# R1 offline process supervision — accepted on Kali

Date: 2026-11-11. This increment follows Kali acceptance of provider wire commit
`a2fdf5802e4728e75b6b0afc5408a7a84488dd0f`. It implements the process supervision
and local preservation part of the guarded launcher. It is deliberately an
**offline synthetic rehearsal**, not a complete live launcher or activation gate.

## Supervisor Kali acceptance

The report `radar-r1-supervisor-offline-20261111T143934Z-1091449.json` for
`1e8bed1aa3158db93ee0000c3f0af78733208236` passed review: 241 tests,
zero failures/errors/skips; all 33 source hashes matched. Python 3.14.6 /
SQLite 3.53.4 / websockets 17.4; 7.623608 seconds overall; the reaped worker
completed in 0.314780 seconds with source preservation and local replay.
Report SHA-256: `877bc3d819d59e567cb5682bd5d075a56c4276503080b33a486774fbfe26765f`.
No live connection or funding acceptance is implied. The following records
this completed increment; current work is in `R1-MEASUREMENT-20261111.md`.

## Accepted preceding evidence

Uploaded `radar-r1-wire-offline-20261111T142405Z-1056782.json`:

- SHA-256: `843e1a65b370a23b0eacd5ed26d2955538adf859390796e60f2d9a338ab5023b`.
- Status: `offline-provider-wire-passed-live-blocked`.
- 227 tests, zero failures/errors/skips; 3.492902 seconds.
- Python 3.14.6, SQLite 3.53.4, websockets 17.4.
- All 30 source hashes independently matched the reviewed tree
  `243fc9436d3cf5ac07d92677280657b8f706be25`.
- Synthetic source preservation and local restore passed; Internet socket/DNS
  guard enabled. No provider connection, TLS handshake, credential loading or
  paid collection. Connection coexistence is still unaccepted.

This accepts the wire's stated offline scope, not the full R1 gate.

## Later complete-session resource revision

The complete-session increment raises only the per-file ceiling from the
36 MiB documented below to 44 MiB, to fit the combined bounded capture/journal
archive. Other limits remain unchanged. See `R1-SESSION-BUNDLE-20261111.md`.

## Implemented behavior

`supervisor.py` takes an existing private owner directory and creates a new
private `run-<random>` child. A nonblocking file lock spans manifest creation,
worker execution, receipt validation and final reporting. The lock inode is
retained between runs. Symlink/aliased owner paths, public owner folders and
unsafe lock files are rejected. This lock coordinates **only cooperating runs
using that same directory**. It does not coordinate with the existing scanner,
other directories or other accounts and does not resolve provider coexistence.

The manifest binds the five implementation source files, fixed synthetic mode,
parent PID, run identity, capture limits and resource limits. The child checks
it before creating a capture. There is no live switch, endpoint override,
credential argument, funding approval flag or wallet access. The supervisor's
internal subprocess primitive is not exposed as an arbitrary-command CLI.

The fixed Python worker runs with `-E -s -B -W error::ResourceWarning`, closed
inherited descriptors, null stdin/stdout/stderr, and only LANG/LC_ALL/PATH in its
environment. Raw tracebacks and child output are never included in reports;
a child output flood cannot accumulate in parent pipes. Each run starts at most
one worker and has no retry/resume path. It does not inherit provider keys,
proxy settings, HOME or PYTHONPATH.

The Linux child sets and verifies these soft and hard limits:

| Control | Bound |
| --- | --- |
| Address space | 256 MiB |
| CPU | 5 seconds |
| Individual file size | 36 MiB |
| Open descriptors | 32 |
| Core dumps | Disabled |
| Child wall alarm | 10 seconds |
| Parent wait | 12 seconds from supervision start |
| TERM cleanup wait | 0.25 seconds |
| KILL/reap wait | 1 second |

Address space and individual-file limits are not a total RSS or directory quota.
The parent sends TERM then KILL as needed to the worker process group, reaps the
worker and restores its signal handlers. Operator SIGINT/SIGTERM records an
interrupted failure. Linux parent-death SIGKILL plus a parent-PID check handles
loss of the supervisor, including the race before the child installs that setting.
A child alarm remains separate from asynchronous transport cancellation.
These are tested process controls, not a hard real-time guarantee for OS process
creation, scheduling or uninterruptible filesystem I/O. Cleanup not confirmed
within its wait cannot produce acceptance.

The worker independently installs Python audit guards rejecting Internet
sockets, DNS, fork/exec and subprocess creation. AF_UNIX socket pairs remain
available to asyncio. These guards protect this trusted offline Python path;
they are not an OS sandbox for arbitrary native or hostile code. They do not
make the provider wire's live socket factory available in this worker.

## Preservation and failure semantics

The real capture/controller receive four synthetic frames from an in-memory
fixture. The fourth frame stops at the message cap; the fixture is aborted and
closed. The worker exports the closed database using the accepted handoff code,
restores it, replays it, and compares original bytes before/after preservation.
The child receipt binds the manifest, resources, session result, database hash,
package hash and package size. The parent checks the receipt's schema and
fixed expected result, source stability, unchanged manifest and retained bytes.
Only a zero child exit plus valid evidence can pass. The session's one opened
connection is **one synthetic fixture**, not a provider connection.

Nonzero exits, deadlines, interrupts, missing/altered/oversized receipts and
changed package bytes fail. Failed or abruptly killed runs retain existing
artifacts; an active/unclean SQLite capture is not reopened, repaired, resumed
or promoted into an accepted archive. An unclean-shutdown test verifies the
database remains byte-identical and replay refuses acceptance. A failed run
must be reviewed, not automatically retried with a fresh budget.

Standalone rehearsal retains its private run files. The acceptance runner uses
only temporary synthetic directories and explicitly reports their removal;
it returns the process/receipt evidence in the uploaded JSON. This increment
does not repeat the accepted B2 rehearsal or prove live-capture backup coverage.

## Validation and Kali action

Development validation: **241 tests**, zero failures/errors/skips, including
14 new supervisor tests. Tests use real Linux subprocesses for normal completion,
resource and network/spawn enforcement, output floods, nonzero exits, deadlines,
TERM-resistant forced kill, parent death, operator interruption and unclean
capture preservation. Additional cases reject unsafe ownership paths, competing
runs, manifest substitutions and modified evidence. Source hashing now covers
33 files. The complete development runner finished in 3.549630 seconds on
Python 3.12.14 / SQLite 3.53.1, with ResourceWarning treated as an error. The
pinned portable websockets 17.4 requirement is unchanged.

Fetch the supplied exact commit/tree into a new isolated review directory,
create its venv, install `requirements-wire.txt` with mandatory hash checking,
then run `r1-data/check.py`. Expected status:
`offline-supervisor-passed-live-blocked`, 241 tests, successful supervision
receipt and synthetic local restore. Upload the single report. No API key,
sudo, funding, scanner restart, cloud repeat or provider connection is needed.

## Remaining sequence and effort cap

1. Accept this supervisor increment on Kali.
2. Resolve the already-recorded one-connection policy: explicit provider
   confirmation for the exact coexistence model, or a separately approved and
   validated shared connection that preserves scanner discovery when R1 stops.
3. Complete the live-launch contract: private credential loading, ownership
   coordinated with that connection model, fixed measurement/exposure terms,
   actual-capture preservation coverage and retention. This offline supervisor
   is reusable infrastructure, not acceptance of those remaining controls.
4. Validate the real host TLS/session under the accepted connection model and
   obtain the owner's explicit numeric funding decision before paid collection.
5. Only after the full gate passes Kali, consolidate for PR/CI and the owner's
   merge decision; then consider the separately authorized measurement pilot.

Continue independent offline preparation while the policy is unresolved. Do
not open a second provider socket, assume a different key/host is permitted,
change production discovery, fit ML, or reset the original five-working-day
R1 build/validation effort cap. No new calendar promise or profitability claim
is established here. If the policy cannot be resolved within the cap, record
R1 as blocked/insufficient and reassess scope instead of adding diagnostic gates.
