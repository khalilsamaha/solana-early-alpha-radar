# R1 session evidence review and timeout correction — 13 November 2026

## Disposition of uploaded evidence

Do not accept the uploaded batch as a clean Kali result despite its reported
`candidate-session-offline-passed-live-blocked` and 157 tests with no failures,
errors or skips. Its validation log contains two `TimeoutError exception in
shielded future` diagnostics, during idle expiry and complete failed-evidence
restore tests. The original diagnostic matcher missed that Python 3.14 wording.

The review inspected supplied artifacts; it did not connect to Kali, a provider,
RPC or B2. Recorded scenario journal timestamps range from 2026-11-13
06:21:15.704903 UTC through 06:21:26.779367 UTC. These are artifact timestamps,
not independently observed host time. No current balance is asserted.

Input identity:

- Producer source: `e8b4df8f6add1ec3b0f6ca8781a8e689e84c9c07`;
  tree `ce245cf54c1a961d03181efe355a8adc9d8f7658`.
- acceptance.zip: 542061 bytes;
  SHA-256 `61f8e5781ec703a54a1c20a74faef7a8690e59b4252ef5666bd769e2a2f28a1b`.
- report.json SHA-256:
  `b5acfcaa25e92bcdba04dde8cd67721467ef56dc0a52bd10f4b4c971b760d075`.
- validation.log SHA-256:
  `2aa4bc00de30d5edaa3a0368b35ebc70388dc349ccf6b1ea464e855e4c034f14`.

All 156 source hashes matched the producer implementation before edits. All eight
archive byte lengths and hashes matched. Each archive passed independent manifest,
receipt, capture/journal replay and isolated restore checks against that source.
Normal, different-size, idle and watch-expiry outcomes remained capture-stopped;
cleanup, send, provider and operator-stop failures remained failures. No failure
was promoted by restore. Four retained scenarios reported actual Node discovery
consumers, and all eight reported verified Unix peer identity. Upstream input was
synthetic. These narrow findings do not override the dirty diagnostic log.

## Correction

The shared controller now polls one pending receive task using `asyncio.wait`,
without cancelling shield futures. Its wait is bounded by 50 ms and the remaining
wall and monotonic capture durations. The capture owns its expiry; ReadyLease no
longer injects TimeoutError at that deadline. A genuine receive TimeoutError is
consumed and recorded as a transport failure, rather than confused with polling.
Cancellation still cancels and awaits the pending task before cleanup. No time,
watch, message or exposure ceiling is increased.

The checker rejects shielded-future, unretrieved-future, destroyed-task,
callback/thread, resource, runtime and unraisable diagnostics. stderr capture now
covers retained scenarios and archive export/restore, including joined workers,
in addition to unit tests. Failed batches retain a failed report and diagnostic
log. New regressions cover delayed receive failure after several polls, a clean
unittest exit with diagnostics, and a worker diagnostic during a retained scenario
that must prevent creation of acceptance.zip.

## Local validation and required next check

The corrected combined batch passed 160 tests, zero failures/errors/skips and all
eight retained scenario export/restores in 16.722232 seconds on Python 3.12.14.
No diagnostic matched. All 157 source fingerprints stayed unchanged during the
batch. Development endpoints were explicitly simulated; this environment cannot
supply native Unix acceptance or Python 3.14 verification.

- Status: `candidate-session-development-passed-unix-pending`.
- report.json SHA-256:
  `7dfd297d423db3ee93ff59028053513cd0af3452eecb9cb86364561015b296e2`.
- validation.log SHA-256:
  `7368a47eab19cb39668cddcd17f4ea07b262494166a4ac80e2c367d544d3cb56`.

Run one replacement `scripts/r1-session-kali.sh` batch at the new pinned revision
in a fresh isolated checkout. Keep the earlier evidence unchanged. The script
requires native Unix IPC, uses Node in four retained scenarios, enforces a bounded
run and opens no provider connection. Return its single acceptance.zip on success;
otherwise preserve and return report.json and validation.log. This check writes
only isolated synthetic evidence and a temporary environment; it is not a live
host observation, production deployment or E0 transaction check.

## Agenda and unchanged gates

R1 remains at collector/preservation prerequisites. Before any provider pilot,
process/credential/global ownership and actual production handoff/rollback,
live retention/capacity, fixed measurement terms and numeric exposure approval
must be closed. No provider activation, main merge, B2 transfer or retention change
is part of this correction.

The November 12–18 five-working-day build allocation is unchanged; remaining
effort is not established. November 19 remains at risk, and no 21-day confirmation
window has started. Any future pass still requires 21 complete UTC days after
prerequisites and sealed approval; day 14 allows futility only. December 31 stays
the decision checkpoint. Do not recover the schedule by shortening evidence.

E0 is independent: last accepted operational observation remains November 9,
18:50:41 CET, blocked with holds preserved. No fresh E0 receipt, journal or
historical-coverage evidence was obtained in this R1 artifact review. November 20
may be complete only with required closure evidence; otherwise disposition stays
blocked-with-holds-preserved. Reopen E0 only on exact closure-relevant finalized
receipts, a material journal discrepancy requiring reconciliation, or credible
coverage evidence sufficient under its closure contract. RPC absence, expired
blockhashes and matching balances do not establish non-execution.
