# R1 reusable session and portable evidence candidate

This increment replaces the fixture-specific coordination assumptions with a
reusable **library** and an offline acceptance batch. It is not a production
launcher. The executable checker generates synthetic input only, blocks Internet
sockets/DNS, and has no provider credential, B2, wallet, Docker or production
target argument. Existing accepted fixtures remain available at their original
source revisions; this work does not repeat their B2 transfers.

## Session lifecycle

`session.run(control, ipc, factory, limits, stop=event)` consumes a fresh private
control directory before opening a discovery endpoint. It waits for one same-UID
Unix consumer before invoking the caller's reviewed `Wire` factory, makes one
upstream attempt and one research attachment, and never reconnects. Capture runs
on a separate thread. Limits cannot exceed the draft's messages/bytes/time/watch
ceilings; the recorded sample modulus may vary for offline tests. This is not
approval of any measurement selection or exposure terms.

The upstream reader waits until the capture journal's start record and first
heartbeat are complete. An event already queued when connection setup returns
is therefore offered to capture instead of being lost before research attaches.
This does not prove provider history or initial-event completeness. Bounded wire
and channel queues can still overflow; that remains a failure, never a reconnect.

Receive polling uses a non-cancelling wait on one retained receive task, bounded
by 50 ms and both remaining capture clocks. Capture expiry needs no artificial
receive exception and no cancelled shield. A receive TimeoutError is retained
as a transport failure; it is never mistaken for a poll timeout. No deadline is
extended. The independent lease/watchdog remains conservative under
delayed scheduling. Operator stop, failed sends, failed cleanup and upstream errors
stop the session, preserving their actual journal outcome.

After capture stops, the coordinator closes the whole upstream/discovery session
and joins the capture thread before writing `stopped.json`. This bounded candidate
does not leave discovery running indefinitely, restore direct mode or change a
production restart policy. Production handoff/rollback must still be integrated
with the separately reviewed lifecycle coordinator and real supervision profile.

Cancellation, source drift, failed startup, failed close, an unjoined worker or
failed receipt write produces no completed marker. The source directory stays
consumed and is never repaired, overwritten, deleted or resumed by this library.
The directory is a cooperating-process guard, not a host-wide or tamper-resistant
lock. The caller must supply the global handoff/registry boundary before live use.

Startup waits are bounded (peer 3 s, capture setup 3 s, existing owner connect
5 s); capture uses its recorded duration, with a 3 s outer grace. Shutdown waits
at most 3 s for the thread. Python cannot forcibly kill a stuck thread: the
enclosing process supervisor must kill/reap the process, and such a run has no
completion receipt. A production process supervisor, credential provision and
provider TLS acceptance are still required. No security boundary is claimed for
an arbitrary injected Python factory.

## Arbitrary-session preservation

`archive.export` accepts a completed candidate run with any valid capture size
and identity, rather than one of three fixed synthetic hashes. It obtains the
existing run/capture locks, rejects rollback evidence, missing stop receipts and
unexpected members, and replays copies of the capture and measurement journal.
It never opens the source SQLite database. Original bytes and file/directory
identities are checked again before output.

The deterministic four-member archive contains admission, stop receipt, complete
capture/journal session and an exact manifest. Restore requires an independently
supplied SHA-256, bounds ZIP metadata before parsing, replays the capture/journal,
and checks receipt/limits/command bindings. Both successful and failed sessions
can have complete evidence; the archived outcome is never promoted from failure
to success. Restores go to a new evidence directory, not a resumable service.

Hashes detect inconsistency, not producer authenticity. A locally claimed close
does not establish provider acknowledgement, billing cutoff or historical
coverage. No archive grants production or live authority. Incomplete runs remain
in their original directory for review; this exporter does not label them complete
or erase SQLite rollback files.

Raw payload allowance remains 8 MiB, the capture DB at most 32 MiB and the
measurement journal at most 8 MiB. Archive/member bounds are derived from the
existing formats. A conservative 512 MiB **available-space sample** is required
before a run/export/restore; it is not a reservation, ongoing free-space monitor,
global quota or proof against competing disk use. No rotation or deletion is
implemented. Keep run originals, admission/stop evidence, archives, hashes and
matching source revisions pending review. An approved live retention duration,
capacity allocation and off-machine lifecycle are still missing. The fixed B2
rehearsal adapter is deliberately not generalized or activated by this increment.

## Measurement correction and source identity

The draft evaluator previously treated all completed commands as completed
subscriptions, rejecting a valid session once an ordinary watch-expiry unsubscribe
was recorded. It now uses the latency distribution's subscription count for the
selected-subscription completion fraction and latency bounds, while retaining all
command completions for intent conservation. A real synthetic watch-expiry path
exercises capture, unsubscribe, replay, evaluation, archive and restore together.
The draft approval flags and numeric criteria are unchanged.

This correction changes `r1-registration/contract.py` and its tests. Consequently
new contract/source fingerprints differ. The already accepted B2 package and
historical receipts must continue to be reviewed with their pinned implementation
`04209213b38fdc29a37e0b830bc10cc09ed3f294`; they must not be relabelled as produced
or accepted by this new revision. No historical package is rewritten.

## One consolidated Kali acceptance

Run `check_session.py --output-directory NEW_PRIVATE_PATH` with the existing
hash-pinned wire dependency. It runs the affected capture/measurement/wire/shared
session suites, draft-contract tests and new candidate/archive tests in one batch.
Then eight retained scenarios cover normal and different-size sessions, idle
expiry, watch expiry, operator stop, failed send, provider error and failed cleanup.
Each exports and independently restores its complete evidence.

Kali's default mode requires real Unix IPC in every retained scenario and the
existing Node scanner adapter in normal, cleanup-failure, watch-expiry and
different-size scenarios. There is no fallback if Unix IPC fails. Unit-test
endpoints remain explicitly simulated, with peer verification false. The optional
`--development` mode uses simulated endpoints for retained scenarios as well;
its status cannot pass Kali IPC acceptance.

Upload **acceptance.zip**. It contains report.json, validation.log and all eight
archives. Preserve the full output, including on failure; then supply report.json
and validation.log if no acceptance bundle was completed. The checker rejects
failures, errors, skips and captured resource/unraisable/async diagnostics,
including Python 3.14's `exception in shielded future`. The log covers both unit
tests and retained scenarios, including worker-thread stderr and archive restore.
Failed batches retain their log and failed report without granting acceptance.

The earlier uploaded batch at `e8b4df8f6add1ec3b0f6ca8781a8e689e84c9c07`
reported 157 passing tests but emitted two such diagnostics. Its source hashes,
eight archives, receipt bindings and isolated restores matched on independent
review; its clean acceptance was rejected. Retain it unchanged as historical
evidence and use the corrected source for one replacement consolidated batch.

Expected Kali status: `candidate-session-offline-passed-live-blocked`.
Development status: `candidate-session-development-passed-unix-pending`.
Neither means a live provider, actual production rollback, long-duration soak,
remote retention, source adequacy, approved pilot or profit-study registration
passed. The total five-working-day engineering cap is unchanged; remaining effort
is unknown without an effort ledger. E0 remains separate and held.
