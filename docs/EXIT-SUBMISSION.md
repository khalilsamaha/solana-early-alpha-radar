# One-send exit submission and recovery — 31 October 2026

The restricted exit key backend passed its exact 27-case Kali replay at
2026-10-31 18:14:04 UTC. This increment adds internal fixed-devnet transport for
its already-signed exit. There is no live execution CLI or scanner integration.
The public host exercise uses existing public signatures and synthetic responses.

## Before the application send boundary

The sender requires explicit internal opt-in, the same wallet/pool scope, the
private backend attempt and acknowledgment, and the exact signed reverse message.
It replays the collected evidence, acquired quantity, source history and held fees
under the cooperating wallet lock. STOP, expired original deadlines, changed
source history and missing backend acknowledgments refuse before a send.

Four fixed-endpoint RPC reads check devnet genesis, blockhash validity, the exact
message fee and devnet genesis again. Their context cannot precede the collected
account/quote/simulation evidence. The fee must fit the original exit cap. The
sender replays current local evidence again while holding the SQLite writer
reservation, then commits the exact signature, request, signing head, endpoint and
preflight evidence before the only possible application send call.

The send uses the exact saved wire, preflight enabled, `maxRetries=0` and a minimum
context slot. No new signature, automatic retry, blockhash replacement or refreshed
deadline is permitted. The final STOP/deadline check happens after commit. A crash,
STOP or expiry in that interval leaves an uncertain attempt even if no packet was
sent. A repeated call observes the existing boundary and never calls transport.
This is an application-level one-attempt guarantee, not a claim of exactly-once
network delivery or chain execution.

## Recovery evidence and remaining accounting gate

Recovery only queries the original signature and exact transaction at the fixed
devnet endpoint, with genesis checks around the observation. It can run after STOP
or expiry, without opening a key. Each observation is atomically stored with its
boundary hash, previous capture hash and original clocks. The cap is eight captures
of at most 4 MiB, within the existing 64 MiB admission-ledger cap. A saved terminal
capture replays without another RPC request.

Matching finalized signature/slot/error headers and the exact signed wire produce
`exit-finalized-evidence` or `exit-failed-evidence`. These are **RPC finality claims**,
not reconciled balance effects or cryptographic finality proof. Missing or merely
confirmed evidence stays unknown. Wrong genesis, wire, response signature or
contradictory terminal evidence quarantines the path. The public output withholds
signed wires and raw RPC payloads.

This increment does not verify token transfer effects, actual fees, residual
balances or principal return. `receiptEffectsReconciled`,
`residualInventoryVerified`, `reservationReleased` and `allocationTransferred`
remain false. The next increment must replay full receipt effects and reconcile
acquired inventory, fees and any residuals before releasing commitments.

## Validation scope and timing limitation

All 32 targeted Python tests passed: 12 transport tests (including the complete
24-case portable CLI), one full-source integration/restore test and 19 existing
private-recovery regressions. Source hygiene and package manifests passed.

The transport tests cover a committed boundary before the synthetic send, duplicate
calls, post-commit STOP/expiry, lost responses, capture limits, bad cluster/context,
changed wire, fee caps, changed source history and conflicting finality evidence.
The existing 19 private-recovery regressions passed. The full-source test connects
the actual disposable-key backend to synthetic transport and verifies isolated
restore after key removal, with a tampered-marker rejection.

The initial implementation exposed a nested SQLite transaction; the corrected
writer path uses a separate read-only replay connection while its writer
reservation remains held. A wall-clock full-source test also hit the existing
10-second source-read deadline under test load and refused. The completed synthetic
transport/restore test uses a deterministic clock and does not prove live latency.
Before any actual execution, the complete path still needs timing acceptance on
the host within the unchanged original evidence deadline. No production timeout or
freshness guard was relaxed.

## Private recovery and host check

The existing private snapshot verifier includes optional exit transport state and
replays its boundary/capture semantics. It never repairs or sends from a restored
copy. Existing snapshots without exit transport retain their original projection.
No backup service, cloud policy, sampling policy or running scanner changes.

After fetching the exact source commit provided in chat:

```bash
cd "$HOME/apps/solana-early-alpha-radar"
python3 -E -s \
  "$HOME/apps/solana-radar-dev/position-book/exit_submission_cli.py" \
  --output "$PWD/radar-exit-submission-check-$(date -u +%Y%m%dT%H%M%SZ)-$$.json.gz"
```

Expected: `offline-checks-passed`, 24 synthetic cases. No real network requests,
wallet access, new signatures or transactions. No rebuild or restart is needed.
Upload only the public `.json.gz` report. This check is not live execution approval.
The fixed November 6 confirmation-study review is unchanged.
