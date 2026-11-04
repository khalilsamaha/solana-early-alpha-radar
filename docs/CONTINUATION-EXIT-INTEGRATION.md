# Continuation signer and transport rehearsal — 4 November 2026

## Accepted predecessor

Kali report `radar-continuation-check-20261104T183734Z-2517242.json.gz`, captured
18:45:58 UTC, passed all 25 portable continuation cases and 14 independent Node
contract cases. Archive SHA-256:
`d13f852a9084f9ecda1cdcaf83c56733a330b02500cd51bafa620e2047dbebbb`.
The report used disposable fixtures; no continuation signature, real RPC, user
wallet, production ledger update or send occurred. This accepts the record and
independent validation contract, not a completed devnet exit.

## Host integration accepted on the diagnostic rerun

Kali report `radar-continuation-integration-20261104T185655Z-2587155.json.gz`,
captured 19:00:49 UTC (20:00:49 Amsterdam), returned **review-required**, with only
11 fault cases passed. Archive SHA-256:
`a355ce31b0da215f521c87ff9e9558af8a9b11f285865e075662623121abec47`.
Connected elapsed time, stage and diagnostic were all null. No independent
contract results were present. The report confirms no real RPC, production wallet
access or production ledger update, and removal of disposable fixtures. It does
not establish where the connected test failed or how far fixture signing reached.

This earlier report was not accepted and consolidation was held. The diagnostic
rerun `radar-continuation-diagnostic-20261104T190941Z-2630533.json.gz` passed at
19:13:19 UTC (20:13:19 Amsterdam), archive SHA-256
`9d411383143463911662dd29172873209d44bc3cd580073e4d1b49987f195117`.
All 16 fault/connected cases and 14 independent signer cases passed; every
phase completed. The connected attempt took 5,550.364 ms, with reported deadline
headroom of 5,874 ms, 20 collection requests, five sender requests, one synthetic
signature/send and recovery without another send or releasing reservations.
The whole fixture/rehearsal includes deliberate predecessor-expiry waits and is
not the measured execution attempt. The earlier failure did not recur; its cause
is not established. This acceptance supports consolidation of the offline batch,
not live continuation, actual receipt settlement, or a claim of stable latency.

The diagnostic correction adds: bounded labelled phases cover
fixture setup, entry collection/settlement, both predecessor preparations and
expiry waits, the connected attempt, validation and recovery. Each failure records
an allowlisted code/type; precursor collector results retain only safe flags and
bounded counts. Failed phases also retain up to eight module/function/line code
locations within the checked-out position-book code, without source lines or
local variable values. No raw exceptions, provider responses, paths, transaction wires or
keys are copied. Diagnostic timing never grants execution or changes its clocks.
The command publishes the failure report and exits **2** for `review-required`.
An existing output remains protected from overwrite.

Future diagnostic reruns should still be uploaded even if they exit 2. A pass
requires all 16 connected/fault and 14 independent signer cases. No retry of a user position,
new continuation allowance, timing relaxation or service change is introduced.

Local verification of the diagnostic correction passed seven diagnostic safety
checks, the full three-test CLI/integration suite (16 connected/fault cases plus
14 independent signer cases), and two CI partition checks. The synthetic connected
attempt took 2,698.745 ms. The subsequent Kali acceptance is recorded above.

## Connected contract

`fresh_exit.continue_sign_submit` connects the existing third-generation record to
the isolated Node signer and guarded one-send transport. It requires both exact,
distinct predecessor hashes and three exact boolean opt-ins: continuation,
private-key signing and devnet submission. Existing ordinary and replacement
wrappers reject continuation selectors. The internal generation modes are
mutually exclusive; none is selected automatically.

The existing source locks, full history/provenance replay, STOP checks and signer
contract remain active. The signer request and every sender guard bind to the
new record hash and its original deadline. Collection has at most 20 requests;
transport has at most five, including at most one application send request. The
10-second freshness deadline and shared 30-second budget are not increased.

Both expired predecessors, entry accounting, cumulative fee commitments and
protected inventory remain preserved. A persisted continuation consumes its slot
even if the deadline expires before signing. An uncertain signing response keeps
the attempt unresolved. A lost send response is recovered only by observing the
recorded signature; recovery never recollects, signs or resends. Finalized receipt
evidence still does not release holds or constitute scoped receipt settlement.

This release adds **no operational continuation CLI**. The sole new CLI accepts
`--output`, runs synthetic offline fixtures and publishes an exclusive private
report. It rejects wallet, pool, directory, action and submission flags. Fixture
setup and the connected test use disposable signing keys; no user keys are used.

## Acceptance evidence

The connected rehearsal uses the actual isolated signer with real wall time and
synthetic provider replies. It lets both predecessors expire naturally, collects
and appends the continuation, signs its exact request, loses one synthetic send
response, removes the disposable key, and recovers with STOP set. A second
recovery must preserve the durable evidence byte-for-byte. The test independently
replays all three generations through the 14-case Node contract mutation suite.

Fault cases cover STOP before/after persistence, wrong predecessor identities,
backend markers, write failure, shared-budget exhaustion, collection expiry,
persisted expiry before signing and uncertain signer responses. Repetition after
persistence must make zero collection/key/send attempts. Independent unit checks
cover generation selector exclusivity, malformed identities and rejected
operational command flags. Existing replacement and ordinary exit paths remain
regression targets.

Timing is diagnostic only. Passing synthetic RPC proves the connection and
ordering, not that real network latency fits the remaining deadline. No deadline
is extended to obtain a pass. A report with `review-required` is not acceptance.

The initial connected run passed with 3,089.549 ms elapsed and 7,684 ms of
reported deadline headroom (the shared coordinator begins before the collector's
10-second window, so these durations are not complements). It used 20 synthetic
collection requests, five sender requests, one signature and one send. The
existing replacement regression also passed all 12 integration and 10 independent
signer cases. The final extended continuation run passed all 16 fault/connected cases and
14 independent contract cases, with a 2,646.907 ms connected attempt. All three
CLI/integration unit tests, six targeted ordinary-exit/continuation regressions
and two CI partition checks passed. The Kali result remains required for host
acceptance.

## Kali acceptance

Fetch the exact branch/commit supplied in chat, then run:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/continuation_exit_cli.py" \
  --output "$PWD/radar-continuation-integration-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

The full disposable fixture setup can take several minutes; only the separately
reported connected attempt is measured against its freshness deadline. Expected:
`offline-integration-passed`, 16 connected/fault cases and 14 independent signer
contract cases. Upload the public `.json.gz` report. No sudo, Docker rebuild or
service restart is needed.

## Next gates

1. Accept the connected Kali report and consolidate the continuation work with
   the retained regression/CI checks.
2. Design a narrowly scoped operational continuation command with preflight
   identity inspection, explicit opt-ins and recovery-only behavior after any
   uncertain attempt. Do not repeat the old replacement command.
3. After separately reviewed execution evidence, reconcile the exact finalized
   exit receipt and fresh balances, then close only this position's scoped holds.

The actual held devnet exit is unresolved. Scanner, sampling, alerts, backup jobs
and frozen study definitions are unchanged. Availability captures on November 5
and 6 remain separate. This gate does not establish mainnet readiness or returns.
