# Unsigned exit replacement consolidation — November 4, 2026

The controlled devnet entry was reconciled, but its first exit preparation expired
before signing. This batch preserves that preparation and permits one separately
identified replacement internally, with independent validation before signing.

Three increments are included: read-only preparation inspection; append-only
unsigned replacement; and connected replacement signing/one-send recovery.
Their Kali checks passed 11, 17 and 12 cases respectively. The final November 4
04:23:09 UTC report also passed ten independent signer-contract cases.

The final host exercise used 20 synthetic collection requests and five sender
requests, exactly one send attempt and one recorded signature. Its lost-response
recovery observed finalized synthetic evidence without sending and kept the
reservation held. Disposable keys and temporary ledgers were used; no production
wallet, network, scanner, observer or study was changed. The measured connected
stage took 6,546.413 ms and completed within its original deadline. This does not
predict real RPC latency or establish the exit of the user's position.

Original evidence, ownership, protected inventory, fee caps, STOP handling and
one-attempt boundaries remain intact. Repeated execution cannot collect a second
replacement. Unknown effects remain held and require inspection.

Consolidation requires all twelve CI groups on the reviewed commit before merge.
Next: expose one explicit controlled-devnet replacement action, preserving exact
original identity and three separate opt-ins; verify the command boundary, then
inspect the existing host state before any signing. Finalized receipt accounting
and fresh-balance closure follow separately. No automatic retry or new entry.

The availability study remains unchanged. November 3 capture was confirmed by the
user. Preserve November 5 and 6 captures and review on November 6 at 00:05 UTC
(01:05 Europe/Amsterdam). Engineering acceptance is separate from economic
qualification and does not authorize a real-money pilot.

## Review correction: active transport context

PR review identified that the transport's context-slot floor still came directly
from the original preparation table. With a later replacement, that could permit
a blockhash or fee response older than the evidence being signed. Transport now
replays the active preparation and verifies that its hash matches the signing
request before deriving the context floor. Both blockhash and fee checks, saved
send-boundary replay and send options inherit that active floor.

Regression coverage includes a real replacement whose maximum context advances
from 112 to 122, rejection of older blockhash and fee contexts, unchanged original-
only behavior, a mismatched signing identity and corrupt replacement rejection.
No previously accepted stale proof is silently grandfathered or resubmitted.

The active preparation is handed directly from the successful signing replay to
the transport in the same read. This avoids a second full replay per call without
introducing a cache or skipping validation; failed replay publishes no preparation.

CI measured partition 1 reaching its ten-minute job limit without a test failure.
The 183-second accounting-recovery module moves to partition 2 (previously 268
seconds), and unsigned replacement is assigned to partition 4 (previously 305
seconds). Every module remains included exactly once; test and execution deadlines
are unchanged. The complete matrix must pass again on this assignment.
